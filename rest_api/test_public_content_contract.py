from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from campaigns.models import Campaign
from core.models import Opportunity,CommunityInitiative,AdvocacyCampaign,Patron
from leadership.models import Zone,LGA,Ward
from staff.models import User

class PublicContentContractTests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.zone=Zone.objects.create(name="Central")
  self.lga=LGA.objects.create(name="Birnin Kebbi",zone=self.zone); self.ward=Ward.objects.create(name="Nassarawa",lga=self.lga)
  self.author=User.objects.create_user(username="writer",password="x",phone="1",first_name="KPN",last_name="Writer")
  self.article=Campaign.objects.create(title="Civic update",slug="civic-update",subheadline="Verified community news",content="one two three",category="CIVIC",location="Birnin Kebbi",lga=self.lga,ward=self.ward,verification_status="VERIFIED",reporter_credit="KPN_EDITORIAL",author=self.author,status="PUBLISHED",published_at=timezone.now())
  self.open=Opportunity.objects.create(title="Open grant",slug="open-grant",category="GRANT",provider="KPN Partner",description="Real opportunity",requirements="Eligible youth",benefits="Training",application_link="https://example.com/apply",status="OPEN")
  self.closed=Opportunity.objects.create(title="Old grant",slug="old-grant",category="GRANT",provider="Partner",description="Historic",status="CLOSED")
  self.initiative=CommunityInitiative.objects.create(title="Clean up",category="VOLUNTEER",status="ACTIVE",description="Community clean up",location_text="Central Market",people_reached=12)
  self.active_advocacy=AdvocacyCampaign.objects.create(title="Active voice",issue="Issue",background="Context",is_active=True)
  AdvocacyCampaign.objects.create(title="Inactive voice",issue="Issue",background="Context",is_active=False)
  self.grand=Patron.objects.create(patron_type="GRAND",full_name="Grand Patron",title="Grand Patron",order=9,is_published=True)
  Patron.objects.create(patron_type="PATRON",full_name="Regular Patron",title="Patron",order=0,is_published=True)
  Patron.objects.create(patron_type="PATRON",full_name="Hidden Patron",title="Patron",is_published=False)
 def test_newsroom_exposes_source_backed_mobile_fields_and_filters(self):
  response=self.client.get("/api/v1/newsroom/?category=CIVIC&q=verified")
  self.assertEqual(response.status_code,200); self.assertEqual(response.data["count"],1)
  article=response.data["results"][0]
  for field in ("category_label","location","lga_name","ward_name","verification_status_label","reporter_credit","author_name","views","read_time","content_json"):
   self.assertIn(field,article)
  self.assertEqual(article["author_name"],"KPN Writer")
 def test_opportunities_default_matches_website_active_feed_and_all_is_explicit(self):
  response=self.client.get("/api/v1/opportunities/")
  self.assertEqual(response.data["count"],1); self.assertEqual(response.data["results"][0]["slug"],"open-grant")
  self.assertEqual(self.client.get("/api/v1/opportunities/?status=all").data["count"],2)
  detail=self.client.get("/api/v1/opportunities/open-grant/")
  self.assertEqual(detail.status_code,200); self.assertEqual(detail.data["requirements"],"Eligible youth")
 def test_community_list_and_detail_include_real_impact_fields(self):
  listing=self.client.get("/api/v1/community/")
  self.assertEqual(listing.data["results"][0]["people_reached"],12)
  detail=self.client.get(f"/api/v1/community/{self.initiative.id}/")
  self.assertEqual(detail.data["location_text"],"Central Market")
 def test_advocacy_exposes_only_active_public_records(self):
  listing=self.client.get("/api/v1/advocacy/")
  self.assertEqual(listing.data["count"],1)
  self.assertEqual(self.client.get(f"/api/v1/advocacy/{self.active_advocacy.id}/").status_code,200)
 def test_patrons_are_published_only_and_grand_patron_first(self):
  response=self.client.get("/api/v1/patrons/")
  self.assertEqual(response.data["count"],2)
  self.assertEqual(response.data["results"][0]["patron_type"],"GRAND")
  self.assertEqual(response.data["results"][0]["patron_type_label"],"Grand Patron")
