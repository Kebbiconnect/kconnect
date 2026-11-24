"""Relevance engine for raw publications (Phase 3).

Rules-based and deterministic — no AI anywhere in this path (Doc 03
§1). For each unprocessed :class:`RawPublication` the engine:

1. scans title + body against the geographic directory
   (:mod:`intelligence.matching`, Engines A + B),
2. classifies the item CONFIRMED / STRONG_POSSIBLE / UNCERTAIN /
   NOT_RELEVANT (blueprint Part C §6, Doc 03 §2.3) and stores a
   human-readable reason for every signal that fired,
3. writes one :class:`PublicationLocation` per matched place,
4. attaches rule-based category suggestions
   (:mod:`intelligence.category_rules`),
5. links near-duplicates (flagged, never deleted), and
6. assigns an event cluster (:mod:`intelligence.clustering`).

Classification ladder (conservative, per the docs):

- CONFIRMED — an explicit state mention, or an unambiguous explicit
  mention of an LGA / district / ward / community (name or approved
  alias);
- STRONG_POSSIBLE — contextual evidence only (a GeoEntity that
  implies a location, a place name ambiguous across LGAs): Doc 03
  caps contextual-only evidence here, and an uncertain match is
  never silently converted into a confirmed fact;
- UNCERTAIN — the weakest signal only: the item names nothing, but
  its source is based in a known LGA (the source's home LGA);
- NOT_RELEVANT — no signal at all.

Manual overrides: a classification set by staff (``relevance_manual``)
is preserved verbatim — reprocessing skips the item entirely, manual
location rows are never deleted, and the override is audited
(Doc 03 §2.3: "A human can reclassify; the change is audited").
"""
import time
from datetime import timedelta
from difflib import SequenceMatcher

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import clustering, matching
from .category_rules import suggest_categories
from .models import (
    IntelligenceAudit, IntelligenceCategory, PublicationCategory,
    PublicationLocation, RawPublication, normalize_alias,
)

TITLE_DUPLICATE_THRESHOLD = 0.90
TITLE_SIMILARITY_THRESHOLD = 0.80
TEXT_OVERLAP_THRESHOLD = 0.5
DEDUPE_WINDOW_DAYS = 14

_KIND_FIELD = {
    'LGA': 'lga', 'DISTRICT': 'district', 'WARD': 'ward',
    'COMMUNITY': 'community', 'GEO_ENTITY': 'geo_entity',
}
_KIND_LABEL = {
    'LGA': 'LGA', 'DISTRICT': 'district', 'WARD': 'ward',
    'COMMUNITY': 'community', 'GEO_ENTITY': 'place',
}


def _threshold(name, default):
    return float(getattr(settings, name, default))


def _reason(rule, kind, detail, **extra):
    reason = {'rule': rule, 'kind': kind, 'detail': detail}
    reason.update(extra)
    return reason


