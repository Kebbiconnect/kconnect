"""v2.4: category/deadline validation, auto-publish, publish-item rescue,
featured images, and editor powers over published articles."""
import base64
import io
import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from campaigns.models import Campaign
from core.models import Opportunity
from editorial import brain, publish
from editorial.brain import BrainError
from editorial.models import Item
from editorial.tests.helpers import make_user, media_director

TOKEN = 'test-brain-token-with-at-least-32-characters'
AUTH = {'HTTP_AUTHORIZATION': f'Bearer {TOKEN}'}
FUTURE = '2027-06-30'


def opp_item(**kw):
    defaults = dict(
        key='pub-opp-1', kind='OPPORTUNITY', title='Opp', state='REVIEW',
        source_url='https://example.com/opp',
        original={'title': 'Opp', 'text': 'Details', 'source_url': 'https://example.com/opp',
                  'application_links': [{'url': 'https://example.com/apply', 'label': 'Apply'}]},
        draft={'title': 'Opp', 'body': 'Body', 'provider': 'NGO', 'category': 'JOB',
               'application_link': 'https://example.com/apply', 'deadline': FUTURE})
    defaults.update(kw)
    return Item.objects.create(**defaults)


class CategoryValidationTests(TestCase):
    def _news(self):
        return Item.objects.create(key='val-news', kind='NEWS', title='N',
                                   original={'title': 'N', 'text': 'E'})

    def _opp(self):
        return Item.objects.create(
            key='val-opp', kind='OPPORTUNITY', title='O',
            original={'title': 'O', 'text': 'E', 'source_url': 'https://example.com/o'})

    def test_opportunity_general_category_rejected(self):
        # The exact bug from production: 'GENERAL' is a news category only.
        with self.assertRaises(BrainError) as ctx:
            brain.validate_draft(self._opp(), {'title': 'O', 'body': 'B', 'provider': 'P',
                                               'category': 'GENERAL'})
        self.assertEqual(ctx.exception.code, 'invalid_category')

    def test_opportunity_category_alias_normalised(self):
        draft = {'title': 'O', 'body': 'B', 'provider': 'P',
                 'category': 'Scholarships & Education', 'deadline': FUTURE}
        brain.validate_draft(self._opp(), draft)
        self.assertEqual(draft['category'], 'SCHOLARSHIP')

    def test_news_category_alias_normalised(self):
        draft = {'title': 'N', 'body': 'B', 'category': 'Government'}
        brain.validate_draft(self._news(), draft)
        self.assertEqual(draft['category'], 'GOVERNANCE')

    def test_freetext_deadline_rejected(self):
        with self.assertRaises(BrainError) as ctx:
            brain.validate_draft(self._opp(), {'title': 'O', 'body': 'B', 'provider': 'P',
                                               'category': 'SCHOLARSHIP',
                                               'deadline': '30 November 2026'})
        self.assertEqual(ctx.exception.code, 'invalid_deadline')

    def test_past_deadline_rejected(self):
        with self.assertRaises(BrainError) as ctx:
            brain.validate_draft(self._opp(), {'title': 'O', 'body': 'B', 'provider': 'P',
                                               'category': 'SCHOLARSHIP',
                                               'deadline': '2020-01-01'})
        self.assertEqual(ctx.exception.code, 'deadline_passed')


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN,
                   KPN_EDITORIAL_AUTO_PUBLISH=True)
