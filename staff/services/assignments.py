"""Transactional leadership assignment shared by website and native administration."""
from django.core.exceptions import ValidationError
from django.db import transaction
from leadership.models import RoleDefinition
from staff.models import User

FIELDS=("role", "role_definition", "zone", "lga", "ward")

def validate_location(definition, zone=None, lga=None, ward=None, registration=False):
    if definition and definition.tier not in {"STATE","ZONAL","LGA","WARD"}:
        raise ValidationError("Choose a valid leadership tier.")
    if lga and zone and lga.zone_id != zone.pk:
        raise ValidationError("The selected LGA does not belong to the selected zone.")
    if ward and lga and ward.lga_id != lga.pk:
        raise ValidationError("The selected ward does not belong to the selected LGA.")
    if ward and zone and ward.lga.zone_id != zone.pk:
        raise ValidationError("The selected ward does not belong to the selected zone.")
    tier=definition.tier if definition else "GENERAL"
    if registration and not definition:
        raise ValidationError("Registration is leadership-only; choose a position.")
    if tier=="STATE" and registration and (not zone or not lga):
        raise ValidationError("Zone and LGA are required for State Executive applications.")
    if tier=="ZONAL" and not zone: raise ValidationError("Zone is required for this position.")
    if tier=="LGA" and not lga: raise ValidationError("LGA is required for this position.")
    if tier=="WARD" and not ward: raise ValidationError("Ward is required for this position.")
    if ward and not lga: lga=ward.lga
    if lga and not zone: zone=lga.zone
    return {"role":tier,"role_definition":definition,"zone":zone,"lga":lga,"ward":ward}

@transaction.atomic
def assign_member(member_id, definition, zone=None, lga=None, ward=None, verified=False, approver=None):
    member=User.objects.select_for_update().get(pk=member_id, is_superuser=False)
    values=validate_location(definition,zone,lga,ward)
    if definition:
        RoleDefinition.objects.select_for_update().get(pk=definition.pk)
        scope={"role_definition":definition,"status":"VERIFIED"}
        key={"ZONAL":"zone","LGA":"lga","WARD":"ward"}.get(definition.tier)
        if key: scope[key]=values[key]
        if (member.status=="VERIFIED" or verified) and User.objects.filter(**scope).exclude(pk=member.pk).exists():
            raise ValidationError("This leadership seat is already occupied.")
    for key,value in values.items(): setattr(member,key,value)
    if verified:
        from django.utils import timezone
        member.status="VERIFIED";member.approved_by=approver;member.date_approved=timezone.now()
    member.save()
    return member

@transaction.atomic
def swap_members(first_id,second_id):
    if first_id==second_id: raise ValidationError("Choose two different members.")
    members=list(User.objects.select_for_update().filter(pk__in=[first_id,second_id],is_superuser=False).order_by("pk"))
    if len(members)!=2: raise ValidationError("Both members must exist and cannot be administrators.")
    definitions=sorted({u.role_definition_id for u in members if u.role_definition_id})
    list(RoleDefinition.objects.select_for_update().filter(pk__in=definitions).order_by("pk"))
    first,second=members
    first_values={k:getattr(first,k) for k in FIELDS};second_values={k:getattr(second,k) for k in FIELDS}
    # Verified-seat guards are immediate. Vacate both seats only inside this
    # atomic transaction, then restore each original status with its swapped seat.
    User.objects.filter(pk__in=[first.pk,second.pk],status="VERIFIED").update(status="UNDER_REVIEW")
    for member,values in ((first,second_values),(second,first_values)):
        for key,value in values.items():setattr(member,key,value)
        member.save()
    return first,second
