"""Promise-candidate detection (Phase 5 — Doc 03 §2.7, blueprint Part H).

A rules-based detector over processed raw publications. It flags
sentences that carry commitment language into the PromiseCandidate
queue — it never creates a Promise and never touches the public
tracker. Quote fidelity is the core rule:

- the stored quote is the EXACT sentence from the source item
  (whitespace-trimmed, never paraphrased, never completed);
- an institution is recorded only when the text itself names a known
  ``story_intelligence.Institution`` (in the sentence first, then the
  item text) — otherwise the field stays blank for the human;
- a deadline is stored only as the verbatim phrase the text uses
  ("by December 2027") — the detector never converts a phrase into a
  date, so no date can be invented;
- the location comes from the item's own matched locations.

A human confirms (creating a real Promise through the same field
conventions as the promise desk) or dismisses with a reason. Re-runs
never duplicate a candidate: each (item, quote) pair has one
dedupe key.
"""
import hashlib
import re

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from leadership.capabilities import capabilities_for

from .models import PromiseCandidate, RawPublication, normalize_alias

# Commitment-language rules (label, pattern). Deliberately tight:
# plain reporting ("the governor inspected the ongoing work") matches
# none of these; every hit still lands in a human queue, so a rare
# over-flag costs a dismissal, never a false public promise.
_ACTION_VERBS = (
    'construct|build|renovate|rehabilitate|reconstruct|complete|'
    'commission|provide|supply|establish|create|employ|recruit|'
    'distribute|flag\\s+off|expand|upgrade|deliver'
)
COMMITMENT_PATTERNS = [
    ('will_act', re.compile(
        r'\bwill\s+(?:' + _ACTION_VERBS + r')\b', re.IGNORECASE)),
    ('pledged_to', re.compile(r'\bpledged\s+to\b', re.IGNORECASE)),
    ('promised_to', re.compile(r'\bpromised\s+to\b', re.IGNORECASE)),
    ('promise_to', re.compile(r'\bpromise\s+to\b', re.IGNORECASE)),
    ('vowed_to', re.compile(r'\bvowed\s+to\b', re.IGNORECASE)),
    ('assured_will', re.compile(
        r'\bassured\b[^.!?]{0,80}?\bwill\b', re.IGNORECASE)),
    ('set_to_act', re.compile(
        r'\bset\s+to\s+(?:' + _ACTION_VERBS + r')\b', re.IGNORECASE)),
    ('to_be_completed_by', re.compile(
        r'\bto\s+be\s+completed\s+by\b', re.IGNORECASE)),
]

_MONTHS = ('January|February|March|April|May|June|July|August|'
           'September|October|November|December')
DEADLINE_PATTERNS = [
    re.compile(r'\bto\s+be\s+completed\s+by\s+[^.!?,;]{3,60}', re.IGNORECASE),
    re.compile(r'\bby\s+(?:the\s+end\s+of\s+)?(?:' + _MONTHS + r')\s+\d{4}\b',
               re.IGNORECASE),
    re.compile(r'\bbefore\s+(?:' + _MONTHS + r')\s+\d{4}\b', re.IGNORECASE),
    re.compile(r'\bwithin\s+(?:the\s+next\s+)?\d+\s+(?:weeks?|months?|years?)\b',
               re.IGNORECASE),
    re.compile(r'\bby\s+\d{4}\b', re.IGNORECASE),
]

_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')


class CandidateError(Exception):
    """A candidate action that cannot be performed."""


def has_capability(user, capability):
    return bool(user is not None and user.is_authenticated
                and (user.is_superuser
                     or capability in capabilities_for(user)))


def _sentences(text):
    """Split *text* into its sentences, verbatim (trimmed only)."""
    out = []
    for part in _SENTENCE_SPLIT.split((text or '').strip()):
        sentence = part.strip()
        if sentence:
            out.append(sentence)
    return out


def _item_sentences(pub):
    """All quotable spans of an item: title, then summary, then text."""
    spans = []
    for chunk in (pub.title, pub.summary, pub.text):
        spans.extend(_sentences(chunk))
    return spans


def _deadline_phrase(sentence):
    for pattern in DEADLINE_PATTERNS:
        match = pattern.search(sentence)
        if match:
            return match.group(0).strip()[:160]
    return ''


def _institution_name(sentence, full_text, institution_names):
    """A known institution named in the text, or ''.

    The sentence is checked first; the wider item text is the fallback
    (a statement's speaker is often named in the preceding sentence).
    Only names that already exist as Institution records can match —
    the detector never invents an institution.
    """
    lowered = sentence.lower()
    for name in institution_names:
        if name.lower() in lowered:
            return name
    lowered_full = full_text.lower()
    for name in institution_names:
        if name.lower() in lowered_full:
            return name
    return ''


def _item_lga(pub):
    locations = list(pub.locations.exclude(lga__isnull=True)
                     .select_related('lga'))
    for location in locations:
        if location.match_kind == 'EXPLICIT':
            return location.lga
    return locations[0].lga if locations else None


def dedupe_key_for(pub, quote):
    raw = f'{pub.pk}:{normalize_alias(quote)}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