class AutoPublishApiTests(TestCase):
    def setUp(self):
        self.director = media_director('pub_director')

    def _post_candidate(self, payload):
        return self.client.post(reverse('editorial:brain_submit_item'),
                                data=json.dumps(payload), content_type='application/json', **AUTH)

    def test_news_candidate_publishes_immediately(self):
        response = self._post_candidate({
            'kind': 'NEWS', 'title': 'Kebbi cyclists celebrate',
            'source_url': 'https://example.com/kebbi-cyclists',
            'source_name': 'Example News', 'text': 'Cyclists in Kebbi celebrated.',
            'draft': {'title': 'Kebbi cyclists celebrate', 'body': 'Cyclists in Kebbi celebrated.',
                      'category': 'YOUTH'}})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body['published'])
        self.assertEqual(body['state'], 'HANDED_OFF')
        article = Campaign.objects.get(slug=body['slug'])
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertIsNotNone(article.published_at)
        self.assertEqual(article.author, self.director)
        self.assertEqual(article.reporter_credit, 'KPN_EDITORIAL')

    def test_opportunity_candidate_publishes_open_with_alias_category(self):
        response = self._post_candidate({
            'kind': 'OPPORTUNITY', 'title': 'Big Scholarship 2027',
            'source_url': 'https://example.com/apply-here',
            'source_name': 'Example', 'text': 'Scholarships for Nigerian students.',
            'draft': {'title': 'Big Scholarship 2027', 'body': 'Apply now.',
                      'provider': 'Example Trust', 'category': 'Scholarships & Education',
                      'application_link': 'https://example.com/apply-here',
                      'deadline': FUTURE}})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body['published'])
        opp = Opportunity.objects.get(slug=body['slug'])
        self.assertEqual(opp.status, 'OPEN')
        self.assertEqual(opp.category, 'SCHOLARSHIP')
        self.assertEqual(str(opp.deadline), FUTURE)

    @override_settings(MEDIA_ROOT='/tmp/kpn-test-media')
    def test_news_candidate_with_base64_image_gets_featured_image(self):
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (64, 64), 'green').save(buffer, format='PNG')
        payload = {
            'kind': 'NEWS', 'title': 'Kebbi market reopens',
            'source_url': 'https://example.com/kebbi-market',
            'source_name': 'Example News', 'text': 'A market in Kebbi reopened.',
            'draft': {'title': 'Kebbi market reopens', 'body': 'A market in Kebbi reopened.',
                      'category': 'MARKETS',
                      'image_base64': base64.b64encode(buffer.getvalue()).decode()}}
        response = self._post_candidate(payload)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['published'])
        self.assertEqual(response.json()['image_warning'], '')
        article = Campaign.objects.get(slug=response.json()['slug'])
        self.assertTrue(article.featured_image)

    def test_broken_image_url_does_not_block_publishing(self):
        payload = {
            'kind': 'NEWS', 'title': 'Kebbi school wins prize',
            'source_url': 'https://example.com/kebbi-school',
            'source_name': 'Example News', 'text': 'A school in Kebbi won a prize.',
            'draft': {'title': 'Kebbi school wins prize', 'body': 'A school in Kebbi won a prize.',
                      'category': 'EDUCATION',
                      'image_url': 'https://example.com/missing.png'}}
        with mock.patch.object(publish.requests, 'get', side_effect=RuntimeError('boom')):
            response = self._post_candidate(payload)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['published'])
        self.assertEqual(response.json()['image_warning'], 'image_download_failed')
        article = Campaign.objects.get(slug=response.json()['slug'])
        self.assertFalse(article.featured_image)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN,
                   KPN_EDITORIAL_AUTO_PUBLISH=True)
class PublishItemRescueTests(TestCase):
    def test_publish_item_repairs_stuck_opportunity(self):
        # A legacy stuck item: stored draft has the old broken values.
        item = opp_item(draft={'title': 'NNPC Scholarship', 'body': 'Body',
                               'provider': 'NNPC/SNEPCo', 'category': 'GENERAL',
                               'application_link': 'https://example.com/apply',
                               'deadline': '30 November 2026'})
        # Without corrections it still fails validation.
        response = self.client.post(reverse('editorial:brain_publish_item'),
                                    data=json.dumps({'item_id': item.pk}),
                                    content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 400)
        # With corrections it publishes.
        response = self.client.post(
            reverse('editorial:brain_publish_item'),
            data=json.dumps({'item_id': item.pk,
                             'draft_overrides': {'category': 'SCHOLARSHIP', 'deadline': FUTURE}}),
            content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['published'])
        item.refresh_from_db()
        self.assertEqual(item.state, 'HANDED_OFF')
        self.assertEqual(Opportunity.objects.get(slug=response.json()['slug']).category, 'SCHOLARSHIP')

    def test_synthetic_item_can_never_publish(self):
        item = Item.objects.create(key='pub-syn', kind='NEWS', title='T', state='REVIEW',
                                   original={'title': 'T', 'text': 'E', 'synthetic': True},
                                   draft={'title': 'T', 'body': 'B', 'category': 'GENERAL'})
        with self.assertRaises(BrainError) as ctx:
            publish.publish_brain_item(item)
        self.assertEqual(ctx.exception.code, 'synthetic_not_publishable')


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN,
                   KPN_EDITORIAL_AUTO_PUBLISH=False)
class PublishItemGateTests(TestCase):
    def test_publish_item_refuses_when_auto_publish_off(self):
        item = opp_item()
        response = self.client.post(reverse('editorial:brain_publish_item'),
                                    data=json.dumps({'item_id': item.pk}),
                                    content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Opportunity.objects.exists())


class DuplicateGuardTests(TestCase):
    def test_conflict_exact_title_different_case_and_punctuation(self):
        Campaign.objects.create(author=media_director('dup_director'), title='Kebbi Youth Wins Big!',
                                slug='dup-1', status='PUBLISHED')
        level, _ = publish.duplicate_conflict('NEWS', 'kebbi youth wins big')
        self.assertEqual(level, 'exact')

    def test_conflict_none_for_unrelated_title(self):
        Campaign.objects.create(author=media_director('dup_director2'), title='Argungu Fishing Festival Dates',
                                slug='dup-2', status='PUBLISHED')
        level, _ = publish.duplicate_conflict('NEWS', 'Zuru Emirate Announces New Palace Museum')
        self.assertEqual(level, '')

    def test_publish_exact_duplicate_dismisses_item_without_second_copy(self):
        director = media_director('dup_director3')
        Campaign.objects.create(author=director, title='Kebbi cyclists celebrate',
                                slug='dup-3', status='PUBLISHED')
        item = Item.objects.create(
            key='dup-item-1', kind='NEWS', title='Kebbi cyclists celebrate', state='REVIEW',
            original={'title': 'Kebbi cyclists celebrate', 'text': 'E'},
            draft={'title': 'Kebbi cyclists celebrate', 'body': 'Body', 'category': 'YOUTH'})
        result = publish.publish_brain_item(item)
        self.assertFalse(result['published'])
        self.assertTrue(result['duplicate'])
        item.refresh_from_db()
        self.assertEqual(item.state, 'DISMISSED')
        self.assertEqual(Campaign.objects.filter(title='Kebbi cyclists celebrate').count(), 1)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN,
                   KPN_EDITORIAL_AUTO_PUBLISH=True)
