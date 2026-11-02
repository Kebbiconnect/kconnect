"""The public article page and API expose story data — and ONLY story
data: no consent records, no audit internals, no draft updates, no
private evidence, no reporter-private information.
"""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from story_intelligence.models import (
    Claim, ConsentRecord, Correction, EvidenceRecord, StoryProfile, StoryUpdate,
)


class PublicPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('panel_editor')

    def setUp(self):
        self.article = Campaign.objects.create(
            author=self.editor, title='Panel Story', slug='panel-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00071',
            source_name='Daily Trust', source_url='https://example.com/original')
        StoryProfile.objects.create(
            article=self.article, kind='NEWS',
            why_it_matters='It decides water access for three wards.',
            who_is_affected='Residents of Argungu.',
            what_is_unknown='The contractor has not been named.',
            what_to_watch='The council meeting on Thursday.')
        StoryUpdate.objects.create(
            article=self.article, title='Council Responds', body='Response body.',
            status='PUBLISHED', published_at=timezone.now(), author=self.editor)
        StoryUpdate.objects.create(
            article=self.article, title='DRAFT-SECRET-UPDATE', body='Hidden.',
            status='DRAFT', author=self.editor)
        Claim.objects.create(
            article=self.article, text='The project cost is N40 million.',
            status='OFFICIAL_STATEMENT', noted_by=self.editor)
        Claim.objects.create(
            article=self.article, text='Work started on Monday.',
            status='CONFIRMED', noted_by=self.editor)
        EvidenceRecord.objects.create(
            article=self.article, title='Council minutes (public)',
            kind='OFFICIAL_RECORD', url='https://example.com/minutes',
            is_public=True, added_by=self.editor)
        EvidenceRecord.objects.create(
            article=self.article, title='PRIVATE-EVIDENCE-SECRET',
            kind='DOCUMENT', is_public=False, added_by=self.editor)
        Correction.objects.create(
            article=self.article, kind='CORRECTION',
            text='An earlier version misstated the ward name.',
            created_by=self.editor)
        ConsentRecord.objects.create(
            article=self.article, subject_descriptor='CONSENT-SECRET-SUBJECT',
            consent_basis='WRITTEN', recorded_by=self.editor,
            notes='CONSENT-SECRET-NOTES')

    def test_panel_renders_story_data(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)
        for expected in ['KPN-SI-2026-00071', 'Story File',
                         'It decides water access for three wards.',
                         'Council Responds', 'Confirmed by KPN',
                         'not independently verified',
                         'Council minutes (public)',
                         'An earlier version misstated the ward name.']:
            self.assertContains(response, expected)

    def test_panel_never_renders_private_data(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.article.slug]))
        for forbidden in ['DRAFT-SECRET-UPDATE', 'PRIVATE-EVIDENCE-SECRET',
                          'CONSENT-SECRET-SUBJECT', 'CONSENT-SECRET-NOTES']:
            self.assertNotContains(response, forbidden)

    def test_article_without_story_data_renders_as_before(self):
        plain = Campaign.objects.create(
            author=self.editor, title='Ordinary Story', slug='ordinary-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now())
        response = self.client.get(
            reverse('campaigns:article_detail', args=[plain.slug]))
        self.assertEqual(response.status_code, 200)
        # The panel markup (folder icon + section) must not render at all.
        self.assertNotContains(response, 'fa-folder-open')

    def test_story_id_alone_shows_panel(self):
        only_id = Campaign.objects.create(
            author=self.editor, title='Id Only Story', slug='id-only-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00072')
        response = self.client.get(
            reverse('campaigns:article_detail', args=[only_id.slug]))
        self.assertContains(response, 'KPN-SI-2026-00072')


class ApiExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('api_panel_editor')

    def setUp(self):
        self.client = APIClient()
        self.article = Campaign.objects.create(
            author=self.editor, title='Api Story', slug='api-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00073', source_name='Punch',
            source_url='https://example.com/punch-story')

    def test_newsroom_detail_exposes_story_and_source_fields(self):
        response = self.client.get(f'/api/v1/newsroom/{self.article.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['story_id'], 'KPN-SI-2026-00073')
        self.assertEqual(response.data['source_name'], 'Punch')
        self.assertEqual(response.data['source_url'], 'https://example.com/punch-story')

    def test_story_id_is_read_only_on_write_serializer(self):
        self.client.force_authenticate(self.editor)
        response = self.client.post('/api/v1/articles/mine/', {
            'title': 'Written Via Api', 'category': 'GENERAL',
            'content': 'Body.', 'verification_status': 'DEVELOPING',
            'reporter_credit': 'KPN_REPORTER',
            'story_id': 'KPN-SI-1999-99999',
            'source_name': 'Wire', 'source_url': 'https://example.com/wire',
        })
        self.assertEqual(response.status_code, 201)
        created = Campaign.objects.get(title='Written Via Api')
        self.assertIsNone(created.story_id)
        self.assertEqual(created.source_name, 'Wire')
