from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from leadership.models import RoleDefinition,Zone,LGA,Ward
from staff.models import User,Announcement
from staff.forms import AnnouncementForm
from staff.services.announcements import deliver_announcement
from core.models import Notification

class StateAnnouncementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zone=Zone.objects.create(name='State audience test zone');cls.lga=LGA.objects.create(name='State audience test LGA',zone=cls.zone);cls.ward=Ward.objects.create(name='State audience test ward',lga=cls.lga)
        cls.users={}
        for tier,title in [('STATE','President'),('ZONAL','Senatorial Director'),('LGA','LGA Network Lead'),('WARD','Ward Community Lead')]:
            rd=RoleDefinition.objects.create(title=title,tier=tier,seat_number=1)
            cls.users[tier]=User.objects.create_user(username='state_scope_'+tier,phone=tier,status='VERIFIED',role=tier,role_definition=rd,zone=cls.zone,lga=cls.lga,ward=cls.ward)
        cls.general=User.objects.create_user(username='state_scope_general',phone='General',role='GENERAL',status='VERIFIED')
        cls.pending=User.objects.create_user(username='state_scope_pending',phone='Pending',role='STATE',status='PENDING',role_definition=cls.users['STATE'].role_definition)
        cls.inactive=User.objects.create_user(username='state_scope_inactive',phone='Inactive',role='STATE',status='SUSPENDED',is_active=False,role_definition=cls.users['STATE'].role_definition)
        cls.unassigned=User.objects.create_user(username='state_scope_unassigned',phone='Unassigned',role='STATE',status='VERIFIED')

    def publish(self,scope):
        return Announcement.objects.create(title='Local audience test',content='No live broadcast',scope=scope,created_by=self.users['STATE'])

    def test_state_choice_only_available_to_state_senders(self):
        for tier,user in self.users.items():
            choices=dict(AnnouncementForm(user=user).fields['scope'].choices)
            self.assertEqual('STATE' in choices,tier=='STATE')

    def test_state_received_only_by_verified_active_executives(self):
        a=self.publish('STATE')
        for user in [*self.users.values(),self.general,self.pending,self.inactive,self.unassigned]:
            self.assertEqual(Announcement.for_user(user).filter(pk=a.pk).exists(),user.pk==self.users['STATE'].pk,user.username)
        self.assertEqual(a.get_target_display(),'State Executive Team')

    @patch('core.notifications._push')
    def test_state_notification_recipients_and_deduplication(self,push):
        with self.captureOnCommitCallbacks(execute=True):
            a=self.publish('STATE')
        ids=list(Notification.objects.filter(target_type='announcement',target_id=a.pk).values_list('user_id',flat=True))
        self.assertEqual(ids,[self.users['STATE'].pk])
        self.assertEqual(deliver_announcement(a.pk),0)
        self.assertEqual(push.call_count,1)

    def test_general_remains_all_members(self):
        a=self.publish('GENERAL')
        for user in [*self.users.values(),self.general]:self.assertTrue(Announcement.for_user(user).filter(pk=a.pk).exists())
        expected=User.objects.filter(status='VERIFIED',is_active=True).count()
        self.assertEqual(Notification.objects.filter(target_type='announcement',target_id=a.pk).count(),expected)
        self.assertEqual(deliver_announcement(a.pk),0)

    def test_expired_and_inactive_state_messages_do_not_deliver(self):
        for opts in [{'is_active':False},{'expires_at':timezone.now()-timedelta(days=1)}]:
            a=Announcement.objects.create(title='No delivery',content='Local only',scope='STATE',**opts)
            self.assertEqual(deliver_announcement(a.pk),0)
            self.assertFalse(Announcement.for_user(self.users['STATE']).filter(pk=a.pk).exists())

    def test_state_rejects_geographic_targets(self):
        for target in [{'target_zone':self.zone},{'target_lga':self.lga},{'target_ward':self.ward}]:
            with self.assertRaises(ValidationError):Announcement(title='QA',content='Local',scope='STATE',**target).full_clean()

    def test_api_create_edit_permissions_and_received_isolation(self):
        client=APIClient()
        def login(user):client.credentials(HTTP_AUTHORIZATION='Bearer '+str(AccessToken.for_user(user)))
        payload={'title':'Inactive state API test','content':'No live broadcast','scope':'STATE','is_active':False}
        login(self.users['STATE']);response=client.post('/api/v1/announcements/',payload,format='json');self.assertEqual(response.status_code,201);pk=response.data['id']
        for user in [self.users['ZONAL'],self.users['LGA'],self.users['WARD']]:
            login(user);self.assertEqual(client.post('/api/v1/announcements/',payload,format='json').status_code,403)
            self.assertEqual(client.get('/api/v1/announcements/received/').data['count'],0)
        login(self.general);self.assertEqual(client.post('/api/v1/announcements/',payload,format='json').status_code,403)
        login(self.users['STATE']);self.assertEqual(client.patch(f'/api/v1/announcements/{pk}/',{'title':'Revised'},format='json').status_code,200)
        self.assertEqual(client.delete(f'/api/v1/announcements/{pk}/').status_code,204)
