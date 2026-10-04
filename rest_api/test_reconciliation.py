from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from leadership.models import Zone,LGA,Ward,RoleDefinition
from staff.models import User, Announcement
from core.models import Report,DeviceRegistration,Notification
from core.notifications import announcement_recipients, notify_many
from campaigns.models import Campaign
from events.models import Event, EventAttendance
from media.models import MediaItem
from django.core.files.uploadedfile import SimpleUploadedFile

class ReconciliationAPITests(APITestCase):
 @classmethod
 def setUpTestData(cls):
  cls.z1=Zone.objects.create(name='Zone A'); cls.z2=Zone.objects.create(name='Zone B')
  cls.l1=LGA.objects.create(name='LGA A',zone=cls.z1); cls.l2=LGA.objects.create(name='LGA B',zone=cls.z2)
  cls.w1=Ward.objects.create(name='Ward A',lga=cls.l1); cls.w2=Ward.objects.create(name='Ward B',lga=cls.l2)
  cls.state_role=RoleDefinition.objects.create(title='President',tier='STATE',seat_number=1)
  cls.lga_role=RoleDefinition.objects.create(title='LGA Network Lead',tier='LGA',seat_number=1)
  cls.ward_role=RoleDefinition.objects.create(title='Ward Community Lead',tier='WARD',seat_number=1)
  cls.editor_role=RoleDefinition.objects.create(title='Director of Media & Communications',tier='STATE',seat_number=2)
  cls.events_role=RoleDefinition.objects.create(title='Director of Programmes & Events',tier='STATE',seat_number=3)
  cls.comms_role=RoleDefinition.objects.create(title='LGA Communications Officer',tier='LGA',seat_number=2)
  cls.president=User.objects.create_user('president',password='secret1',status='VERIFIED',role='STATE',role_definition=cls.state_role,lga=cls.l1,zone=cls.z1,phone='1')
  cls.lga=User.objects.create_user('lga',password='secret1',status='VERIFIED',role='LGA',role_definition=cls.lga_role,lga=cls.l1,zone=cls.z1,phone='2')
  cls.lga2=User.objects.create_user('lga2',password='secret1',status='VERIFIED',role='LGA',role_definition=cls.lga_role,lga=cls.l2,zone=cls.z2,phone='3')
  cls.ward=User.objects.create_user('ward',password='secret1',status='VERIFIED',role='WARD',role_definition=cls.ward_role,ward=cls.w1,lga=cls.l1,zone=cls.z1,phone='4')
  cls.app1=User.objects.create_user('app1',password='secret1',status='PENDING',role='WARD',role_definition=cls.ward_role,ward=cls.w1,lga=cls.l1,zone=cls.z1,phone='5')
  cls.app2=User.objects.create_user('app2',password='secret1',status='PENDING',role='WARD',role_definition=cls.ward_role,ward=cls.w2,lga=cls.l2,zone=cls.z2,phone='6')
  cls.editor=User.objects.create_user('editor',password='secret1',status='VERIFIED',role='STATE',role_definition=cls.editor_role,phone='7')
  cls.events_manager=User.objects.create_user('events_manager',password='secret1',status='VERIFIED',role='STATE',role_definition=cls.events_role,phone='8')
  cls.comms=User.objects.create_user('comms',password='secret1',status='VERIFIED',role='LGA',role_definition=cls.comms_role,zone=cls.z1,lga=cls.l1,phone='9')
 def auth(self,user): self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
 def test_login_refresh_and_unauthorized(self):
  self.assertEqual(self.client.get('/api/v1/members/').status_code,401)
  r=self.client.post('/api/v1/auth/login/',{'username':'lga','password':'secret1'}); self.assertEqual(r.status_code,200); self.assertIn('refresh',r.data)
  self.assertEqual(self.client.post('/api/v1/auth/login/',{'username':'lga','password':'wrong'}).status_code,401)
  self.assertEqual(self.client.post('/api/v1/auth/refresh/',{'refresh':r.data['refresh']}).status_code,200)
 def test_jurisdiction_blocks_cross_lga_member(self):
  self.auth(self.lga)
  ids={row['id'] for row in self.client.get('/api/v1/members/pending/').data['results']}; self.assertIn(self.app1.id,ids); self.assertNotIn(self.app2.id,ids)
  self.assertEqual(self.client.get(f'/api/v1/members/{self.app2.id}/').status_code,404)
 def test_membership_approve_and_reject_preserve_record(self):
  self.auth(self.lga)
  self.assertEqual(self.client.post(f'/api/v1/members/{self.app1.id}/decision/',{'decision':'approve'}).status_code,200)
  self.app1.refresh_from_db(); self.assertEqual(self.app1.status,'VERIFIED')
  self.auth(self.lga2); self.assertEqual(self.client.post(f'/api/v1/members/{self.app2.id}/decision/',{'decision':'reject'}).status_code,200)
  self.app2.refresh_from_db(); self.assertEqual(self.app2.status,'REJECTED')
 def test_report_submission_review_and_escalation(self):
  self.auth(self.ward); r=self.client.post('/api/v1/reports/',{'title':'Ward report','content':'Facts','period':'October'}); self.assertEqual(r.status_code,201,r.data)
  report=Report.objects.get(pk=r.data['id']); self.assertEqual(report.submitted_to,self.lga); self.assertEqual(report.status,'SUBMITTED')
  self.auth(self.lga); r=self.client.post(f'/api/v1/reports/{report.id}/review/',{'action':'approve','notes':'Checked'}); self.assertEqual(r.status_code,200,r.data)
  self.assertEqual(self.client.post(f'/api/v1/reports/{report.id}/escalate/').status_code,400) # no configured Senatorial Director
 def test_newsroom_draft_submit_publish(self):
  self.auth(self.lga); r=self.client.post('/api/v1/articles/mine/',{'title':'Local update','content':'Verified source material','category':'COMMUNITY'}); self.assertEqual(r.status_code,201,r.data)
  article=Campaign.objects.get(pk=r.data['id']); self.assertEqual(self.client.post(f'/api/v1/articles/{article.id}/submit/').status_code,200)
  self.auth(self.editor); self.assertEqual(self.client.post(f'/api/v1/articles/{article.id}/decision/',{'decision':'publish'}).status_code,200)
  article.refresh_from_db(); self.assertEqual(article.status,'PUBLISHED')
 def test_device_registration_and_notification_read(self):
  self.auth(self.lga); r=self.client.post('/api/v1/devices/',{'token':'token-1','device_id':'phone'}); self.assertEqual(r.status_code,200); self.assertEqual(DeviceRegistration.objects.filter(user=self.lga,is_active=True).count(),1)
  n=Notification.objects.create(user=self.lga,title='Test',message='Body')
  self.assertEqual(self.client.post(f'/api/v1/notifications/{n.id}/read/').status_code,204); n.refresh_from_db(); self.assertTrue(n.is_read)
 def test_announcement_targeting_and_mark_all_read(self):
  ann=Announcement.objects.create(title='LGA notice',content='Scoped',scope='LGA',target_lga=self.l1,created_by=self.lga)
  recipients=announcement_recipients(ann); self.assertIn(self.lga,recipients); self.assertIn(self.ward,recipients); self.assertNotIn(self.lga2,recipients)
  notify_many(recipients,title=ann.title,message=ann.content,event='ANNOUNCEMENT_CREATED')
  self.auth(self.lga); self.assertEqual(self.client.post('/api/v1/notifications/read-all/').status_code,204); self.assertFalse(Notification.objects.filter(user=self.lga,is_read=False).exists())
 def test_cross_jurisdiction_applicant_decision_is_not_found(self):
  self.auth(self.lga); self.assertEqual(self.client.post(f'/api/v1/members/{self.app2.id}/decision/',{'decision':'approve'}).status_code,404)
 def test_event_create_update_and_attendance(self):
  self.auth(self.events_manager)
  r=self.client.post('/api/v1/events/',{'title':'KPN Meeting','description':'Agenda','location':'Secretariat','start_date':'2026-10-10T09:00:00+01:00','end_date':'2026-10-10T10:00:00+01:00'}); self.assertEqual(r.status_code,201,r.data)
  event=Event.objects.get(pk=r.data['id'])
  self.assertEqual(self.client.patch(f'/api/v1/events/{event.id}/',{'location':'Main Hall'}).status_code,200)
  r=self.client.put(f'/api/v1/events/{event.id}/attendance/',{'records':[{'attendee':self.lga.id,'present':True}]},format='json'); self.assertEqual(r.status_code,200,r.data); self.assertTrue(EventAttendance.objects.filter(event=event,attendee=self.lga,present=True).exists())
 def test_media_permission_and_director_review(self):
  self.auth(self.lga); self.assertEqual(self.client.get('/api/v1/media/mine/').status_code,403)
  item=MediaItem.objects.create(title='Field photo',description='Evidence',media_type='PHOTO',file=SimpleUploadedFile('evidence.jpg',b'bytes',content_type='image/jpeg'),uploaded_by=self.comms,status='PENDING')
  self.auth(self.editor); r=self.client.post(f'/api/v1/media/{item.id}/decision/',{'decision':'approve'}); self.assertEqual(r.status_code,200,r.data); item.refresh_from_db(); self.assertEqual(item.status,'APPROVED')

