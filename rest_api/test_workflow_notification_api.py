from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from leadership.models import Zone,LGA,Ward,RoleDefinition
from staff.models import User,WardMeeting,DisciplinaryAction
from events.models import Event,EventAttendance,MeetingMinutes
from donations.models import Donation,Expense
from core.models import Notification
from rest_api.models import DeviceRegistration

class WorkflowNotificationApiTests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.zone=Zone.objects.create(name='Central'); self.lga=LGA.objects.create(name='Birnin',zone=self.zone); self.ward=Ward.objects.create(name='Nassarawa',lga=self.lga)
  self.other_zone=Zone.objects.create(name='North'); self.other_lga=LGA.objects.create(name='Argungu',zone=self.other_zone); self.other_ward=Ward.objects.create(name='Galadima',lga=self.other_lga)
  self.events_role=self.role('Director of Programmes & Events','STATE',11); self.secretary_role=self.role('General Secretary','STATE',3)
  self.ward_role=self.role('Ward Community Lead','WARD',1); self.finance_role=self.role('Director of Finance','STATE',7)
  self.ops_role=self.role('Finance Operations Officer','STATE',8); self.president_role=self.role('President','STATE',1)
  self.state_role=self.role('Director of Monitoring & Compliance','STATE',5)
  self.events_user=self.user('events','STATE',self.events_role); self.secretary=self.user('secretary','STATE',self.secretary_role)
  self.ward_user=self.user('ward','WARD',self.ward_role,self.zone,self.lga,self.ward)
 def role(self,title,tier,seat): return RoleDefinition.objects.create(title=title,tier=tier,seat_number=seat)
 def user(self,name,tier,role,zone=None,lga=None,ward=None,status='VERIFIED'):
  return User.objects.create_user(username=name,password='x',phone='1',role=tier,status=status,role_definition=role,zone=zone,lga=lga,ward=ward)
 def auth(self,user): self.client.force_authenticate(user)
 def test_event_create_attendance_and_minutes_permissions(self):
  self.auth(self.events_user); created=self.client.post('/api/v1/events/',{'title':'Forum','description':'Agenda','location':'Hall','start_date':'2026-11-01T09:00:00Z','end_date':'2026-11-01T11:00:00Z'},format='json')
  self.assertEqual(created.status_code,201); event_id=created.data['id']
  attendee=self.user('member','WARD',self.ward_role,self.zone,self.lga,self.ward)
  attendance=self.client.put(f'/api/v1/events/{event_id}/attendance/',{'records':[{'attendee':attendee.id,'present':True,'notes':'On time'}]},format='json')
  self.assertEqual(attendance.status_code,200); self.assertTrue(EventAttendance.objects.get(event_id=event_id,attendee=attendee).present)
  self.assertEqual(self.client.put(f'/api/v1/events/{event_id}/minutes/',{'content':'Minutes','summary':'Summary','attendees_present':[attendee.id],'is_published':True},format='json').status_code,403)
  self.auth(self.secretary); minutes=self.client.put(f'/api/v1/events/{event_id}/minutes/',{'content':'Minutes','summary':'Summary','attendees_present':[attendee.id],'is_published':True},format='json')
  self.assertEqual(minutes.status_code,200); self.assertIsNotNone(MeetingMinutes.objects.get(event_id=event_id).published_at)
 def test_ward_meeting_ignores_client_scope_and_uses_authenticated_ward(self):
  self.auth(self.ward_user); response=self.client.post('/api/v1/ward-meetings/',{'ward':self.other_ward.id,'title':'Ward meeting','meeting_type':'GENERAL','date':'2026-11-02','location':'Hall'},format='json')
  self.assertEqual(response.status_code,201); self.assertEqual(WardMeeting.objects.get(pk=response.data['id']).ward,self.ward)
 def test_finance_uses_only_real_recorded_values_and_capabilities(self):
  director=self.user('finance','STATE',self.finance_role); ops=self.user('ops','STATE',self.ops_role)
  Donation.objects.create(donor_name='A',amount='100.00',reference='r1',status='RECORDED'); Donation.objects.create(donor_name='B',amount='900.00',reference='r2',status='UNVERIFIED')
  Expense.objects.create(description='Print',amount='35.00',category='OPERATIONS',date='2026-10-01',recorded_by=ops)
  self.auth(director); result=self.client.get('/api/v1/finance/summary/')
  self.assertEqual(result.status_code,200); self.assertEqual(result.data['total_income'],'100'); self.assertEqual(result.data['balance'],'65')
  self.auth(self.ward_user); self.assertEqual(self.client.get('/api/v1/finance/summary/').status_code,403)
 def test_dismissal_is_inactive_without_invalid_user_status(self):
  president=self.user('president','STATE',self.president_role); target=self.user('target','STATE',self.state_role)
  action=DisciplinaryAction.objects.create(user=target,action_type='DISMISSAL',reason='Decision',issued_by=president,legal_reviewed_by=president,legal_opinion='Proceed',legal_approved=True)
  self.auth(president); result=self.client.post(f'/api/v1/discipline/{action.id}/decision/',{'decision':'APPROVE'},format='json')
  self.assertEqual(result.status_code,200); target.refresh_from_db(); self.assertEqual(target.status,'SUSPENDED'); self.assertFalse(target.is_active)
 def test_notification_and_device_ownership(self):
  other=self.user('other','WARD',self.ward_role,self.other_zone,self.other_lga,self.other_ward)
  own=Notification.objects.create(user=self.ward_user,title='Own',message='Visible'); Notification.objects.create(user=other,title='Other',message='Hidden')
  self.auth(self.ward_user); listing=self.client.get('/api/v1/notifications/'); self.assertEqual(listing.data['count'],1)
  self.assertEqual(self.client.post(f'/api/v1/notifications/{own.id}/read/').status_code,204)
  registered=self.client.post('/api/v1/devices/',{'token':'token-a','device_id':'phone','platform':'ANDROID'},format='json'); self.assertEqual(registered.status_code,200)
  device_id=registered.data['id']; self.auth(other); self.assertEqual(self.client.delete(f'/api/v1/devices/{device_id}/').status_code,404)
  self.assertTrue(DeviceRegistration.objects.filter(pk=device_id).exists())
