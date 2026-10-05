from django.test import TestCase
from rest_framework.test import APIClient
from leadership.models import Zone,LGA,Ward,RoleDefinition
from leadership.roles import ALL_ROLE_TITLES,ROLES_BY_TIER,canonical_role_title
from leadership.capabilities import capabilities_for
from staff.models import User

class CanonicalRoleContractTests(TestCase):
 def test_exactly_41_unique_constitutional_roles(self):
  self.assertEqual(len(ALL_ROLE_TITLES),41)
  self.assertEqual(len(set(ALL_ROLE_TITLES)),41)
  self.assertEqual([len(ROLES_BY_TIER[x]) for x in ("STATE","ZONAL","LGA","WARD")],[20,3,10,8])
 def test_known_legacy_aliases_emit_canonical_titles(self):
  self.assertEqual(canonical_role_title("Financial Secretary"),"Finance Operations Officer")
  self.assertEqual(canonical_role_title("LGA Coordinator"),"LGA Network Lead")

class IdentityAndDashboardContractTests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.zone=Zone.objects.create(name="Kebbi Central")
  self.lga=LGA.objects.create(name="Birnin Kebbi",zone=self.zone)
  self.ward=Ward.objects.create(name="Nassarawa I",lga=self.lga)
 def user(self,name,tier,title,status="VERIFIED",**extra):
  role=RoleDefinition.objects.create(title=title,tier=tier,seat_number=extra.pop("seat",1))
  return User.objects.create_user(username=name,password="StrongPass123!",role=tier,status=status,role_definition=role,zone=self.zone,lga=self.lga,ward=self.ward,phone="08000000000",**extra)
 def test_me_resolves_canonical_identity_capabilities_and_access(self):
  user=self.user("lgaadmin","LGA","LGA Administrative Officer")
  self.client.force_authenticate(user); response=self.client.get("/api/v1/auth/me/")
  self.assertEqual(response.status_code,200)
  self.assertEqual(response.data["tier"],"LGA")
  self.assertEqual(response.data["role_title"],"LGA Administrative Officer")
  self.assertEqual(response.data["dashboard"],"lga_admin")
  self.assertEqual(response.data["access"]["state"],"ALLOWED")
  self.assertIn("REVIEW_APPLICANTS",response.data["capabilities"])
  self.assertIn("SUBMIT_REPORTS",response.data["capabilities"])
 def test_pending_user_has_no_operational_capabilities(self):
  user=self.user("pending","LGA","LGA Adviser",status="PENDING")
  self.client.force_authenticate(user); response=self.client.get("/api/v1/auth/me/")
  self.assertEqual(response.data["access"]["state"],"PENDING_APPROVAL")
  self.assertEqual(response.data["capabilities"],())
  self.assertEqual(self.client.get("/api/v1/dashboards/me/").status_code,403)
 def test_wrong_tier_cannot_call_dashboard(self):
  user=self.user("ward","WARD","Ward Adviser")
  self.client.force_authenticate(user)
  self.assertEqual(self.client.get("/api/v1/dashboards/lga/").status_code,403)
 def test_lga_dashboard_has_real_metrics_and_explicit_unavailable_finance(self):
  user=self.user("lga","LGA","LGA Adviser")
  self.client.force_authenticate(user); response=self.client.get("/api/v1/dashboards/me/")
  self.assertEqual(response.status_code,200)
  blocks={b["key"]:b for b in response.data["blocks"]}
  self.assertEqual(blocks["membership"]["items"][0]["value"],1)
  self.assertFalse(blocks["finance"]["available"])
  self.assertNotIn("lga_balance",str(response.data))
 def test_general_member_self_registration_policy_remains_blocked(self):
  fields=__import__("rest_api.serializers",fromlist=["RegisterSerializer"]).RegisterSerializer().fields
  self.assertTrue(fields["role_definition"].required)
