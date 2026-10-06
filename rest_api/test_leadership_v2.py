from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from leadership.models import Zone,LGA,Ward,RoleDefinition
from leadership.roles import LGA_ROLES,WARD_ROLES
from staff.models import User

class LeadershipV2Tests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.zone=Zone.objects.create(name="Kebbi Central")
  self.other_zone=Zone.objects.create(name="Kebbi North")
  self.lga=LGA.objects.create(name="Birnin Kebbi",zone=self.zone)
  self.other_lga=LGA.objects.create(name="Argungu",zone=self.other_zone)
  self.ward=Ward.objects.create(name="Nassarawa I",lga=self.lga)
  for number,title in enumerate(LGA_ROLES,1): RoleDefinition.objects.create(title=title,tier="LGA",seat_number=number)
  for number,title in enumerate(WARD_ROLES,1): RoleDefinition.objects.create(title=title,tier="WARD",seat_number=number)
  role=RoleDefinition.objects.get(title="LGA Network Lead")
  self.holder=User.objects.create_user(username="lead",password="x",first_name="Amina",last_name="Bello",email="private@example.com",phone="080123",role="LGA",status="VERIFIED",role_definition=role,zone=self.zone,lga=self.lga,photo=SimpleUploadedFile("leader.jpg",b"photo",content_type="image/jpeg"))
 def test_default_returns_filled_seats_only_with_location_and_photo(self):
  response=self.client.get("/api/v1/leadership/")
  self.assertEqual(response.status_code,200); self.assertEqual(response.data["count"],1)
  seat=response.data["results"][0]
  self.assertEqual(seat["role_title"],"LGA Network Lead")
  self.assertEqual(seat["location"]["lga_name"],"Birnin Kebbi")
  self.assertTrue(seat["holder"]["photo"].startswith("http://testserver/"))
  self.assertNotIn("email",seat["holder"]); self.assertNotIn("phone",seat["holder"])
 def test_lga_all_returns_exactly_ten_constitutional_seats(self):
  response=self.client.get(f"/api/v1/leadership/?tier=LGA&lga={self.lga.id}&status=all&page_size=50")
  self.assertEqual(response.status_code,200); self.assertEqual(response.data["count"],10)
  self.assertEqual(sum(x["status"]=="FILLED" for x in response.data["results"]),1)
  self.assertEqual(len({x["seat_key"] for x in response.data["results"]}),10)
 def test_vacancies_are_bounded_to_location(self):
  self.assertEqual(self.client.get("/api/v1/leadership/?tier=LGA&status=VACANT").status_code,400)
  self.assertEqual(self.client.get("/api/v1/leadership/?tier=WARD&status=VACANT").status_code,400)
  response=self.client.get(f"/api/v1/leadership/?tier=WARD&ward={self.ward.id}&status=VACANT&page_size=50")
  self.assertEqual(response.status_code,200); self.assertEqual(response.data["count"],8)
 def test_cross_location_filter_mismatch_is_rejected(self):
  response=self.client.get(f"/api/v1/leadership/?tier=LGA&zone={self.other_zone.id}&lga={self.lga.id}&status=all")
  self.assertEqual(response.status_code,400)
 def test_page_size_is_capped_at_fifty(self):
  for i in range(6): Ward.objects.create(name=f"Ward {i}",lga=self.lga)
  response=self.client.get(f"/api/v1/leadership/?tier=WARD&lga={self.lga.id}&status=all&page_size=500")
  self.assertEqual(response.status_code,200); self.assertEqual(len(response.data["results"]),50)
  self.assertGreater(response.data["count"],50)
