"""Geographic directory lookups.

Phase 1 provides alias resolution: a written name (an LGA name, an approved
alternative spelling, a district/ward/community/entity name) resolves to
exactly one directory record, or to nothing. Phase 2's matching engines
build on this; nothing here guesses — an unmatched name returns None.
"""
from leadership.models import LGA, Ward

from .models import Community, District, GeoAlias, GeoEntity, normalize_alias

_MODELS = (
    (LGA, 'LGA'),
    (District, 'DISTRICT'),
    (Ward, 'WARD'),
    (Community, 'COMMUNITY'),
    (GeoEntity, 'GEO_ENTITY'),
)


def resolve_alias(text):
    """Return (target_kind, record) for *text*, or None if it does not resolve.

    Approved aliases win first; then exact (normalised) directory names.
    Pending or rejected aliases never resolve.
    """
    key = normalize_alias(text)
    if not key:
        return None
    alias = (
        GeoAlias.objects.filter(normalized_alias=key, status='APPROVED')
        .select_related('lga', 'district', 'ward', 'community', 'geo_entity')
        .first()
    )
    if alias is not None and alias.target is not None:
        return alias.target_kind, alias.target
    for model, kind in _MODELS:
        for record in model.objects.all():
            if normalize_alias(record.name) == key:
                return kind, record
    return None


def lga_for(text):
    """Resolve *text* to an LGA record where the match implies one, else None."""
    resolved = resolve_alias(text)
    if resolved is None:
        return None
    kind, record = resolved
    if kind == 'LGA':
        return record
    if kind in ('DISTRICT', 'COMMUNITY'):
        return record.lga
    if kind == 'WARD':
        return record.lga
    if kind == 'GEO_ENTITY':
        return record.lga
    return None
