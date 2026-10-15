from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from leadership.models import RoleDefinition, Zone, LGA, Ward
from leadership.capabilities import capabilities_for, ALL_CAPABILITIES
from staff.models import User
from staff.services.member_admin import decide_application, MemberDecisionError
from staff.services.assignments import assign_member, swap_members, validate_location
from campaigns.models import Campaign

class Fixtures:
    def seed(self):
        self.zone=Zone.objects.create(name='Synthetic zone')
        self.lga=LGA.objects.create(name='Synthetic LGA',zone=self.zone)
        self.ward=Ward.objects.create(name='Synthetic ward',lga=self.lga)
        self.president_role=RoleDefinition.objects.create(title='President',tier='STATE',seat_number=1)
        self.media_role=RoleDefinition.objects.create(title='Director of Media & Communications',tier='STATE',seat_number=18)
        self.destination=RoleDefinition.objects.create(title='LGA Network Lead',tier='LGA',seat_number=1)
        self.approver=User.objects.create_user(username='synthetic_president',phone='s1',role='STATE',status='VERIFIED',role_definition=self.president_role)
    def applicant(self,username='synthetic_applicant',definition=None):
        definition=definition or self.destination
        return User.objects.create_user(username=username,password='SyntheticPass123!',phone=username[:20],role=definition.tier,status='PENDING',role_definition=definition,zone=self.zone,lga=self.lga,ward=self.ward)

class ReleaseRuleTests(Fixtures, TestCase):
    def setUp(self): self.seed()
    def test_rejection_archives_preserves_foreign_keys_and_audit_actor(self):
        applicant=self.applicant()
        article=Campaign.objects.create(title='Synthetic authored record',slug='synthetic-authored',content='Synthetic',author=applicant)
        decide_application(self.approver,applicant.pk,'reject','Synthetic review reason')
        applicant.refresh_from_db();article.refresh_from_db()
        self.assertEqual(applicant.status,'REJECTED');self.assertFalse(applicant.is_active)
        self.assertIsNotNone(applicant.archived_at);self.assertEqual(applicant.archived_by_id,self.approver.pk)
        self.assertEqual(applicant.archive_reason,'Synthetic review reason');self.assertEqual(article.author_id,applicant.pk)
    def test_archived_jwt_is_denied(self):
        applicant=self.applicant();token=str(AccessToken.for_user(applicant))
        decide_application(self.approver,applicant.pk,'reject')
        client=APIClient();client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(client.get('/api/v1/auth/me/').status_code,401)
    def test_archived_application_cannot_be_approved_as_pending(self):
        applicant=self.applicant();decide_application(self.approver,applicant.pk,'reject')
        with self.assertRaises(MemberDecisionError):decide_application(self.approver,applicant.pk,'approve')
    def test_media_director_gets_all_confirmed_capabilities(self):
        media=User.objects.create_user(username='synthetic_media',phone='s2',role='STATE',status='VERIFIED',role_definition=self.media_role)
        self.assertEqual(capabilities_for(media),tuple(cap for cap in ALL_CAPABILITIES if cap != "SUBMIT_REPORTS"))
        applicant=self.applicant('synthetic_state',RoleDefinition.objects.create(title='General Secretary',tier='STATE',seat_number=3))
        decide_application(media,applicant.pk,'approve');applicant.refresh_from_db()
        self.assertEqual(applicant.status,'VERIFIED')
    def test_pending_media_director_has_no_management_access(self):
        media=self.applicant('synthetic_pending_media',self.media_role)
        self.assertEqual(capabilities_for(media),())
    def test_database_prevents_duplicate_verified_seat(self):
        first=self.applicant('synthetic_first');decide_application(self.approver,first.pk,'approve')
        second=self.applicant('synthetic_second')
        with self.assertRaises(IntegrityError),transaction.atomic():
            User.objects.filter(pk=second.pk).update(status='VERIFIED')
    def test_other_lga_has_independent_seat(self):
        first=self.applicant('synthetic_first');decide_application(self.approver,first.pk,'approve')
        second=self.applicant('synthetic_second');second.lga=LGA.objects.create(name='Synthetic other LGA',zone=self.zone);second.ward=None;second.save()
        decide_application(self.approver,second.pk,'approve');second.refresh_from_db();self.assertEqual(second.status,'VERIFIED')
    def test_swapping_occupied_seats_is_atomic_with_unique_indexes(self):
        first=self.applicant('synthetic_first');decide_application(self.approver,first.pk,'approve')
        other_role=RoleDefinition.objects.create(title='LGA Communications Officer',tier='LGA',seat_number=2)
        second=self.applicant('synthetic_second',other_role);decide_application(self.approver,second.pk,'approve')
        swap_members(first.pk,second.pk);first.refresh_from_db();second.refresh_from_db()
        self.assertEqual(first.role_definition_id,other_role.pk);self.assertEqual(second.role_definition_id,self.destination.pk)
        self.assertEqual(first.status,'VERIFIED');self.assertEqual(second.status,'VERIFIED')
    def test_reinstatement_cannot_take_an_occupied_seat(self):
        first=self.applicant('synthetic_first');decide_application(self.approver,first.pk,'approve')
        second=self.applicant('synthetic_second');second.status='SUSPENDED';second.save()
        with self.assertRaises(ValidationError):assign_member(second.pk,self.destination,self.zone,self.lga,self.ward,verified=True,approver=self.approver)
    def test_registration_rejects_mismatched_location_and_general_signup(self):
        other=Zone.objects.create(name='Synthetic other zone')
        with self.assertRaises(ValidationError):validate_location(self.destination,other,self.lga,self.ward,registration=True)
        with self.assertRaises(ValidationError):validate_location(None,self.zone,self.lga,registration=True)
    def test_password_reset_null_is_validation_not_server_error(self):
        client=APIClient();response=client.post('/api/v1/auth/password-reset/confirm/',{'uid':'bad','token':'bad','new_password':None},format='json')
        self.assertEqual(response.status_code,400)
    def test_readiness_is_minimal_and_reports_database_failure(self):
        self.assertEqual(self.client.get('/health/ready/').json(),{'status':'ready'})
        with patch('core.health.connection.cursor',side_effect=RuntimeError('Synthetic private marker')):
            response=self.client.get('/health/ready/')
        self.assertEqual(response.status_code,503);self.assertNotContains(response,'Synthetic private marker',status_code=503)

