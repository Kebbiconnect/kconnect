"""Shared membership and jurisdiction access rules."""
from staff.models import User
from .roles import canonical_role_title

def role_title(user):
 role=getattr(user,"role_definition",None)
 return canonical_role_title(role.title) if role else None

def is_verified(user): return bool(getattr(user,"is_authenticated",False) and user.status=="VERIFIED")

def users_in_jurisdiction(user,queryset=None):
 queryset=queryset if queryset is not None else User.objects.all()
 if user.role=="STATE": return queryset
 if user.role=="ZONAL" and user.zone_id: return queryset.filter(zone_id=user.zone_id)
 if user.role=="LGA" and user.lga_id: return queryset.filter(lga_id=user.lga_id)
 if user.role=="WARD" and user.ward_id: return queryset.filter(ward_id=user.ward_id)
 return queryset.filter(pk=user.pk)

def is_in_jurisdiction(user,target):
 if user.pk==target.pk or user.role=="STATE": return True
 if user.role=="ZONAL": return bool(user.zone_id and target.zone_id==user.zone_id)
 if user.role=="LGA": return bool(user.lga_id and target.lga_id==user.lga_id)
 if user.role=="WARD": return bool(user.ward_id and target.ward_id==user.ward_id)
 return False

def can_approve_members(user): return is_verified(user) and user.role in {"STATE","ZONAL","LGA"}
