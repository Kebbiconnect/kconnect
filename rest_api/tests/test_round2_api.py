"""Round 2 (Android 2.0.0 completion): the server-side fixes for the
25 PARTLY BUILT screens.

Each test class names the screen/item it pins. Where round 1 already
supplied the behaviour (field-report occurred_at/photo, promise image,
redact Story-ID resolution, community-report id), the tests lock it in
so the app can rely on it.
"""
import io
import shutil
import tempfile
from unittest import mock

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from core.models import AdvocacyCampaign, CommunityReport, IctAdminAssignment
from donations.models import Donation
from editorial.tests.helpers import (
    general_member, geo, make_user, media_director, president,
)
from intelligence.models import (
    CollectionRun, FieldReport, GeoAlias, IntelligenceAudit,
    IntelligenceCategory, Project, ProjectEvidence,
)
from leadership.models import LGA, Ward
from staff.models import User
from story_intelligence.models import Institution, Promise
from telegram_integration.models import TelegramMembership

API = '/api/v1/'
MEDIA_ROOT = tempfile.mkdtemp(prefix='kpn-round2-media-')


def png(name='test.png'):
    out = io.BytesIO()
    Image.new('RGB', (16, 16), 'green').save(out, 'PNG')
    return SimpleUploadedFile(name, out.getvalue(), content_type='image/png')


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class Round2Case(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.director = media_director('r2_director')
        self.president = president('r2_president')
        self.member = general_member('r2_member')
        self.zone, self.lga, self.ward = geo()


# ─── Item 1 / screen 43 + item 3 / screen 48 ────────────────────────────────

class CommunityReportRound2Tests(Round2Case):
    def test_list_payload_names_lga_and_ward(self):
        CommunityReport.objects.create(
            reporter_name='Private Person', reporter_phone='08000000000',
            submitted_by=self.member, lga=self.lga, ward=self.ward,
            location_details='Near the market', category='HEALTH',
            what_happened='The clinic roof leaks.', status='APPROVED',
            info_status='CONFIRMED')
        response = client_for(self.director).get(API + 'community-reports/')
        self.assertEqual(response.status_code, 200, response.content)
        row = response.data['results'][0]
        self.assertEqual(row['lga_name'], self.lga.name)
        self.assertEqual(row['ward_name'], self.ward.name)
        self.assertEqual(row['lga'], self.lga.pk)
        self.assertEqual(row['ward'], self.ward.pk)

    def test_create_response_includes_created_id(self):
        # Screen 48: the POST response carries the created report's id
        # (the model has no reference/code field — the id is the only
        # identifier, and nothing else is invented).
        response = client_for(self.director).post(
            API + 'community-reports/', {
                'lga': self.lga.pk, 'ward': self.ward.pk,
                'location_details': 'By the well', 'category': 'HEALTH',
                'what_happened': 'No water since Monday.',
            }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIn('id', response.data)
        self.assertTrue(
            CommunityReport.objects.filter(pk=response.data['id']).exists())


# ─── Item 2 / screen 45 ─────────────────────────────────────────────────────

class AdvocacyDetailRound2Tests(Round2Case):
    def test_detail_payload_mirrors_web_detail_page(self):
        published = Campaign.objects.create(
            author=self.director, title='Evidence Story', slug='evidence-story',
            status='PUBLISHED', content='Body',
            published_at=timezone.now(), story_id='KPN-SI-2026-00042')
        draft = Campaign.objects.create(
            author=self.director, title='Draft Story', slug='draft-story',
            status='DRAFT', content='Body')
        campaign = AdvocacyCampaign.objects.create(
            title='Fix the Jega road', issue='The road is impassable.',
            background='Background text.', objective='A passable road.',
            proposed_action='Petition the ministry.',
            government_response='The ministry replied.',
            outcome='', status='PAUSED')
        campaign.evidence_articles.set([published, draft])
        response = APIClient().get(API + f'advocacy/{campaign.pk}/')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertEqual(data['objective'], 'A passable road.')
        self.assertEqual(data['background'], 'Background text.')
        self.assertEqual(data['proposed_action'], 'Petition the ministry.')
        self.assertEqual(data['government_response'], 'The ministry replied.')
        self.assertEqual(data['status'], 'PAUSED')
        self.assertEqual(data['status_label'], 'Paused')
        # Web detail page shows PUBLISHED evidence only, with Story IDs.
        self.assertEqual(len(data['evidence_articles']), 1)
        evidence = data['evidence_articles'][0]
        self.assertEqual(evidence['id'], published.pk)
        self.assertEqual(evidence['slug'], 'evidence-story')
        self.assertEqual(evidence['story_id'], 'KPN-SI-2026-00042')


# ─── Item 6 / screen 73 ─────────────────────────────────────────────────────

class ReportCreateRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        self.recipient = make_user(
            'r2_lga_lead', title='LGA Network Lead', tier='LGA', role='LGA')
        self.submitter = make_user(
            'r2_ward_lead', title='Ward Community Lead', tier='WARD',
            role='WARD')

    def test_create_accepts_matching_type_and_recipient(self):
        response = client_for(self.submitter).post(API + 'reports/', {
            'title': 'Ward report', 'content': 'All quiet.',
            'report_type': 'WARD_TO_LGA', 'submitted_to': self.recipient.pk,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['report_type'], 'WARD_TO_LGA')
        self.assertEqual(response.data['submitted_to'], self.recipient.pk)

    def test_create_rejects_mismatched_type_or_recipient(self):
        client = client_for(self.submitter)
        bad_type = client.post(API + 'reports/', {
            'title': 'Ward report', 'content': 'All quiet.',
            'report_type': 'LGA_TO_ZONAL',
        }, format='json')
        self.assertEqual(bad_type.status_code, 400, bad_type.content)
        bad_recipient = client.post(API + 'reports/', {
            'title': 'Ward report', 'content': 'All quiet.',
            'submitted_to': self.director.pk,
        }, format='json')
        self.assertEqual(bad_recipient.status_code, 400, bad_recipient.content)


# ─── Item 7 / screen 70 ─────────────────────────────────────────────────────

class MemberDecisionNoteRound2Tests(Round2Case):
    def test_reject_with_note_stores_archive_reason(self):
        applicant = make_user(
            'r2_applicant_note', title=None, role='GENERAL', status='PENDING')
        response = client_for(self.president).post(
            API + f'members/{applicant.pk}/decision/',
            {'decision': 'reject', 'note': 'Documents were incomplete.'},
            format='json')
        self.assertEqual(response.status_code, 200, response.content)
        applicant.refresh_from_db()
        self.assertEqual(applicant.status, 'REJECTED')
        self.assertEqual(applicant.archive_reason, 'Documents were incomplete.')

    def test_reject_with_reason_still_works(self):
        applicant = make_user(
            'r2_applicant_reason', title=None, role='GENERAL', status='PENDING')
        response = client_for(self.president).post(
            API + f'members/{applicant.pk}/decision/',
            {'decision': 'reject', 'reason': 'Legacy reason field.'},
            format='json')
        self.assertEqual(response.status_code, 200, response.content)
        applicant.refresh_from_db()
        self.assertEqual(applicant.archive_reason, 'Legacy reason field.')


# ─── Item 8 / screen 93 ─────────────────────────────────────────────────────

class DonationRejectRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        self.finance = make_user(
            'r2_finance', title='Director of Finance', tier='STATE',
            role='STATE')
        self.donation = Donation.objects.create(
            donor_name='A Donor', amount='5000.00', reference='REF-R2-1')

    def test_reject_requires_reason(self):
        response = client_for(self.finance).post(
            API + f'finance/donations/{self.donation.pk}/reject/', {},
            format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, 'UNVERIFIED')

    def test_reject_records_actor_time_and_reason(self):
        response = client_for(self.finance).post(
            API + f'finance/donations/{self.donation.pk}/reject/',
            {'reason': 'Reference could not be traced.'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['status'], 'REJECTED')
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, 'REJECTED')
        self.assertEqual(self.donation.rejected_by, self.finance)
        self.assertIsNotNone(self.donation.rejected_at)
        self.assertEqual(
            self.donation.rejection_reason, 'Reference could not be traced.')

    def test_reject_is_gated_like_verify(self):
        response = client_for(self.member).post(
            API + f'finance/donations/{self.donation.pk}/reject/',
            {'reason': 'No.'}, format='json')
        self.assertEqual(response.status_code, 403, response.content)

    def test_reject_only_from_unverified(self):
        self.donation.status = 'VERIFIED'
        self.donation.save(update_fields=['status'])
        response = client_for(self.finance).post(
            API + f'finance/donations/{self.donation.pk}/reject/',
            {'reason': 'Too late.'}, format='json')
        self.assertEqual(response.status_code, 404, response.content)


# ─── Item 9 / screen 100 ────────────────────────────────────────────────────

class ManagementContentTypesRound2Tests(Round2Case):
    def test_faq_create_accepts_json_and_multipart(self):
        client = client_for(self.director)
        as_json = client.post(API + 'management/faq/', {
            'question': 'JSON question?', 'answer': 'JSON answer.',
            'order': 1, 'is_active': True,
        }, format='json')
        self.assertEqual(as_json.status_code, 201, as_json.content)
        as_multipart = client.post(API + 'management/faq/', {
            'question': 'Multipart question?', 'answer': 'Multipart answer.',
            'order': 2, 'is_active': 'true',
        }, format='multipart')
        self.assertEqual(as_multipart.status_code, 201, as_multipart.content)

    def test_community_create_accepts_json_and_multipart_with_image(self):
        client = client_for(self.director)
        as_json = client.post(API + 'management/community/', {
            'title': 'JSON initiative', 'category': 'WELFARE',
            'description': 'Created from JSON.', 'status': 'PLANNING',
            'location_text': 'Jega',
        }, format='json')
        self.assertEqual(as_json.status_code, 201, as_json.content)
        as_multipart = client.post(API + 'management/community/', {
            'title': 'Multipart initiative', 'category': 'WELFARE',
            'description': 'Created from multipart.', 'status': 'PLANNING',
            'location_text': 'Jega',
            'image': png('initiative.png'),
        }, format='multipart')
        self.assertEqual(as_multipart.status_code, 201, as_multipart.content)
        self.assertTrue(as_multipart.data['image'])


# ─── Item 10 / screen 114 + item 11 / screen 115 ────────────────────────────

class MembersWingAndTierRound2Tests(Round2Case):
    def test_wing_women_filters_server_side(self):
        woman = make_user('r2_woman', title=None, role='GENERAL', gender='F')
        man = make_user('r2_man', title=None, role='GENERAL', gender='M')
        client = client_for(self.director)
        response = client.get(API + 'members/', {'wing': 'women'})
        self.assertEqual(response.status_code, 200, response.content)
        ids = [row['id'] for row in response.data['results']]
        self.assertIn(woman.pk, ids)
        self.assertNotIn(man.pk, ids)
        unknown = client.get(API + 'members/', {'wing': 'unknown-wing'})
        self.assertEqual(unknown.data['results'], [])

    def test_leadership_directory_carries_tier(self):
        response = APIClient().get(API + 'leadership-directory/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data['results'])
        for row in response.data['results']:
            self.assertIn('tier', row)
            self.assertEqual(row['tier'], row['role'])


# ─── Item 14 / screens 133–134 ──────────────────────────────────────────────

class ArticleDecisionLiteralsRound2Tests(Round2Case):
    """Locks the exact action literals POST articles/<id>/decision/
    accepts: 'publish', 'return', 'reject' (case-sensitive), in the
    `action` field; 'return'/'reject' require `note`."""

    def pending_article(self, slug):
        return Campaign.objects.create(
            title='Round 2 fixture', slug=slug, content='Content',
            status='PENDING', author=self.member)

    def test_publish_literal(self):
        article = self.pending_article('r2-publish')
        response = client_for(self.director).post(
            API + f'articles/{article.pk}/decision/',
            {'action': 'publish'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')

    def test_return_and_reject_literals_require_note(self):
        client = client_for(self.director)
        for index, action in enumerate(('return', 'reject')):
            article = self.pending_article(f'r2-{action}')
            no_note = client.post(
                API + f'articles/{article.pk}/decision/',
                {'action': action}, format='json')
            self.assertEqual(no_note.status_code, 400, no_note.content)
            with_note = client.post(
                API + f'articles/{article.pk}/decision/',
                {'action': action, 'note': 'Please revise.'}, format='json')
            self.assertEqual(with_note.status_code, 200, with_note.content)
            article.refresh_from_db()
            self.assertEqual(article.status, 'REJECTED')
            self.assertEqual(article.rejection_note, 'Please revise.')

    def test_other_literals_are_refused(self):
        client = client_for(self.director)
        article = self.pending_article('r2-other-literals')
        for action in ('approve', 'PUBLISH', 'Return', 'delete', ''):
            response = client.post(
                API + f'articles/{article.pk}/decision/',
                {'action': action, 'note': 'x'}, format='json')
            self.assertEqual(response.status_code, 400, (action, response.content))
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')


# ─── Item 15 / screen 138 ───────────────────────────────────────────────────

class FieldReportRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        from intelligence.tests.helpers import seed_directory
        seed_directory()
        self.reporter = make_user(
            'r2_field_reporter', title=None, role='GENERAL',
            is_trusted_reporter=True)
        self.jega = LGA.objects.get(name='Jega')
        self.category = IntelligenceCategory.objects.get(slug='education')

    def test_create_accepts_occurred_at_and_photo_multipart(self):
        response = client_for(self.reporter).post(API + 'field-reports/', {
            'headline': 'School roof damaged',
            'report_text': 'The roof came off in the storm.',
            'lga': self.jega.pk, 'category': self.category.pk,
            'occurred_at': '2026-11-20T10:30:00',
            'photo': png('field.png'),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        report = FieldReport.objects.get(pk=response.data['id'])
        self.assertEqual(report.occurred_at.date().isoformat(), '2026-11-20')
        self.assertTrue(report.photo)

    def test_create_accepts_occurred_at_json(self):
        response = client_for(self.reporter).post(API + 'field-reports/', {
            'headline': 'Market day incident',
            'report_text': 'A stall collapsed; nobody was hurt.',
            'lga': self.jega.pk, 'category': self.category.pk,
            'occurred_at': '2026-11-21T09:15:00Z',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        report = FieldReport.objects.get(pk=response.data['id'])
        self.assertEqual(report.occurred_at.date().isoformat(), '2026-11-21')


# ─── Item 16 / screen 170 ───────────────────────────────────────────────────

class CollectionRunTriggerRound2Tests(Round2Case):
    def test_trigger_creates_manual_run_record(self):
        response = client_for(self.director).post(
            API + 'intelligence/runs/trigger/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['trigger'], 'MANUAL')
        run = CollectionRun.objects.get(pk=response.data['id'])
        self.assertEqual(run.trigger, 'MANUAL')
        self.assertIn(run.status, ('COMPLETED', 'PAUSED', 'SKIPPED_LEASED'))

    def test_trigger_is_gated_on_manage_sources(self):
        response = client_for(self.member).post(
            API + 'intelligence/runs/trigger/', {}, format='json')
        self.assertEqual(response.status_code, 403, response.content)

    def test_web_run_now_button_and_view(self):
        from django.test import Client
        web = Client()
        web.force_login(self.director)
        page = web.get(reverse('intelligence:overview'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Run now')
        self.assertContains(page, reverse('intelligence:run_now'))
        with mock.patch(
                'intelligence.cycle.run_cycle',
                return_value=CollectionRun.objects.create(
                    trigger='MANUAL', status='COMPLETED',
                    started_at=timezone.now(),
                    finished_at=timezone.now())) as run_cycle:
            response = web.post(reverse('intelligence:run_now'))
        self.assertEqual(response.status_code, 302)
        run_cycle.assert_called_once_with(trigger='MANUAL')
        web_member = Client()
        web_member.force_login(self.member)
        self.assertEqual(
            web_member.post(reverse('intelligence:run_now')).status_code, 403)


# ─── Item 17 / screen 171 ───────────────────────────────────────────────────

class AliasCreateRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        from intelligence.tests.helpers import seed_directory
        seed_directory()
        self.jega = LGA.objects.get(name='Jega')

    def test_create_makes_pending_alias_with_audit(self):
        response = client_for(self.director).post(
            API + 'intelligence/aliases/', {
                'alias': 'Jega Town', 'target_kind': 'LGA',
                'lga': self.jega.pk,
            }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['status'], 'PENDING')
        alias = GeoAlias.objects.get(pk=response.data['id'])
        self.assertEqual(alias.created_by, self.director)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='ALIAS_CREATED', target_type='GeoAlias',
            target_id=alias.pk).exists())

    def test_create_is_gated_like_review(self):
        response = client_for(self.member).post(
            API + 'intelligence/aliases/', {
                'alias': 'Nowhere', 'target_kind': 'LGA',
                'lga': self.jega.pk,
            }, format='json')
        self.assertEqual(response.status_code, 403, response.content)


# ─── Item 20 / screen 187 ───────────────────────────────────────────────────

class ProjectEvidenceRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        self.audit_lead = make_user(
            'r2_audit', title='Director of Audit & Accountability')
        self.project = Project.objects.create(
            project_code='KPN-PRJ-2026-00077', title='Round 2 project',
            description='A project.', sector='WATER', category='WATER',
            status='REPORTED_ABANDONED')

    def test_evidence_accepts_multipart_file(self):
        response = client_for(self.audit_lead).post(
            API + f'intelligence/projects/{self.project.pk}/evidence/', {
                'kind': 'PHOTO', 'title': 'Site photo',
                'file': png('evidence.png'),
                'verification_state': 'DOCUMENTED', 'is_public': 'true',
            }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        evidence = ProjectEvidence.objects.get(pk=response.data['id'])
        self.assertTrue(evidence.file)

    def test_evidence_accepts_json_url(self):
        response = client_for(self.audit_lead).post(
            API + f'intelligence/projects/{self.project.pk}/evidence/', {
                'kind': 'OTHER', 'title': 'News report',
                'url': 'https://example.org/report',
                'verification_state': 'DOCUMENTED', 'is_public': True,
            }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        evidence = ProjectEvidence.objects.get(pk=response.data['id'])
        self.assertEqual(evidence.url, 'https://example.org/report')
        self.assertFalse(evidence.file)


# ─── Item 21 / screen 191 ───────────────────────────────────────────────────

class PromiseImageRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        self.institution = Institution.objects.create(name='R2 Ministry')

    def test_create_accepts_multipart_image(self):
        response = client_for(self.director).post(
            API + 'story-intelligence/promises/', {
                'institution': self.institution.pk,
                'title': 'Promise with image',
                'description': 'A promise.', 'announced_on': '2026-11-01',
                'sector': 'HEALTH', 'image': png('promise.png'),
            }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        promise = Promise.objects.get(pk=response.data['id'])
        self.assertTrue(promise.image)

    def test_desk_patch_accepts_multipart_image(self):
        promise = Promise.objects.create(
            institution=self.institution, title='Patch me',
            description='A promise.', status='ANNOUNCED',
            announced_on='2026-11-01')
        response = client_for(self.director).patch(
            API + f'story-intelligence/promises/{promise.pk}/desk/',
            {'image': png('patched.png')}, format='multipart')
        self.assertEqual(response.status_code, 200, response.content)
        promise.refresh_from_db()
        self.assertTrue(promise.image)


# ─── Item 22 / screen 194 ───────────────────────────────────────────────────

class RedactStoryIdRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        self.article = Campaign.objects.create(
            author=self.director, title='Sensitive Story',
            slug='r2-sensitive-story', status='PUBLISHED',
            content='Body naming a private person.',
            published_at=timezone.now(), story_id='KPN-SI-2026-00123')

    def test_redact_by_numeric_id(self):
        response = client_for(self.director).post(
            API + 'story-intelligence/redact/', {
                'target_type': 'article', 'target_id': self.article.pk,
                'reason_category': 'SAFETY',
            }, format='json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_redact_by_story_id_field(self):
        response = client_for(self.director).post(
            API + 'story-intelligence/redact/', {
                'story_id': 'KPN-SI-2026-00123', 'reason': 'SAFETY',
            }, format='json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_redact_by_target_id_story_id_string(self):
        response = client_for(self.director).post(
            API + 'story-intelligence/redact/', {
                'target_type': 'article', 'target_id': 'KPN-SI-2026-00123',
                'reason_category': 'SAFETY',
            }, format='json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_redact_unknown_story_id_404(self):
        response = client_for(self.director).post(
            API + 'story-intelligence/redact/', {
                'story_id': 'KPN-SI-2026-99999', 'reason': 'SAFETY',
            }, format='json')
        self.assertEqual(response.status_code, 404, response.content)


# ─── Item 23 / screen 202 ───────────────────────────────────────────────────

class IctTelegramRound2Tests(Round2Case):
    def setUp(self):
        super().setUp()
        IctAdminAssignment.objects.create(pk=1, user=self.director)

    def test_payload_has_bot_identity_and_server_side_leader_counts(self):
        linked_leader = make_user(
            'r2_linked_leader', title='General Secretary')
        TelegramMembership.objects.create(
            user=linked_leader, telegram_user_id=123456,
            telegram_username='linked_leader', telegram_status='member',
            is_verified=True)
        make_user('r2_unlinked_leader', title='Vice President')
        response = client_for(self.director).get(API + 'ict/telegram/')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertEqual(data['bot_username'], '@KPNKebbiBot')
        self.assertEqual(data['channel_id'], '-1002364023770')
        self.assertNotIn('channel_handle', data)
        # Leaders in this fixture: director, president (setUp), the
        # linked General Secretary and the unlinked President — only
        # the linked one has a verified membership.
        self.assertEqual(data['leaders_linked'], 1)
        self.assertEqual(
            data['leaders_not_linked'], data['leaders_total'] - 1)
        self.assertGreaterEqual(data['leaders_total'], 4)