def _classify(matches, pub):
    """Return (classification, reasons, location_specs).

    location_specs: {(kind, pk): (record, lga, match_kind, matched_text,
    confidence)} — one row per distinct matched place.
    """
    reasons = []
    specs = {}
    state_hit = False
    explicit_lgas = set()
    ambiguous_terms = set()

    def add_spec(kind, record, lga, match_kind, term, confidence):
        key = (kind, record.pk)
        current = specs.get(key)
        # An explicit row beats a contextual row for the same place.
        if current is None or (current[2] == 'CONTEXTUAL' and match_kind == 'EXPLICIT'):
            specs[key] = (record, lga, match_kind, term, confidence)

    for match in matches:
        if match.target_kind == 'STATE':
            state_hit = True
            reasons.append(_reason(
                'state_mention', 'EXPLICIT',
                f"{match.where.capitalize()} mentions '{match.term}' (Kebbi State).",
                entity_kind='STATE', matched_text=match.term, where=match.where))
            continue
        label = _KIND_LABEL[match.target_kind]
        if match.signal == 'EXPLICIT':
            if match.lga is not None:
                explicit_lgas.add(match.lga.pk)
            add_spec(match.target_kind, match.record, match.lga,
                     'EXPLICIT', match.term, 1.0)
            reasons.append(_reason(
                'explicit_mention', 'EXPLICIT',
                f"{match.where.capitalize()} mentions '{match.term}' "
                f"({label}: {match.record}).",
                entity_kind=match.target_kind, entity=str(match.record),
                matched_text=match.term, where=match.where))
        else:
            add_spec(match.target_kind, match.record, match.lga,
                     'CONTEXTUAL', match.term, 0.6)
            if match.target_kind == 'GEO_ENTITY':
                detail = (f"{match.where.capitalize()} mentions "
                          f"'{match.term}' ({label}: {match.record}), which "
                          f"implies a location without naming it.")
            else:
                ambiguous_terms.add(match.term)
                detail = (f"{match.where.capitalize()} mentions "
                          f"'{match.term}' ({label}: {match.record}), a name "
                          f"shared by more than one LGA, so it cannot "
                          f"confirm one location.")
            reasons.append(_reason(
                'contextual_signal', 'CONTEXTUAL', detail,
                entity_kind=match.target_kind, entity=str(match.record),
                matched_text=match.term, where=match.where))

    if state_hit or explicit_lgas:
        return 'CONFIRMED', reasons, specs
    if specs:
        return 'STRONG_POSSIBLE', reasons, specs
    home_lga = getattr(pub.source, 'home_lga', None)
    if home_lga is not None:
        specs[('LGA', home_lga.pk)] = (home_lga, home_lga, 'CONTEXTUAL',
                                       pub.source.name, 0.4)
        reasons.append(_reason(
            'source_home_lga', 'CONTEXTUAL',
            f"No place is named, but the source ({pub.source.name}) is "
            f"based in {home_lga}.",
            entity_kind='LGA', entity=str(home_lga),
            matched_text=pub.source.name, where='source'))
        return 'UNCERTAIN', reasons, specs
    reasons.append(_reason(
        'no_match', 'NONE',
        'No Kebbi State, LGA, district, ward, community or known place '
        'is mentioned, and no contextual signal applies.'))
    return 'NOT_RELEVANT', reasons, specs


def _tokens(text):
    return {word for word in normalize_alias(text).split() if len(word) > 2}


def _text_overlap(first, second):
    one = _tokens(f'{first.summary} {first.text}')
    two = _tokens(f'{second.summary} {second.text}')
    if not one or not two:
        return 0.0
    return len(one & two) / min(len(one), len(two))


def find_duplicate(pub):
    """The canonical item *pub* is a near-duplicate of, or None.

    Layered after URL dedupe (Doc 03 §2.4): identical content
    fingerprint, or a near-identical title, or a similar title with
    substantially overlapping text — inside a ±14-day window. The
    canonical item is the earliest one in the duplicate group, so
    only items discovered before *pub* (or at the same moment, with a
    lower pk) can be its canonical: an item never links forward to a
    later report of the same story.
    """
    window = timedelta(days=DEDUPE_WINDOW_DAYS)
    earlier = (Q(discovered_at__lt=pub.discovered_at)
               | Q(discovered_at=pub.discovered_at, pk__lt=pub.pk))
    candidates = (
        RawPublication.objects
        .filter(discovered_at__gte=pub.discovered_at - window,
                discovered_at__lte=pub.discovered_at + window)
        .filter(earlier)
        .order_by('discovered_at', 'pk')[:300])
    exact = [c for c in candidates if c.content_fingerprint == pub.content_fingerprint]
    if exact:
        canonical = exact[0]
        return canonical.duplicate_of or canonical
    title_threshold = _threshold(
        'KPN_INTELLIGENCE_TITLE_DUPLICATE_THRESHOLD', TITLE_DUPLICATE_THRESHOLD)
    similarity_threshold = _threshold(
        'KPN_INTELLIGENCE_TITLE_SIMILARITY_THRESHOLD', TITLE_SIMILARITY_THRESHOLD)
    clean = normalize_alias(pub.title)
    for cand in candidates:
        ratio = SequenceMatcher(None, clean, normalize_alias(cand.title)).ratio()
        if ratio >= title_threshold:
            return cand.duplicate_of or cand
        if ratio >= similarity_threshold and _text_overlap(pub, cand) >= TEXT_OVERLAP_THRESHOLD:
            return cand.duplicate_of or cand
    return None


