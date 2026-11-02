"""Phase 2 — Community Radar: editorial linking between community
reports and stories, the claim-from-report rule, and the hard privacy
rule that reporter-private data never reaches a public surface."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from core.models import CommunityReport
from editorial.tests.helpers import geo, make_user, media_director
from story_intelligence import services
from story_intelligence.models import Claim, Institution, Promise, StorySourceLink
from story_intelligence.services import story_panel_context

REPORTER_NAME = 'Aisha Bello Private'
REPORTER_PHONE = '08039998877'
INTERNAL_NOTE = 'INTERNAL NOTE DO NOT PUBLISH'
SECRET_DETAIL = 'CollapsedBridgeSecretDetail'
SECRET_LOCATION = 'Secret Hamlet Location'


def make_report(lga, **kw):
    defaults = {
        'reporter_name': REPORTER_NAME,
        'reporter_phone': REPORTER_PHONE,
        'lga': lga,
        'location_details': SECRET_LOCATION,
        'category': 'INFRASTRUCTURE',
        'what_happened': f'The bridge collapsed. {SECRET_DETAIL}',
        'internal_notes': INTERNAL_NOTE,
        'status': 'APPROVED',
    }
    defaults.update(kw)
    return CommunityReport.objects.create(**defaults)


class RadarTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('radar_editor')
        cls.writer = make_user('radar_writer', title='Ward Communications Officer',
                               tier='WARD', role='WARD')
        _zone, cls.lga, _ward = geo()
        cls.article = Campaign.objects.create(
            author=cls.editor, title='Bridge Story', slug='bridge-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00902')
        cls.report = make_report(cls.lga)


class LinkingTests(RadarTestBase):
    def test_editor_links_report_from_story_desk(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('story_intelligence:link_report', args=[self.article.pk]),
            {'report_id': self.report.pk, 'kind': 'SOURCE'})
        self.assertRedirects(
            response, reverse('story_intelligence:desk', args=[self.article.pk]))
        link = StorySourceLink.objects.get(report=self.report, article=self.article)
        self.assertEqual(link.kind, 'SOURCE')
        self.assertEqual(link.linked_by, self.editor)

    def test_linking_twice_does_not_duplicate(self):
        services.link_report_to_story(self.report, self.article, 'SOURCE', self.editor)
        services.link_report_to_story(self.report, self.article, 'SOURCE', self.editor)
        self.assertEqual(StorySourceLink.objects.count(), 1)

    def test_editor_unlinks_report(self):
        link, _ = services.link_report_to_story(
            self.report, self.article, 'SOURCE', self.editor)
        self.client.force_login(self.editor)
        self.client.post(reverse(
            'story_intelligence:unlink_report', args=[self.article.pk, link.pk]))
        self.assertFalse(StorySourceLink.objects.exists())

    def test_non_editor_cannot_link(self):
        self.client.force_login(self.writer)
        response = self.client.post(
            reverse('story_intelligence:link_report', args=[self.article.pk]),
            {'report_id': self.report.pk, 'kind': 'SOURCE'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorySourceLink.objects.exists())

    def test_linking_never_changes_the_report_itself(self):
        services.link_report_to_story(self.report, self.article, 'SOURCE', self.editor)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'APPROVED')
        self.assertEqual(self.report.info_status, '')


class RadarDeskTests(RadarTestBase):
    def test_radar_lists_unlinked_approved_reports(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('story_intelligence:radar'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.report, list(response.context['unlinked_approved']))

    def test_linked_report_leaves_the_unlinked_list(self):
        services.link_report_to_story(self.report, self.article, 'SOURCE', self.editor)
        self.client.force_login(self.editor)
        response = self.client.get(reverse('story_intelligence:radar'))
        self.assertNotIn(self.report, list(response.context['unlinked_approved']))
        self.assertIn(self.report, list(response.context['reports']))

    def test_radar_link_action(self):
        self.client.force_login(self.editor)
        self.client.post(reverse('story_intelligence:radar_link'), {
            'report_id': self.report.pk, 'article_id': self.article.pk,
            'kind': 'FOLLOW_UP'})
        link = StorySourceLink.objects.get(report=self.report, article=self.article)
        self.assertEqual(link.kind, 'FOLLOW_UP')

    def test_non_editor_blocked_from_radar(self):
        self.client.force_login(self.writer)
        self.assertEqual(
            self.client.get(reverse('story_intelligence:radar')).status_code, 403)

    def test_pending_report_is_not_in_unlinked_approved(self):
        pending = make_report(self.lga, status='PENDING')
        self.client.force_login(self.editor)
        response = self.client.get(reverse('story_intelligence:radar'))
        self.assertNotIn(pending, list(response.context['unlinked_approved']))


class ClaimFromReportTests(RadarTestBase):
    def test_claim_from_report_starts_not_established(self):
        link, _ = services.link_report_to_story(
            self.report, self.article, 'SOURCE', self.editor)
        self.client.force_login(self.editor)
        self.client.post(reverse(
            'story_intelligence:claim_from_report', args=[self.article.pk, link.pk]))
        claim = Claim.objects.get(article=self.article)
        self.assertEqual(claim.status, 'NOT_ESTABLISHED')
        self.assertNotEqual(claim.status, 'CONFIRMED')
        self.assertEqual(claim.text, self.report.what_happened)


class ReporterPrivacyTests(RadarTestBase):
    """Reporter name, phone, internal notes and report detail must
    never appear on any public surface just because a report is linked."""

    def setUp(self):
        services.link_report_to_story(self.report, self.article, 'SOURCE', self.editor)

    def assert_no_private_data(self, content):
        for secret in (REPORTER_NAME, REPORTER_PHONE, INTERNAL_NOTE,
                       SECRET_DETAIL, SECRET_LOCATION):
            self.assertNotIn(secret, content)

    def test_public_article_page_shows_area_only(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('community reporters in', content)
        self.assertIn(self.lga.name, content)
        self.assert_no_private_data(content)

    def test_unapproved_report_gets_no_public_attribution(self):
        pending = make_report(self.lga, status='PENDING')
        services.link_report_to_story(pending, self.article, 'RELATED', self.editor)
        context = story_panel_context(self.article)
        # Only the APPROVED report contributes its LGA label.
        self.assertEqual(context['community_sources'], [self.lga.name])

    def test_panel_context_for_pending_only_link_has_no_attribution(self):
        StorySourceLink.objects.all().delete()
        pending = make_report(self.lga, status='UNDER_REVIEW')
        services.link_report_to_story(pending, self.article, 'SOURCE', self.editor)
        article = Campaign.objects.create(
            author=self.editor, title='Other Story', slug='other-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now())
        services.link_report_to_story(pending, article, 'SOURCE', self.editor)
        context = story_panel_context(article)
        self.assertTrue(context is None or context['community_sources'] == [])

    def test_api_article_response_has_no_reporter_data(self):
        response = self.client.get(f'/api/v1/newsroom/{self.article.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assert_no_private_data(response.content.decode())

    def test_public_tracker_has_no_reporter_data(self):
        institution = Institution.objects.create(name='Ministry of Works', kind='MINISTRY')
        promise = Promise.objects.create(
            institution=institution, title='Rebuild the bridge',
            description='Rebuild it.', announced_on='2026-09-01',
            status='IN_PROGRESS', created_by=self.editor)
        promise.stories.add(self.article)
        for url in (reverse('promises:list'),
                    reverse('promises:detail', args=[promise.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assert_no_private_data(response.content.decode())
