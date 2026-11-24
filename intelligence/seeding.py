"""Idempotent seeding of the geographic directory (blueprint Part C §5).

Kept out of the migrations on purpose: ``leadership.Zone.name`` is unique and
pre-seeding zones in a migration collides with existing test fixtures that
create zones by name. This module is run by the
``seed_intelligence_directory`` management command, which ``release_migrate``
invokes automatically inside the release advisory lock on every start
(production deploys have no shell access, so no step may be manual). It is
idempotent and safe to re-run by hand as well.

Variant spellings already present in a database (for example the
``leadership`` seed data's 'Aliero' and 'Wasagu/Danko') are kept as the LGA
rows; the canonical spellings become APPROVED aliases so both resolve.
"""
from leadership.models import LGA, Zone

from .models import GeoAlias, normalize_alias

ZONES = {
    'Kebbi North': ['Arewa', 'Argungu', 'Augie', 'Bagudo', 'Dandi', 'Suru'],
    'Kebbi Central': [
        'Aleiro', 'Birnin Kebbi', 'Bunza', 'Gwandu', 'Jega', 'Kalgo',
        'Koko/Besse', 'Maiyama',
    ],
    'Kebbi South': [
        'Danko/Wasagu', 'Fakai', 'Ngaski', 'Sakaba', 'Shanga', 'Yauri', 'Zuru',
    ],
}

# Existing spellings found in the leadership seed data -> canonical name.
VARIANTS = {
    'Aliero': 'Aleiro',
    'Wasagu/Danko': 'Danko/Wasagu',
}

# Extra approved aliases (alias text -> canonical LGA name).
EXTRA_ALIASES = {
    'Wasagu': 'Danko/Wasagu',
    'Danko Wasagu': 'Danko/Wasagu',
}


def _find_lga(name, variant_names):
    for candidate in [name, *variant_names]:
        row = LGA.objects.filter(name__iexact=candidate).first()
        if row is not None:
            return row
    return None


def _approve_alias(alias_text, lga):
    normalized = normalize_alias(alias_text)
    if not normalized:
        return
    existing = GeoAlias.objects.filter(normalized_alias=normalized).first()
    if existing is not None:
        if existing.lga_id == lga.id and existing.status == 'APPROVED':
            return
        if existing.lga_id != lga.id:
            return  # never steal an alias that points elsewhere
        existing.status = 'APPROVED'
        existing.save(update_fields=['status'])
        return
    GeoAlias.objects.create(
        alias=alias_text, normalized_alias=normalized, target_kind='LGA',
        lga=lga, status='APPROVED')


def seed_directory():
    """Create any missing zones, the 21 LGAs and starter aliases."""
    variants_by_canonical = {}
    for variant, canonical in VARIANTS.items():
        variants_by_canonical.setdefault(canonical, []).append(variant)

    canonical_rows = {}
    for zone_name, lga_names in ZONES.items():
        zone, _ = Zone.objects.get_or_create(name=zone_name)
        for name in lga_names:
            row = _find_lga(name, variants_by_canonical.get(name, []))
            if row is None:
                row = LGA.objects.create(name=name, zone=zone)
            canonical_rows[name] = row

    for variant, canonical in VARIANTS.items():
        row = canonical_rows[canonical]
        # Whichever spelling the row does not carry becomes an approved alias.
        other = variant if row.name.lower() == canonical.lower() else canonical
        _approve_alias(other, row)
    for alias_text, canonical in EXTRA_ALIASES.items():
        _approve_alias(alias_text, canonical_rows[canonical])
    return canonical_rows