@transaction.atomic
def detect_for_publication(pub, institution_names=None):
    """Flag commitment sentences on one processed item.

    Idempotent: candidates are get_or_created by dedupe key, so
    reprocessing an item never duplicates its candidates (and never
    resurrects a dismissed one — the row, and its decision, persist).
    Returns the list of candidates for the item.
    """
    if institution_names is None:
        from story_intelligence.models import Institution
        institution_names = list(
            Institution.objects.order_by('name').values_list('name', flat=True))
    full_text = f'{pub.title} {pub.summary} {pub.text}'
    lga = _item_lga(pub)
    found = []
    seen_quotes = set()
    for sentence in _item_sentences(pub):
        if len(sentence) < 25:
            continue
        key = dedupe_key_for(pub, sentence)
        if key in seen_quotes:
            continue
        matched = None
        for label, pattern in COMMITMENT_PATTERNS:
            if pattern.search(sentence):
                matched = label
                break
        if matched is None:
            continue
        seen_quotes.add(key)
        candidate, _created = PromiseCandidate.objects.get_or_create(
            dedupe_key=key,
            defaults={
                'publication': pub,
                'cluster': pub.cluster,
                'quote': sentence[:4000],
                'matched_pattern': matched,
                'institution_name': _institution_name(
                    sentence, full_text, institution_names),
                'lga': lga,
                'deadline_text': _deadline_phrase(sentence),
            })
        found.append(candidate)
    return found


def detect_pending(limit=200):
    """Run detection over processed items that have no candidates yet
    considered — used by the processing step; per-item isolation is
    the caller's job (see relevance.process_pending)."""
    stats = {'candidates': 0, 'items': 0}
    from story_intelligence.models import Institution
    institution_names = list(
        Institution.objects.order_by('name').values_list('name', flat=True))
    items = (RawPublication.objects.filter(relevance__isnull=False)
             .filter(promise_candidates__isnull=True)
             .select_related('cluster')
             .prefetch_related('locations__lga')
             .order_by('discovered_at', 'pk')[:limit])
    for pub in items:
        created = detect_for_publication(pub, institution_names)
        stats['items'] += 1
        stats['candidates'] += len(created)
    return stats


@transaction.atomic
def confirm_candidate(candidate, actor, *, institution=None,
                      institution_name='', title='', description='',
                      announced_by='', announced_on=None, deadline=None,
                      lga=None, sector=''):
    """Confirm a candidate into a real story_intelligence.Promise.

    The promise is created with the promise desk's own conventions:
    it starts ANNOUNCED, carries the source item as its announcement
    source, and is audited in StoryAudit with its monitoring
    provenance. ``deadline`` is a date the confirming editor supplies
    from the stated phrase — the detector's phrase is never parsed
    into a date automatically.
    """
    if not has_capability(actor, 'MANAGE_PROMISES'):
        raise PermissionDenied(
            'Confirming a promise candidate requires the '
            'MANAGE_PROMISES capability.')
    candidate = PromiseCandidate.objects.select_for_update().get(
        pk=candidate.pk)
    if candidate.status != 'PENDING':
        raise CandidateError('This candidate has already been decided.')
    from story_intelligence.models import Institution, Promise
    from story_intelligence.services import log_audit

    if institution is None:
        name = (institution_name or candidate.institution_name or '').strip()
        if not name:
            raise CandidateError(
                'Choose the institution that made this commitment, or '
                'enter its name exactly as stated.')
        institution, _created = Institution.objects.get_or_create(name=name)
    pub = candidate.publication
    if announced_on is None:
        announced_on = (pub.published_at or pub.discovered_at).date()
    promise_lga = lga if lga is not None else candidate.lga
    promise = Promise.objects.create(
        institution=institution,
        title=(title or '').strip()[:250] or _default_title(candidate),
        description=(description or '').strip() or candidate.quote,
        announced_by=(announced_by or '')[:200],
        announced_on=announced_on,
        source_name=pub.source.name[:200],
        source_url=(pub.original_url or '')[:500],
        deadline=deadline,
        sector=sector or '',
        zone=promise_lga.zone if promise_lga else None,
        lga=promise_lga,
        status='ANNOUNCED',
        created_by=actor)
    log_audit(actor, 'PROMISE_CREATED', 'promise', promise.pk,
              {'institution_id': institution.pk, 'status': promise.status,
               'via': 'intelligence_candidate', 'candidate_id': candidate.pk})
    candidate.status = 'CONFIRMED'
    candidate.promise = promise
    candidate.decided_by = actor
    candidate.decided_at = timezone.now()
    candidate.save(update_fields=['status', 'promise', 'decided_by',
                                  'decided_at'])
    from .models import IntelligenceAudit
    IntelligenceAudit.objects.create(
        actor=actor, action='PROMISE_CANDIDATE_CONFIRMED',
        target_type='PromiseCandidate', target_id=candidate.pk,
        detail={'promise_id': promise.pk})
    return promise


def _default_title(candidate):
    quote = candidate.quote.strip()
    return (quote[:247] + '…') if len(quote) > 250 else quote


@transaction.atomic
def dismiss_candidate(candidate, actor, reason=''):
    """Dismiss a candidate; a reason is required and recorded."""
    if not has_capability(actor, 'MANAGE_PROMISES'):
        raise PermissionDenied(
            'Dismissing a promise candidate requires the '
            'MANAGE_PROMISES capability.')
    if not (reason or '').strip():
        raise CandidateError('A reason is required to dismiss a candidate.')
    candidate = PromiseCandidate.objects.select_for_update().get(
        pk=candidate.pk)
    if candidate.status != 'PENDING':
        raise CandidateError('This candidate has already been decided.')
    candidate.status = 'DISMISSED'
    candidate.decision_note = reason.strip()[:2000]
    candidate.decided_by = actor
    candidate.decided_at = timezone.now()
    candidate.save(update_fields=['status', 'decision_note', 'decided_by',
                                  'decided_at'])
    from .models import IntelligenceAudit
    IntelligenceAudit.objects.create(
        actor=actor, action='PROMISE_CANDIDATE_DISMISSED',
        target_type='PromiseCandidate', target_id=candidate.pk,
        detail={'reason_recorded': True})
    return candidate
