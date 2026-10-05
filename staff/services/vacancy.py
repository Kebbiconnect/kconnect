"""Shared seat-vacancy rule used by the unchanged website and mobile API."""
from leadership.models import RoleDefinition
from staff.models import User

def _vacant_for(tier, **scope):
 result=[]
 for role in RoleDefinition.objects.filter(tier=tier):
  if not User.objects.filter(role_definition=role,status="VERIFIED",**scope).exists():
   result.append({"id":role.id,"title":role.title,"tier":role.tier})
 return result

def vacant_roles(zone=None,lga=None,ward=None):
 """Preserves the website's established inclusion order and scope rules."""
 result=[]
 if zone and lga: result.extend(_vacant_for("STATE"))
 if zone: result.extend(_vacant_for("ZONAL",zone=zone))
 if lga: result.extend(_vacant_for("LGA",lga=lga))
 if ward: result.extend(_vacant_for("WARD",ward=ward))
 return result

def seat_is_filled(role_definition,zone=None,lga=None,ward=None):
 scope={}
 if role_definition.tier=="ZONAL": scope["zone"]=zone
 elif role_definition.tier=="LGA": scope["lga"]=lga
 elif role_definition.tier=="WARD": scope["ward"]=ward
 return User.objects.filter(role_definition=role_definition,status="VERIFIED",**scope).exists()
