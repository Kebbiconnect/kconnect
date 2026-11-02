"""Phase 2 — Public Promise Tracker: permissions, the status workflow,
the COMPLETED_VERIFIED evidence guard, timeline/audit behaviour, and
public-page safety."""
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import make_user, media_director, president
from leadership.capabilities import capabilities_for
from story_intelligence import services
from story_intelligence.models import (
    Claim, EvidenceRecord, Institution, Promise, PromiseUpdate, StoryAudit,
)
from story_intelligence.services import PromiseError

PROMISE_CAPS = {'MANAGE_PROMISES', 'VERIFY_PROMISES'}


def make_promise(editor, **kw):
    institution = kw.pop('institution', None) or Institution.objects.get_or_create(
        name='Kebbi State Ministry of Works', defaults={
            'kind': 'MINISTRY', 'contact_note': 'INTERNAL CONTACT NOTE',
            'notes': 'INTERNAL INSTITUTION NOTE'})[0]
    defaults = {
        'institution': institution,
        'title': 'Rebuild the Argungu township road',
        'description': 'The government promised to rebuild the road.',
        'announced_by': 'The Governor',
        'announced_on': '2026-09-15',
        'created_by': editor,
    }
    defaults.update(kw)
    return Promise.objects.create(**defaults)


class PromiseCapabilityTests(TestCase):
    def test_editor_roles_receive_promise_capabilities(self):
        for factory, name in [(media_director, 'pc_director'),
                              (president, 'pc_president')]:
            user = factory(name)
            self.assertTrue(PROMISE_CAPS.issubset(set(capabilities_for(user))))

    def test_ordinary_members_have_no_promise_capabilities(self):
        writer = make_user('pc_writer', title='Ward Communications Officer',
                           tier='WARD', role='WARD')
        member = make_user('pc_member', title=None, role='GENERAL')
        for user in (writer, member):
            self.assertTrue(PROMISE_CAPS.isdisjoint(set(capabilities_for(user))))


class PromiseDeskAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('pd_editor')
        cls.writer = make_user('pd_writer', title='Ward Communications Officer',
                               tier='WARD', role='WARD')
        cls.promise = make_promise(cls.editor)

    def test_editor_can_open_promise_desk(self):
        self.client.force_login(self.editor)
        self.assertEqual(
            self.client.get(reverse('story_intelligence:promise_desk')).status_code, 200)

    def test_non_editor_is_blocked_from_desk(self):
        self.client.force_login(self.writer)
        self.assertEqual(
            self.client.get(reverse('story_intelligence:promise_desk')).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse('story_intelligence:promise_desk'))
        self.assertEqual(response.status_code, 302)

    def test_non_editor_cannot_add_institution(self):
        self.client.force_login(self.writer)
        response = self.client.post(
            reverse('story_intelligence:add_institution'),
            {'name': 'Sneaky Ministry', 'kind': 'MINISTRY'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Institution.objects.filter(name='Sneaky Ministry').exists())

    def test_non_editor_cannot_add_promise_update(self):
        self.client.force_login(self.writer)
        response = self.client.post(
            reverse('story_intelligence:promise_add_update', args=[self.promise.pk]),
            {'update_date': '2026-10-20', 'title': 'Sneaky', 'body': 'Nope'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PromiseUpdate.objects.filter(promise=self.promise).exists())


class PromiseCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('pcr_editor')
        cls.institution = Institution.objects.create(
            name='Ministry of Education', kind='MINISTRY')

    def test_editor_creates_promise_via_desk(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('story_intelligence:promise_create'), {
            'institution': self.institution.pk,
            'title': 'Free textbooks for primary schools',
            'description': 'Textbooks for every primary school pupil.',
            'announced_by': 'The Commissioner',
            'announced_on': '2026-10-01',
            'source_name': 'Kebbi Radio',
            'source_url': 'https://example.org/announcement',
            'deadline': '',
            'next_check_date': '',
        })
        promise = Promise.objects.get(title='Free textbooks for primary schools')
        self.assertRedirects(
            response,
            reverse('story_intelligence:promise_detail_desk', args=[promise.pk]))
        self.assertEqual(promise.status, 'ANNOUNCED')
        self.assertIsNone(promise.deadline)
        self.assertTrue(StoryAudit.objects.filter(
            action='PROMISE_CREATED', target_id=promise.pk).exists())


class PromiseStatusWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('psw_editor')
        cls.promise = make_promise(cls.editor)

    def test_full_workflow_including_delayed(self):
        for status in ('DOCUMENTED', 'IN_PROGRESS', 'DELAYED', 'IN_PROGRESS'):
            services.set_promise_status(self.promise, status, self.editor)
            self.promise.refresh_from_db()
            self.assertEqual(self.promise.status, status)
        updates = list(self.promise.updates.all())
        self.assertEqual([u.status_after for u in updates],
                         ['DOCUMENTED', 'IN_PROGRESS', 'DELAYED', 'IN_PROGRESS'])
        self.assertEqual(StoryAudit.objects.filter(
            action='PROMISE_STATUS_CHANGED', target_id=self.promise.pk).count(), 4)

    def test_unknown_status_rejected(self):
        with self.assertRaises(PromiseError):
            services.set_promise_status(self.promise, 'HALF_DONE', self.editor)

    def test_same_status_is_a_noop(self):
        services.set_promise_status(self.promise, 'ANNOUNCED', self.editor)
        self.assertFalse(self.promise.updates.exists())


class VerifiedCompletionGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('vcg_editor')
        cls.promise = make_promise(cls.editor, status='IN_PROGRESS')

    def test_verified_completion_blocked_without_evidence_service(self):
        with self.assertRaises(PromiseError):
            services.set_promise_status(self.promise, 'COMPLETED_VERIFIED', self.editor)
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'IN_PROGRESS')
        self.assertFalse(self.promise.updates.exists())

    def test_verified_completion_blocked_without_evidence_via_desk(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse('story_intelligence:promise_change_status', args=[self.promise.pk]),
            {'status': 'COMPLETED_VERIFIED', 'note': 'Trust me'})
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'IN_PROGRESS')

    def test_verified_completion_allowed_with_update_evidence(self):
        services.record_promise_update(
            self.promise, self.editor, update_date=timezone.localdate(),
            title='Completion inspection', body='KPN visited the site.',
            evidence_title='Inspection photos',
            evidence_url='https://example.org/inspection')
        services.set_promise_status(self.promise, 'COMPLETED_VERIFIED', self.editor)
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'COMPLETED_VERIFIED')

    def test_verified_completion_with_evidence_in_the_same_update(self):
        update = services.record_promise_update(
            self.promise, self.editor, update_date=timezone.localdate(),
            title='Verified complete', body='Evidence attached.',
            evidence_url='https://example.org/proof',
            new_status='COMPLETED_VERIFIED')
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'COMPLETED_VERIFIED')
        self.assertEqual(update.status_after, 'COMPLETED_VERIFIED')

    def test_verified_completion_blocked_via_update_without_evidence(self):
        with self.assertRaises(PromiseError):
            services.record_promise_update(
                self.promise, self.editor, update_date=timezone.localdate(),
                title='Claiming done', body='No evidence.', new_status='COMPLETED_VERIFIED')
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'IN_PROGRESS')
        self.assertFalse(self.promise.updates.exists())

    def test_verified_completion_requires_verify_capability(self):
        services.record_promise_update(
            self.promise, self.editor, update_date=timezone.localdate(),
            title='Evidence', body='', evidence_url='https://example.org/proof')
        with mock.patch('leadership.capabilities.capabilities_for',
                        return_value=('MANAGE_PROMISES',)):
            with self.assertRaises(PromiseError):
                services.set_promise_status(
                    self.promise, 'COMPLETED_VERIFIED', self.editor)
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'IN_PROGRESS')

    def test_verified_completion_via_confirmed_claim_with_evidence(self):
        article = Campaign.objects.create(
            author=self.editor, title='Road Story', slug='road-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00901')
        claim = Claim.objects.create(
            article=article, text='The road is complete.', status='OFFICIAL_STATEMENT')
        self.promise.stories.add(article)
        self.promise.verification_claim = claim
        self.promise.save()
        # An official statement alone is NOT verification evidence.
        self.assertFalse(self.promise.has_verification_evidence())
        EvidenceRecord.objects.create(
            article=article, claim=claim, kind='PHOTO', title='Site photo')
        # Still not enough while the claim is only an official statement.
        self.assertFalse(self.promise.has_verification_evidence())
        claim.status = 'CONFIRMED'
        claim.save()
        self.assertTrue(self.promise.has_verification_evidence())
        services.set_promise_status(self.promise, 'COMPLETED_VERIFIED', self.editor)
        self.promise.refresh_from_db()
        self.assertEqual(self.promise.status, 'COMPLETED_VERIFIED')


class PromiseTimelineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('ptl_editor')
        cls.promise = make_promise(cls.editor)

    def test_updates_are_chronological_and_audited(self):
        services.record_promise_update(
            self.promise, self.editor, update_date='2026-10-10',
            title='Later update', body='Second.')
        services.record_promise_update(
            self.promise, self.editor, update_date='2026-09-20',
            title='Earlier update', body='First.')
        titles = [u.title for u in self.promise.updates.all()]
        self.assertEqual(titles, ['Earlier update', 'Later update'])
        self.assertEqual(StoryAudit.objects.filter(
            action='PROMISE_UPDATE_ADDED', target_type='promise_update').count(), 2)


class PublicPromiseTrackerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('ppt_editor')
        cls.promise = make_promise(cls.editor, status='IN_PROGRESS')
        services.record_promise_update(
            cls.promise, cls.editor, update_date='2026-10-05',
            title='Work has started', body='Contractors are on site.',
            evidence_title='Site report', evidence_url='https://example.org/site-report')

    def test_list_renders_public_safe_fields(self):
        response = self.client.get(reverse('promises:list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Rebuild the Argungu township road', content)
        self.assertIn('Kebbi State Ministry of Works', content)
        self.assertIn('In progress', content)
        self.assertNotIn('INTERNAL CONTACT NOTE', content)
        self.assertNotIn('INTERNAL INSTITUTION NOTE', content)

    def test_detail_renders_timeline_and_evidence(self):
        response = self.client.get(reverse('promises:detail', args=[self.promise.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Work has started', content)
        self.assertIn('https://example.org/site-report', content)
        self.assertIn('In progress — work is under way', content)
        self.assertNotIn('INTERNAL CONTACT NOTE', content)
        self.assertNotIn('INTERNAL INSTITUTION NOTE', content)

    def test_list_status_filter(self):
        make_promise(self.editor, title='A delayed promise', status='DELAYED')
        response = self.client.get(reverse('promises:list') + '?status=DELAYED')
        content = response.content.decode()
        self.assertIn('A delayed promise', content)
        self.assertNotIn('Rebuild the Argungu township road', content)

    def test_desk_flags_due_next_check(self):
        make_promise(self.editor, title='Check me promise',
                     next_check_date='2020-01-01')
        self.client.force_login(self.editor)
        response = self.client.get(reverse('story_intelligence:promise_desk'))
        self.assertIn('due now', response.content.decode())
