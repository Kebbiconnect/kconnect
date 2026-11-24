"""Geographic term matching over the intelligence directory (Phase 3).

Engine A (explicit) and Engine B (contextual) from Doc 03 §2.3 and
blueprint Part C share one scan: the item's title and body are
normalised with the directory's own ``normalize_alias`` and searched
for directory terms on word boundaries, so a name can never match
inside a longer word.

Terms come from canonical directory names (LGAs, districts, wards,
communities, GeoEntities) and from APPROVED ``GeoAlias`` rows only —
pending or rejected aliases never match, exactly as in
``intelligence.geo``. A match records the term as written in the
directory, the target record and where it was found (title / body).

Signal strength follows the docs:

- a state mention ("Kebbi" / "Kebbi State") or an LGA / district /
  ward / community name is an EXPLICIT signal;
- a GeoEntity name is a CONTEXTUAL signal (the entity implies a
  location without naming it — Doc 03 Engine B), as is a name that is
  ambiguous across more than one LGA.
"""
from collections import namedtuple

from leadership.models import LGA, Ward

from .models import Community, District, GeoAlias, GeoEntity, normalize_alias

Match = namedtuple('Match', [
    'term', 'target_kind', 'record', 'lga', 'where', 'signal',
])

STATE_TERMS = ('kebbi state', 'kebbi')
PLACE_KINDS = ('LGA', 'DISTRICT', 'WARD', 'COMMUNITY')


def _lga_of(kind, record):
    if kind == 'LGA':
        return record
    return getattr(record, 'lga', None)


def build_term_index():
    """Map normalised term -> list of (target_kind, record).

    Canonical names first, then approved aliases. A term can map to
    more than one record (the same community name in two LGAs); the
    classifier treats such terms as ambiguous rather than guessing.
    """
    index = {}

    def add(term, kind, record):
        key = normalize_alias(term)
        if not key:
            return
        entries = index.setdefault(key, [])
        if (kind, record.pk) not in [(k, r.pk) for k, r in entries]:
            entries.append((kind, record))

    for lga in LGA.objects.all():
        add(lga.name, 'LGA', lga)
    for district in District.objects.select_related('lga'):
        add(district.name, 'DISTRICT', district)
    for ward in Ward.objects.select_related('lga'):
        add(ward.name, 'WARD', ward)
    for community in Community.objects.select_related('lga'):
        add(community.name, 'COMMUNITY', community)
    for entity in GeoEntity.objects.select_related('lga'):
        add(entity.name, 'GEO_ENTITY', entity)
    aliases = GeoAlias.objects.filter(status='APPROVED').select_related(
        'lga', 'district', 'ward', 'community', 'geo_entity')
    for alias in aliases:
        target = alias.target
        if target is not None:
            add(alias.alias, alias.target_kind, target)
    return index


def _contains(padded_text, term):
    return f' {term} ' in padded_text


def scan_text(title, body, index=None):
    """Scan *title* and *body* against the directory term index.

    Returns a list of :class:`Match`. State matches carry
    ``target_kind='STATE'`` and ``record=None``. GeoEntity matches and
    matches whose term spans more than one LGA are CONTEXTUAL; all
    other place matches are EXPLICIT.
    """
    index = index if index is not None else build_term_index()
    fields = [('title', f' {normalize_alias(title)} '),
              ('body', f' {normalize_alias(body)} ')]
    matches = []
    seen = set()

    def record_match(term, kind, record, where, signal):
        key = (term, kind, record.pk if record is not None else None, where)
        if key in seen:
            return
        seen.add(key)
        matches.append(Match(
            term=term, target_kind=kind, record=record,
            lga=_lga_of(kind, record) if record is not None else None,
            where=where, signal=signal))

    # State mentions (explicit). "kebbi state" is checked first so the
    # longer, clearer term is the one recorded.
    for where, padded in fields:
        for term in STATE_TERMS:
            if _contains(padded, term):
                record_match(term, 'STATE', None, where, 'EXPLICIT')
                break

    for term, targets in index.items():
        if term in STATE_TERMS:
            continue  # the bare word "Kebbi" is the state signal above
        wheres = [where for where, padded in fields if _contains(padded, term)]
        if not wheres:
            continue
        lgas = {_lga_of(kind, record).pk
                for kind, record in targets
                if _lga_of(kind, record) is not None}
        ambiguous = len(lgas) > 1
        for kind, record in targets:
            if kind == 'GEO_ENTITY' or ambiguous:
                signal = 'CONTEXTUAL'
            else:
                signal = 'EXPLICIT'
            for where in wheres:
                record_match(term, kind, record, where, signal)
    return matches
