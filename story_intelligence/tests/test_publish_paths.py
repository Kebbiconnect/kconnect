"""Every real publication path must produce a Story ID (Phase 1 §7.5):
web review queue, REST API decision, brain auto-publish, editorial-desk
handoff. Allocation failure on the web/API paths leaves the article
PENDING and recoverable.
"""
import re

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from editorial import publish as brain_publish
from editorial import services as editorial_services
from editorial.models import Item
from editorial.tests.helpers import media_director
from story_intelligence.models import StorySequence

STORY_ID_RE = re.compile(r'^KPN-SI-\d{4}-\d{5}$')


def pending_article(author, title):
    return Campaign.objects.create(
        author=author, title=title, slug=title.lower().replace(' ', '-'),
        status='PENDING', content='Body.')


class WebPublishPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('path_editor')

    def test_web_publish_assigns_story_id(self):
        article = pending_article(self.editor, 'Web Path Story')
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('campaigns:publish_article', args=[article.pk]))
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertTrue(STORY_ID_RE.match(article.story_id))

    def test_web_publish_allocation_failure_leaves_article_pending(self):
        year = timezone.now().year
        Campaign.objects.create(
            author=self.editor, title='Id Holder', slug='id-holder',
            status='PUBLISHED', content='x', published_at=timezone.now(),
            story_id=f'KPN-SI-{year}-00001')
        StorySequence.objects.create(year=year, last_number=0)
        article = pending_article(self.editor, 'Colliding Story')
        self.client.force_login(self.editor)
        self.client.post(reverse('campaigns:publish_article', args=[article.pk]))
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')
        self.assertIsNone(article.story_id)


class ApiPublishPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('api_editor')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.editor)

    def test_api_publish_assigns_story_id_and_exposes_fields(self):
        article = pending_article(self.editor, 'Api Path Story')
        response = self.client.post(
            f'/api/v1/articles/{article.pk}/decision/', {'action': 'publish'})
        self.assertEqual(response.status_code, 200)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertTrue(STORY_ID_RE.match(article.story_id))
        self.assertEqual(response.data['story_id'], article.story_id)
        self.assertIn('source_name', response.data)
        self.assertIn('source_url', response.data)

    def test_api_publish_allocation_failure_leaves_article_pending(self):
        year = timezone.now().year
        Campaign.objects.create(
            author=self.editor, title='Api Id Holder', slug='api-id-holder',
            status='PUBLISHED', content='x', published_at=timezone.now(),
            story_id=f'KPN-SI-{year}-00001')
        StorySequence.objects.create(year=year, last_number=0)
        article = pending_article(self.editor, 'Api Colliding Story')
        response = self.client.post(
            f'/api/v1/articles/{article.pk}/decision/', {'action': 'publish'})
        self.assertEqual(response.status_code, 400)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')
        self.assertIsNone(article.story_id)


def news_item(key, title='Brain Story'):
    return Item.objects.create(
        key=key, kind='NEWS', title=title, state='REVIEW',
        source_url='https://example.com/story',
        original={'title': title, 'text': 'Evidence text',
                  'source_url': 'https://example.com/story'},
        draft={'title': title, 'body': 'First paragraph.\n\nSecond paragraph.',
               'category': 'GENERAL'})


@override_settings(KPN_EDITORIAL_AUTO_PUBLISH=True)
class BrainPublishPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('brain_editor')

    def test_brain_publish_assigns_story_id(self):
        item = news_item('brain-path-1')
        result = brain_publish.publish_brain_item(item)
        self.assertTrue(result['published'])
        item.refresh_from_db()
        self.assertEqual(item.state, 'HANDED_OFF')
        self.assertIsNotNone(item.article)
        self.assertEqual(item.article.status, 'PUBLISHED')
        self.assertTrue(STORY_ID_RE.match(item.article.story_id))

    def test_editorial_handoff_assigns_story_id(self):
        item = news_item('brain-path-2')
        editorial_services.act(self.editor, item.pk, 'handoff', item.version,
                               confirmed=True)
        item.refresh_from_db()
        self.assertEqual(item.state, 'HANDED_OFF')
        self.assertEqual(item.article.status, 'PUBLISHED')
        self.assertTrue(STORY_ID_RE.match(item.article.story_id))
