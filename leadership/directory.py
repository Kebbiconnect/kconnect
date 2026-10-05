"""Public leadership seat projection; exposes no private member fields."""
from leadership.models import Zone,LGA,Ward,RoleDefinition
from staff.models import User

def _location(tier,obj=None):
 if tier=="STATE": return {"label":"Kebbi State","zone":None,"zone_name":None,"lga":None,"lga_name":None,"ward":None,"ward_name":None}
 if tier=="ZONAL": return {"label":obj.name,"zone":obj.id,"zone_name":obj.name,"lga":None,"lga_name":None,"ward":None,"ward_name":None}
 if tier=="LGA": return {"label":f"{obj.name} LGA","zone":obj.zone_id,"zone_name":obj.zone.name,"lga":obj.id,"lga_name":obj.name,"ward":None,"ward_name":None}
 return {"label":f"{obj.name} Ward","zone":obj.lga.zone_id,"zone_name":obj.lga.zone.name,"lga":obj.lga_id,"lga_name":obj.lga.name,"ward":obj.id,"ward_name":obj.name}

def _location_id(tier,obj): return "state" if tier=="STATE" else obj.id

def _holder_for(role,tier,obj):
 qs=User.objects.filter(role_definition=role,status="VERIFIED",is_superuser=False).order_by("id")
 if tier=="ZONAL": qs=qs.filter(zone=obj)
 elif tier=="LGA": qs=qs.filter(lga=obj)
 elif tier=="WARD": qs=qs.filter(ward=obj)
 return qs.first()

def seat_record(role,obj=None,request=None):
 holder=_holder_for(role,role.tier,obj); photo=None
 if holder and holder.photo:
  photo=holder.photo.url
  if request: photo=request.build_absolute_uri(photo)
 return {"seat_key":f"{role.tier}:{role.id}:{_location_id(role.tier,obj)}","role_definition":role.id,"role_title":role.title,"tier":role.tier,"seat_number":role.seat_number,"location":_location(role.tier,obj),"status":"FILLED" if holder else "VACANT","holder":({"id":holder.id,"name":holder.get_full_name(),"photo":photo} if holder else None)}

def locations_for(tier,zone=None,lga=None,ward=None,require_vacancy_scope=False):
 if tier=="STATE": return [None]
 if tier=="ZONAL": return list(Zone.objects.filter(pk=zone.pk)) if zone else ([] if require_vacancy_scope else list(Zone.objects.all()))
 if tier=="LGA":
  if lga: return [lga]
  if require_vacancy_scope: return []
  return list(LGA.objects.select_related("zone").filter(zone=zone) if zone else LGA.objects.select_related("zone").all())
 if ward: return [ward]
 if lga: return list(Ward.objects.select_related("lga__zone").filter(lga=lga))
 if require_vacancy_scope: return []
 return list(Ward.objects.select_related("lga__zone").filter(lga__zone=zone) if zone else Ward.objects.select_related("lga__zone").all())

def leadership_seats(tier=None,zone=None,lga=None,ward=None,status="FILLED",request=None):
 tiers=[tier] if tier else ["STATE","ZONAL","LGA","WARD"]
 records=[]; needs_scope=status in {"VACANT","all"}
 for current in tiers:
  roles=RoleDefinition.objects.filter(tier=current).order_by("seat_number","id")
  for location in locations_for(current,zone,lga,ward,needs_scope):
   for role in roles:
    record=seat_record(role,location,request)
    if status=="all" or record["status"]==status: records.append(record)
 return records