class DuplicateCandidateApiTests(TestCase):
    def setUp(self):
        media_director('dup_api_director')

    def _post(self, payload):
        return self.client.post(reverse('editorial:brain_submit_item'),
                                data=json.dumps(payload), content_type='application/json', **AUTH)

    def _news_payload(self, url):
        return {'kind': 'NEWS', 'title': 'Kebbi cyclists celebrate a big win',
                'source_url': url, 'source_name': 'Example', 'text': 'Cyclists in Kebbi celebrated.',
                'draft': {'title': 'Kebbi cyclists celebrate a big win',
                          'body': 'Cyclists in Kebbi celebrated.', 'category': 'YOUTH'}}

    def test_same_story_from_another_source_rejected(self):
        first = self._post(self._news_payload('https://example.com/first-report'))
        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()['published'])
        second = self._post(self._news_payload('https://other.example.net/second-report'))
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()['code'], 'duplicate_candidate')
        self.assertEqual(Campaign.objects.count(), 1)

    def test_opportunity_with_same_application_link_rejected(self):
        Opportunity.objects.create(
            title='Existing Scholarship', slug='existing-scholarship', category='SCHOLARSHIP',
            provider='Trust', description='d', application_link='https://example.com/apply-portal',
            status='OPEN')
        payload = {'kind': 'OPPORTUNITY', 'title': 'A Different Listing Of The Same Scholarship',
                   'source_url': 'https://example.com/apply-portal',
                   'source_name': 'Example', 'text': 'Scholarship listing.',
                   'draft': {'title': 'A Different Listing Of The Same Scholarship', 'body': 'Apply.',
                             'provider': 'Trust', 'category': 'SCHOLARSHIP',
                             'application_link': 'https://example.com/apply-portal',
                             'deadline': FUTURE}}
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'duplicate_candidate')
        self.assertEqual(Opportunity.objects.count(), 1)

    def test_published_endpoint_lists_live_content(self):
        self._post(self._news_payload('https://example.com/listed-report'))
        response = self.client.get(reverse('editorial:brain_published'), **AUTH)
        self.assertEqual(response.status_code, 200)
        titles = [row['title'] for row in response.json()['articles']]
        self.assertIn('Kebbi cyclists celebrate a big win', titles)
        response = self.client.get(reverse('editorial:brain_published'))
        self.assertEqual(response.status_code, 401)


class EditorArticlePowersTests(TestCase):
    def setUp(self):
        self.director = media_director('pw_director')
        self.writer = make_user('pw_writer', title='Ward Coordinator', role='WARD',
                                first_name='Writer', last_name='Person')
        self.article = Campaign.objects.create(
            author=self.writer, title='Live story', slug='live-story',
            status='PUBLISHED', content='Body text', reporter_credit='KPN_EDITORIAL')

    def test_director_can_edit_published_article_and_it_stays_published(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('campaigns:edit_article', args=[self.article.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('campaigns:edit_article', args=[self.article.pk]), {
            'title': 'Live story corrected', 'subheadline': '', 'category': 'GENERAL',
            'verification_status': 'DEVELOPING', 'reporter_credit': 'KPN_EDITORIAL',
            'location': '', 'meta_description': '', 'content_json': ''})
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Live story corrected')
        self.assertEqual(self.article.status, 'PUBLISHED')

    def test_writer_cannot_edit_published_article(self):
        self.client.force_login(self.writer)
        response = self.client.get(reverse('campaigns:edit_article', args=[self.article.pk]))
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Live story')

    def test_director_can_delete_published_article(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('campaigns:delete_article', args=[self.article.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Campaign.objects.filter(pk=self.article.pk).exists())

    def test_writer_cannot_delete_published_article(self):
        own = Campaign.objects.create(author=self.writer, title='Mine', slug='mine-live',
                                      status='PUBLISHED', content='x')
        self.client.force_login(self.writer)
        self.client.post(reverse('campaigns:delete_article', args=[own.pk]))
        self.assertTrue(Campaign.objects.filter(pk=own.pk).exists())

    def test_public_article_page_shows_editorial_team_not_author(self):
        response = self.client.get(reverse('campaigns:article_detail', args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'KPN Editorial Team')
        self.assertNotContains(response, self.writer.get_full_name())
