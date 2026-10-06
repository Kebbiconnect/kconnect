from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from leadership.models import Zone,LGA,Ward,RoleDefinition
from staff.models import User

class MemberApiSecurityTests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.zone=Zone.objects.create(name='Central'); self.other_zone=Zone.objects.create(name='North')
  self.lga=LGA.objects.create(name='Birnin Kebbi',zone=self.zone); self.other_lga=LGA.objects.create(name='Argungu',zone=self.other_zone)
  self.ward=Ward.objects.create(name='Nassarawa',lga=self.lga); self.other_ward=Ward.objects.create(name='Galadima',lga=self.other_lga)
  self.lga_role=RoleDefinition.objects.create(title='LGA Adviser',tier='LGA',seat_number=10)
  self.ward_role=RoleDefinition.objects.create(title='Ward Adviser',tier='WARD',seat_number=8)
  self.state_role=RoleDefinition.objects.create(title='Director of Youth Development',tier='STATE',seat_number=15)
  self.president_role=RoleDefinition.objects.create(title='President',tier='STATE',seat_number=1)
  self.vice_role=RoleDefinition.objects.create(title='Vice President',tier='STATE',seat_number=2)
  self.approver=self.user('approver','LGA','VERIFIED',self.lga_role,self.zone,self.lga,self.ward)
 def user(self,name,tier,status,role,zone,lga,ward):
  return User.objects.create_user(username=name,password='x',phone='1',role=tier,status=status,role_definition=role,zone=zone,lga=lga,ward=ward)
 def auth(self,user): self.client.force_authenticate(user)
 def test_member_list_and_detail_are_jurisdiction_scoped(self):
  local=self.user('local','WARD','VERIFIED',self.ward_role,self.zone,self.lga,self.ward)
  remote=self.user('remote','WARD','VERIFIED',self.ward_role,self.other_zone,self.other_lga,self.other_ward)
  self.auth(self.approver); listing=self.client.get('/api/v1/members/')
  ids={x['id'] for x in listing.data['results']}; self.assertIn(local.id,ids); self.assertNotIn(remote.id,ids)
  self.assertEqual(self.client.get(f'/api/v1/members/{remote.id}/').status_code,404)
 def test_pending_includes_under_review_and_approval_sets_canonical_status(self):
  pending=self.user('pending','WARD','UNDER_REVIEW',self.ward_role,self.zone,self.lga,self.ward)
  self.auth(self.approver); listing=self.client.get('/api/v1/members/pending/')
  self.assertIn(pending.id,{x['id'] for x in listing.data['results']})
  response=self.client.post(f'/api/v1/members/{pending.id}/decision/',{'decision':'approve'},format='json')
  self.assertEqual(response.status_code,200); pending.refresh_from_db(); self.assertEqual(pending.status,'VERIFIED'); self.assertEqual(pending.approved_by,self.approver)
 def test_cross_jurisdiction_decision_is_denied(self):
  remote=self.user('remote-pending','WARD','PENDING',self.ward_role,self.other_zone,self.other_lga,self.other_ward)
  self.auth(self.approver); response=self.client.post(f'/api/v1/members/{remote.id}/decision/',{'decision':'approve'},format='json')
  self.assertEqual(response.status_code,403); self.assertEqual(response.data['error']['code'],'outside_jurisdiction')
 def test_lga_cannot_approve_state_applicant(self):
  applicant=self.user('state-app','STATE','PENDING',self.state_role,self.zone,self.lga,self.ward)
  self.auth(self.approver); response=self.client.post(f'/api/v1/members/{applicant.id}/decision/',{'decision':'approve'},format='json')
  self.assertEqual(response.status_code,403); self.assertEqual(response.data['error']['code'],'tier_ceiling')
 def test_only_president_or_vice_president_approves_state_applicant(self):
  other_state=self.user('director','STATE','VERIFIED',self.state_role,self.zone,self.lga,self.ward)
  applicant=self.user('state-app','STATE','PENDING',self.vice_role,self.zone,self.lga,self.ward)
  self.auth(other_state); self.assertEqual(self.client.post(f'/api/v1/members/{applicant.id}/decision/',{'decision':'approve'},format='json').status_code,403)
  president=self.user('president','STATE','VERIFIED',self.president_role,self.zone,self.lga,self.ward)
  self.auth(president); self.assertEqual(self.client.post(f'/api/v1/members/{applicant.id}/decision/',{'decision':'approve'},format='json').status_code,200)
 def test_filled_seat_cannot_be_approved_twice(self):
  self.user('holder','WARD','VERIFIED',self.ward_role,self.zone,self.lga,self.ward)
  applicant=self.user('duplicate','WARD','PENDING',self.ward_role,self.zone,self.lga,self.ward)
  self.auth(self.approver); response=self.client.post(f'/api/v1/members/{applicant.id}/decision/',{'decision':'approve'},format='json')
  self.assertEqual(response.status_code,400); self.assertIn('already filled',response.data['error']['message'])
 def test_reject_matches_website_delete_policy(self):
  applicant=self.user('reject-me','WARD','PENDING',self.ward_role,self.zone,self.lga,self.ward)
  self.auth(self.approver); response=self.client.post(f'/api/v1/members/{applicant.id}/decision/',{'decision':'reject'},format='json')
  self.assertEqual(response.status_code,200); self.assertEqual(response.data['status'],'REJECTED'); self.assertFalse(User.objects.filter(pk=applicant.id).exists())
 @override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
 def test_website_queue_uses_same_scope_and_under_review_rule(self):
  local=self.user('web-local','WARD','UNDER_REVIEW',self.ward_role,self.zone,self.lga,self.ward)
  self.user('web-remote','WARD','PENDING',self.ward_role,self.other_zone,self.other_lga,self.other_ward)
  self.client.force_login(self.approver); response=self.client.get('/account/approve-members/')
  self.assertEqual(response.status_code,200); self.assertEqual(list(response.context['pending_users']),[local])
