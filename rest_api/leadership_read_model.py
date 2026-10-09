"""Batched public seat projection; mirrors website seat semantics without per-seat SQL.

Only public fields are projected. Website directory functions/models are untouched.
"""
from leadership.models import RoleDefinition
from leadership.directory import locations_for, _location, _location_id
from staff.models import User


def leadership_seats(tier=None, zone=None, lga=None, ward=None, status='FILLED', request=None):
    tiers = [tier] if tier else ['STATE', 'ZONAL', 'LGA', 'WARD']
    roles = list(RoleDefinition.objects.filter(tier__in=tiers).order_by('seat_number', 'id'))
    by_tier = {name: [role for role in roles if role.tier == name] for name in tiers}
    holders = {}
    definitions = {role.pk: role for role in roles}
    # Same candidate filter and oldest-holder rule as the authoritative website directory.
    users = User.objects.filter(role_definition_id__in=definitions, status='VERIFIED', is_superuser=False).only(
        'id', 'role_definition', 'first_name', 'last_name', 'photo', 'zone', 'lga', 'ward'
    ).order_by('id')
    for user in users:
        current = definitions[user.role_definition_id].tier
        location_id = {'STATE': 'state', 'ZONAL': user.zone_id, 'LGA': user.lga_id, 'WARD': user.ward_id}[current]
        holders.setdefault((user.role_definition_id, location_id), user)
    records = []
    needs_scope = status in {'VACANT', 'all'}
    for current in tiers:
        for location in locations_for(current, zone, lga, ward, needs_scope):
            for role in by_tier[current]:
                location_id = _location_id(current, location)
                user = holders.get((role.pk, location_id))
                state = 'FILLED' if user else 'VACANT'
                if status != 'all' and state != status:
                    continue
                photo = user.photo.url if user and user.photo else None
                if photo and request:
                    photo = request.build_absolute_uri(photo)
                records.append({
                    'seat_key': f'{current}:{role.pk}:{location_id}',
                    'role_definition': role.pk, 'role_title': role.title,
                    'tier': current, 'seat_number': role.seat_number,
                    'location': _location(current, location), 'status': state,
                    'holder': {'id': user.pk, 'name': user.get_full_name(), 'photo': photo} if user else None,
                })
    return records
