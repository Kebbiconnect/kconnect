from django.test import TestCase
from rest_framework.test import APIClient
from leadership.models import Zone,LGA,Ward,RoleDefinition
from staff.models import User
from core.models import Report

class ReportWorkflowApiTests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.zone=Zone.objects.create(name='Central'); self.other_zone=Zone.objects.create(name='North')
  self.lga=LGA.objects.create(name='Birnin Kebbi',zone=self.zone); self.other_lga=LGA.objects.create(name='Argungu',zone=self.other_zone)
  self.ward=Ward.objects.create(name='Nassarawa',lga=self.lga)
  roles={}
  for tier,title,n in [('WARD','Ward Adviser',8),('LGA','LGA Network Lead',1),('ZONAL','Senatorial Director',1),('STATE','Director of Monitoring & Compliance',5),('STATE','Director of Youth Development',15)]:
   roles[title]=RoleDefinition.objects.create(title=title,tier=tier,seat_number=n)
  self.ward_user=self.user('ward','WARD',roles['Ward Adviser'],zone=self.zone,lga=self.lga,ward=self.ward)
  self.lga_lead=self.user('lga','LGA',roles['LGA Network Lead'],zone=self.zone,lga=self.lga)
  self.zonal=self.user('zonal','ZONAL',roles['Senatorial Director'],zone=self.zone)
  self.monitor=self.user('monitor','STATE',roles['Director of Monitoring & Compliance'])
  self.unrelated_state=self.user('youth','STATE',roles['Director of Youth Development'])
 def user(self,name,tier,role,**scope): return User.objects.create_user(username=name,password='x',phone='1',role=tier,status='VERIFIED',role_definition=role,**scope)
 def auth(self,user): self.client.force_authenticate(user)
 def test_recipient_preview_and_submission_are_server_derived(self):
  self.auth(self.ward_user); preview=self.client.get('/api/v1/reports/recipient/')
  self.assertEqual(preview.status_code,200); self.assertEqual(preview.data['recipient']['id'],self.lga_lead.id)
  response=self.client.post('/api/v1/reports/',{'title':'Ward report','content':'Operational facts','period':'October'},format='json')
  self.assertEqual(response.status_code,201); report=Report.objects.get(pk=response.data['id'])
  self.assertEqual(report.report_type,'WARD_TO_LGA'); self.assertEqual(report.submitted_to,self.lga_lead); self.assertEqual(report.status,'SUBMITTED')
 def test_cross_jurisdiction_report_is_not_visible(self):
  self.auth(self.ward_user); created=self.client.post('/api/v1/reports/',{'title':'Scoped','content':'Facts'},format='json').data
  remote_role=RoleDefinition.objects.get(title='LGA Network Lead')
  remote=self.user('remote','LGA',remote_role,zone=self.other_zone,lga=self.other_lga)
  self.auth(remote); self.assertEqual(self.client.get(f"/api/v1/reports/{created['id']}/").status_code,404)
 def test_review_requires_notes_for_flag_or_reject(self):
  self.auth(self.ward_user); report_id=self.client.post('/api/v1/reports/',{'title':'Needs review','content':'Facts'},format='json').data['id']
  self.auth(self.lga_lead); response=self.client.post(f'/api/v1/reports/{report_id}/review/',{'action':'flag','notes':''},format='json')
  self.assertEqual(response.status_code,400); self.assertIn('notes',response.data['error']['details']['fields'])
 def test_approval_uses_approved_then_escalates_to_verified_zonal_director(self):
  self.auth(self.ward_user); report_id=self.client.post('/api/v1/reports/',{'title':'Ward review','content':'Facts','period':'Q4'},format='json').data['id']
  self.auth(self.lga_lead); response=self.client.post(f'/api/v1/reports/{report_id}/review/',{'action':'approved','notes':'Accepted'},format='json')
  self.assertEqual(response.status_code,200); original=Report.objects.get(pk=report_id)
  self.assertEqual(original.status,'ESCALATED'); self.assertTrue(original.is_escalated)
  child=Report.objects.get(parent_report=original); self.assertEqual(child.status,'SUBMITTED'); self.assertEqual(child.submitted_to,self.zonal)
  self.assertEqual(response.data['escalated_report']['id'],child.id)
 def test_non_report_state_role_has_no_report_access(self):
  self.auth(self.unrelated_state); self.assertEqual(self.client.get('/api/v1/reports/').status_code,403)
 def test_monitoring_director_can_see_state_report_but_other_state_role_cannot(self):
  report=Report.objects.create(title='State report',content='Facts',report_type='ZONAL_TO_STATE',submitted_by=self.zonal,submitted_to=self.monitor,status='SUBMITTED')
  self.auth(self.monitor); self.assertEqual(self.client.get(f'/api/v1/reports/{report.id}/').status_code,200)
  self.auth(self.unrelated_state); self.assertEqual(self.client.get(f'/api/v1/reports/{report.id}/').status_code,403)
 def test_no_report_workflow_queries_invalid_verified_status(self):
  valid={choice for choice,_ in Report.STATUS_CHOICES}; self.assertIn('APPROVED',valid); self.assertNotIn('VERIFIED',valid)
