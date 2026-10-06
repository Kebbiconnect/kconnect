from django.test import TestCase
from leadership.models import Zone,LGA,Ward,RoleDefinition
from leadership.roles import ROLES_BY_TIER
from staff.models import User

class VacancyContractTests(TestCase):
 def setUp(self):
  self.zone=Zone.objects.create(name="Central"); self.lga=LGA.objects.create(name="Birnin Kebbi",zone=self.zone); self.ward=Ward.objects.create(name="Nassarawa",lga=self.lga)
  for tier,titles in ROLES_BY_TIER.items():
   for n,title in enumerate(titles,1): RoleDefinition.objects.create(title=title,tier=tier,seat_number=n)
  role=RoleDefinition.objects.get(title="Senatorial Director")
  User.objects.create_user(username="zonal",password="x",phone="1",role="ZONAL",status="VERIFIED",role_definition=role,zone=self.zone)
 def expected(self,zone=None,lga=None,ward=None):
  output=[]
  definitions=[]
  if zone and lga: definitions.append(("STATE",{}))
  if zone: definitions.append(("ZONAL",{"zone":zone}))
  if lga: definitions.append(("LGA",{"lga":lga}))
  if ward: definitions.append(("WARD",{"ward":ward}))
  for tier,scope in definitions:
   for role in RoleDefinition.objects.filter(tier=tier):
    if not User.objects.filter(role_definition=role,status="VERIFIED",**scope).exists(): output.append({"id":role.id,"title":role.title,"tier":role.tier})
  return output
 def test_website_json_is_identical_for_five_location_shapes(self):
  cases=[({},None,None,None),({"zone_id":self.zone.id},self.zone,None,None),({"lga_id":self.lga.id},None,self.lga,None),({"zone_id":self.zone.id,"lga_id":self.lga.id},self.zone,self.lga,None),({"zone_id":self.zone.id,"lga_id":self.lga.id,"ward_id":self.ward.id},self.zone,self.lga,self.ward)]
  for params,zone,lga,ward in cases:
   with self.subTest(params=params):
    response=self.client.get('/account/api/check-vacant-roles/',params)
    self.assertEqual(response.status_code,200)
    self.assertEqual(response.json(),{"vacant_roles":self.expected(zone,lga,ward)})
 def test_mobile_endpoint_adds_only_nonempty_tier_summary(self):
  response=self.client.get('/api/v1/registration/vacant-roles/',{"zone":self.zone.id,"lga":self.lga.id,"ward":self.ward.id})
  self.assertEqual(response.status_code,200)
  self.assertEqual([x['tier'] for x in response.data['tiers']],['STATE','ZONAL','LGA','WARD'])
  self.assertEqual(next(x for x in response.data['tiers'] if x['tier']=='ZONAL')['vacant'],2)
 def test_ward_tier_is_not_offered_until_ward_is_selected(self):
  response=self.client.get('/api/v1/registration/vacant-roles/',{"zone":self.zone.id,"lga":self.lga.id})
  self.assertNotIn('WARD',[x['tier'] for x in response.data['tiers']])
 def test_cross_location_selection_is_rejected_by_mobile_api(self):
  other=Zone.objects.create(name="North")
  response=self.client.get('/api/v1/registration/vacant-roles/',{"zone":other.id,"lga":self.lga.id})
  self.assertEqual(response.status_code,400)