@transaction.atomic
def process_publication(pub, index=None):
    """Run the full Phase 3 pipeline over one raw publication.

    Idempotent: engine-written location/category rows are replaced,
    MANUAL location rows and manual classifications are preserved,
    and cluster/duplicate links, once set, are never moved.
    """
    if pub.relevance_manual:
        return pub
    body = f'{pub.summary} {pub.text}'
    matches = matching.scan_text(pub.title, body, index=index)
    classification, reasons, specs = _classify(matches, pub)

    PublicationLocation.objects.filter(publication=pub).exclude(
        match_kind='MANUAL').delete()
    for (kind, _pk), (record, lga, match_kind, term, confidence) in specs.items():
        fields = {_KIND_FIELD[kind]: record}
        fields['lga'] = lga  # denormalised owning LGA (same record for LGA rows)
        PublicationLocation.objects.create(
            publication=pub, match_kind=match_kind,
            matched_text=term[:160], confidence=confidence, **fields)

    PublicationCategory.objects.filter(publication=pub).delete()
    categories = {c.slug: c for c in IntelligenceCategory.objects.all()}
    for position, suggestion in enumerate(
            suggest_categories(pub.title, pub.summary, pub.text)):
        category = categories.get(suggestion['slug'])
        if category is None:
            continue
        PublicationCategory.objects.create(
            publication=pub, category=category,
            is_primary=(position == 0), reason=suggestion['reason'])

    pub.relevance = classification
    pub.relevance_reasons = reasons
    pub.processed_at = timezone.now()
    pub.save(update_fields=['relevance', 'relevance_reasons', 'processed_at'])

    if not pub.duplicate_of_id:
        canonical = find_duplicate(pub)
        if canonical is not None and canonical.pk != pub.pk:
            pub.duplicate_of = canonical
            pub.save(update_fields=['duplicate_of'])
    clustering.assign_cluster(pub)
    return pub


def process_pending(limit=200, deadline=None):
    """Process unprocessed items, oldest first, isolating failures.

    Returns a stats dict. ``deadline`` is a ``time.monotonic()`` value;
    processing stops cleanly when it passes so the collection cycle
    keeps its time budget.

    Phase 5: each successfully processed item also passes through the
    promise-candidate detector, in its own isolation boundary — a
    detector failure never marks the item failed and never stops the
    batch (detection is a lead generator, not a gate).
    """
    stats = {'processed': 0, 'failed': 0, 'clusters': 0,
             'promise_candidates': 0}
    pending = (RawPublication.objects.filter(relevance__isnull=True)
               .select_related('source')
               .order_by('discovered_at', 'pk')[:limit])
    index = matching.build_term_index()
    known_clusters = set()
    for pub in pending:
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            process_publication(pub, index=index)
            stats['processed'] += 1
            if pub.cluster_id:
                known_clusters.add(pub.cluster_id)
        except Exception:  # one bad item must never stop the batch
            stats['failed'] += 1
            continue
        try:
            from . import promise_detection
            stats['promise_candidates'] += len(
                promise_detection.detect_for_publication(pub))
        except Exception:  # detection must never stop processing
            pass
        try:
            # Phase 6 alert rule: a Confirmed item in a sensitive
            # category alerts the security-desk holders (once per
            # item — the alert dedupe key sees to that).
            if pub.relevance == 'CONFIRMED':
                primary = (pub.category_links.filter(is_primary=True)
                           .select_related('category').first())
                if primary is not None and primary.category.is_sensitive:
                    from . import alerts as alert_service
                    alert_service.fire_sensitive_confirmed(pub)
        except Exception:  # alerting must never stop processing
            pass
    stats['clusters'] = len(known_clusters)
    return stats


def set_manual_relevance(pub, classification, actor):
    """Record a staff reclassification (Doc 03 §2.3) and audit it.

    The engine preserves manual classifications verbatim on every
    later run; the change itself is written to the intelligence
    audit log with no source text in the detail.
    """
    if classification not in dict(RawPublication.RELEVANCE):
        raise ValueError(f'Unknown relevance classification: {classification}')
    label = dict(RawPublication.RELEVANCE)[classification]
    pub.relevance = classification
    pub.relevance_manual = True
    pub.processed_at = timezone.now()
    reasons = [r for r in (pub.relevance_reasons or [])
               if r.get('rule') != 'manual_override']
    reasons.append(_reason(
        'manual_override', 'MANUAL',
        f'Manually classified as {label} by staff; the engines '
        f'preserve this classification.'))
    pub.relevance_reasons = reasons
    pub.save(update_fields=['relevance', 'relevance_reasons',
                            'relevance_manual', 'processed_at'])
    IntelligenceAudit.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action='RELEVANCE_MANUAL', target_type='RawPublication',
        target_id=pub.pk, detail={'relevance': classification})
    return pub