class ApprovalConcurrencyTests(Fixtures, TransactionTestCase):
    def setUp(self):self.seed()
    def test_two_postgresql_approvals_cannot_fill_one_seat_twice(self):
        if connection.vendor!='postgresql':self.skipTest('Requires PostgreSQL row locking.')
        first=self.applicant('synthetic_race_one');second=self.applicant('synthetic_race_two')
        barrier=Barrier(2)
        def approve(pk):
            try:
                approver=User.objects.get(pk=self.approver.pk)
                barrier.wait(timeout=10)
                decide_application(approver,pk,'approve')
                return 'approved'
            except MemberDecisionError as exc:return exc.code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(approve,[first.pk,second.pk]))
        self.assertCountEqual(outcomes,['approved','seat_filled'])
        self.assertEqual(User.objects.filter(role_definition=self.destination,lga=self.lga,status='VERIFIED').count(),1)

class StaffStatusDisplayTests(Fixtures, TestCase):
    def setUp(self):self.seed()
    def render_listing(self,member):
        from django.template.loader import render_to_string
        return render_to_string('staff/manage_staff.html',{'staff':[member],'user':self.approver,'zones':[]})
    def test_verified_member_is_not_displayed_as_dismissed(self):
        member=self.applicant();decide_application(self.approver,member.pk,'approve');member.refresh_from_db()
        html=self.render_listing(member)
        self.assertIn('Verified</span>',html);self.assertNotIn('Dismissed</span>',html)
    def test_archived_applicant_has_preservation_label_not_reinstate_action(self):
        member=self.applicant();decide_application(self.approver,member.pk,'reject');member.refresh_from_db()
        html=self.render_listing(member)
        self.assertIn('Archived</span>',html);self.assertIn('Records preserved',html)
        self.assertNotIn('> Reinstate',html);self.assertNotIn('> Edit Role',html)
