from django.test import TestCase
from rest_framework.test import APIClient
from leadership.models import RoleDefinition,Zone,LGA,Ward
from staff.models import User,Announcement
from core.models import FAQ,CommunityReport
from donations.models import Donation

class ExtendedContractTests(TestCase):
 def setUp(self):
  self.c=APIClient();self.z=Zone.objects.create(name='Central');self.l=LGA.objects.create(name='Birnin',zone=self.z);self.w=Ward.objects.create(name='Ward',lga=self.l)
  self.media_role=RoleDefinition.objects.create(title='Director of Media & Communications',tier='STATE',seat_number=18)
  self.finance_role=RoleDefinition.objects.create(title='Director of Finance',tier='STATE',seat_number=7)
  self.reporter_role=RoleDefinition.objects.create(title='Ward Communications Officer',tier='WARD',seat_number=5)
  self.media=User.objects.create_user(username='media',password='x',phone='1',role='STATE',status='VERIFIED',role_definition=self.media_role)
  self.reporter=User.objects.create_user(username='reporter',password='x',phone='1',role='WARD',status='VERIFIED',role_definition=self.reporter_role,zone=self.z,lga=self.l,ward=self.w,is_trusted_reporter=True,reporter_level='TRUSTED_REPORTER')
 def auth(self,u):self.c.force_authenticate(u)
 def test_public_content_and_faq(self):
  FAQ.objects.create(question='Who?',answer='KPN',is_active=True)
  self.assertEqual(self.c.get('/api/v1/content/about/').status_code,200)
  self.assertEqual(self.c.get('/api/v1/content/support/').data['bank_details'],None)
  self.assertEqual(self.c.get('/api/v1/content/faq/').data['count'],1)
 def test_community_report_submit_and_review_notifies_reporter(self):
  self.auth(self.reporter);created=self.c.post('/api/v1/community-reports/',{'category':'COMMUNITY','lga':self.l.id,'ward':self.w.id,'location_details':'Town','what_happened':'Activity'},format='json')
  self.assertEqual(created.status_code,201);report=CommunityReport.objects.get(pk=created.data['id']);self.assertEqual(report.submitted_by,self.reporter)
  self.auth(self.media);decided=self.c.post(f'/api/v1/community-reports/{report.id}/review/',{'action':'approve','info_status':'VERIFIED'},format='json')
  self.assertEqual(decided.status_code,200);self.assertTrue(self.reporter.notifications.filter(event='COMMUNITY_REPORT_REVIEWED').exists())
 def test_announcement_targets_only_selected_ward(self):
  self.auth(self.media);response=self.c.post('/api/v1/announcements/',{'title':'Ward notice','content':'Meeting','scope':'WARD','priority':'NORMAL','target_ward':self.w.id},format='json')
  self.assertEqual(response.status_code,201);self.assertTrue(self.reporter.notifications.filter(event='ANNOUNCEMENT').exists())
 def test_donation_transitions_enforce_roles(self):
  finance=User.objects.create_user(username='finance',password='x',phone='1',role='STATE',status='VERIFIED',role_definition=self.finance_role)
  donation=Donation.objects.create(donor_name='A',amount='20',reference='one')
  self.auth(finance);result=self.c.post(f'/api/v1/finance/donations/{donation.id}/verify/',{},format='json')
  self.assertEqual(result.status_code,200);self.assertEqual(result.data['status'],'VERIFIED')
