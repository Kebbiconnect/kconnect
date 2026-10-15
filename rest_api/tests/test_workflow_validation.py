"""Isolated successful actions and malformed-input regressions (no provider calls)."""
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from leadership.models import RoleDefinition
from staff.models import User, DisciplinaryAction
from campaigns.models import Campaign
from media.models import MediaItem
from events.models import Event, EventAttendance, MeetingMinutes

class WorkflowValidationTests(TestCase):
    def setUp(self):
        role,_=RoleDefinition.objects.get_or_create(tier='STATE',title='Director of Media & Communications',defaults={'seat_number':14})
        self.actor=User.objects.create_user(username='isolated_workflow_actor',password='test-only',role='STATE',status='VERIFIED',role_definition=role,phone='isolated-actor')
        self.target=User.objects.create_user(username='isolated_workflow_target',password='test-only',role='GENERAL',status='VERIFIED',phone='isolated-target')
        self.client=APIClient();self.client.force_authenticate(self.actor)
    def pending_article(self):
        return Campaign.objects.create(title='Isolated editorial fixture',slug='isolated-editorial-fixture',content='Isolated content',status='PENDING',author=self.target)
    def test_article_publish_success(self):
        a=self.pending_article();r=self.client.post(f'/api/v1/articles/{a.pk}/decision/',{'action':'publish'},format='json')
        self.assertEqual(r.status_code,200,r.data);a.refresh_from_db();self.assertEqual(a.status,'PUBLISHED');self.assertEqual(a.approved_by,self.actor)
    def test_article_return_success(self):
        a=self.pending_article();r=self.client.post(f'/api/v1/articles/{a.pk}/decision/',{'action':'return','note':'Please add context.'},format='json')
        self.assertEqual(r.status_code,200,r.data);a.refresh_from_db();self.assertEqual(a.status,'REJECTED');self.assertEqual(a.rejection_note,'Please add context.')
    def test_article_structured_action_and_note_are_rejected(self):
        a=self.pending_article()
        for payload in ({'action':[]},{'action':{}},{'action':'return','note':{}},{'action':'return','note':[]}):
            with self.subTest(payload=payload):self.assertEqual(self.client.post(f'/api/v1/articles/{a.pk}/decision/',payload,format='json').status_code,400)
        a.refresh_from_db();self.assertEqual(a.status,'PENDING')
    def test_media_approval_success(self):
        m=MediaItem.objects.create(title='Isolated media fixture',media_type='PHOTO',file='isolated/not-a-real-upload.jpg',uploaded_by=self.target)
        self.assertEqual(self.client.post(f'/api/v1/media/{m.pk}/decision/',{'action':'approve'},format='json').status_code,200)
        m.refresh_from_db();self.assertEqual(m.status,'APPROVED');self.assertEqual(m.approved_by,self.actor)
    def test_media_structured_action_is_rejected(self):
        m=MediaItem.objects.create(title='Isolated media fixture',media_type='PHOTO',file='isolated/not-a-real-upload.jpg',uploaded_by=self.target)
        for value in (None,[],{}):self.assertEqual(self.client.post(f'/api/v1/media/{m.pk}/decision/',{'action':value},format='json').status_code,400)
    def test_member_decision_invalid_values_return_400(self):
        for value in (None,[],{},'unknown'):
            self.assertEqual(self.client.post('/api/v1/members/999999/decision/',{'decision':value},format='json').status_code,400)
    def test_json_top_level_array_is_rejected(self):
        self.assertEqual(self.client.post('/api/v1/members/999999/decision/',[],format='json').status_code,400)
    def test_legal_false_string_does_not_grant_approval(self):
        a=DisciplinaryAction.objects.create(user=self.target,issued_by=self.actor,action_type='DISMISSAL',reason='Isolated legal fixture')
        r=self.client.post(f'/api/v1/discipline/{a.pk}/legal-opinion/',{'legal_opinion':'Not approved.','legal_approved':'false'},format='json')
        self.assertEqual(r.status_code,200,r.data);a.refresh_from_db();self.assertFalse(a.legal_approved)
    def test_legal_true_boolean_grants_review_only(self):
        a=DisciplinaryAction.objects.create(user=self.target,issued_by=self.actor,action_type='DISMISSAL',reason='Isolated legal fixture')
        r=self.client.post(f'/api/v1/discipline/{a.pk}/legal-opinion/',{'legal_opinion':'Approved for review.','legal_approved':True},format='json')
        self.assertEqual(r.status_code,200,r.data);a.refresh_from_db();self.assertTrue(a.legal_approved);self.assertFalse(a.is_approved)
    def test_attendance_and_minutes_success(self):
        now=timezone.now();e=Event.objects.create(title='Isolated event',description='Test fixture',location='Isolated',start_date=now,end_date=now+timedelta(hours=1),created_by=self.actor)
        r=self.client.put(f'/api/v1/events/{e.pk}/attendance/',{'records':[{'attendee':self.target.pk,'present':True,'notes':'Isolated'}]},format='json')
        self.assertEqual(r.status_code,200,r.data);self.assertTrue(EventAttendance.objects.get(event=e,attendee=self.target).present)
        r=self.client.put(f'/api/v1/events/{e.pk}/minutes/',{'content':'Isolated minutes','summary':'Isolated summary','attendees_present':[self.target.pk],'is_published':True},format='json')
        self.assertEqual(r.status_code,200,r.data);self.assertIsNotNone(MeetingMinutes.objects.get(event=e).published_at)
    def test_attendance_malformed_records_return_400(self):
        now=timezone.now();e=Event.objects.create(title='Isolated event',description='Test',location='Isolated',start_date=now,end_date=now+timedelta(hours=1),created_by=self.actor)
        for records in (None,{},[{}],[{'attendee':[]} ]):
            self.assertEqual(self.client.put(f'/api/v1/events/{e.pk}/attendance/',{'records':records},format='json').status_code,400)
    def test_invalid_location_filters_return_400(self):
        for path,keys in (('/api/v1/locations/lgas/',('zone',)),('/api/v1/locations/wards/',('lga',)),('/api/v1/leadership/',('zone','lga','ward')),('/api/v1/registration/vacant-roles/',('zone','lga','ward'))):
            for key in keys:
                with self.subTest(path=path,key=key):self.assertEqual(self.client.get(path,{key:'not-an-id'}).status_code,400)
    def test_contact_valid_input_delivers_to_local_mailbox(self):
        from django.core import mail
        self.client.force_authenticate(user=None)
        r=self.client.post('/api/v1/content/contact/',{'name':'Isolated test sender','email':'isolated@example.invalid','message':'Synthetic local-only contact check.'},format='json')
        self.assertEqual(r.status_code,201,r.data);self.assertEqual(len(mail.outbox),1)
    def test_contact_invalid_email_and_header_input_are_rejected(self):
        self.client.force_authenticate(user=None)
        for fields in ({'name':None,'email':'isolated@example.invalid','message':'Test'},{'name':'Test','email':'not-an-email','message':'Test'},{'name':'Test\nBad','email':'isolated@example.invalid','message':'Test'},{'name':'Test','email':{},'message':[]}):
            self.assertEqual(self.client.post('/api/v1/content/contact/',fields,format='json').status_code,400)
