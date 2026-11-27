"""Section 26 (27 Nov 2026): brain LGA tagging for news, and the new
SIGNAL candidate kind for the Future Signal page."""
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from intelligence.models import ArticleLocation
from leadership.models import LGA, Zone

TOKEN = 'section26-test-token'
AUTH = {'HTTP_AUTHORIZATION': f'Bearer {TOKEN}'}


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN,
                   KPN_EDITORIAL_AUTO_PUBLISH=True)
class BrainSection26Tests(TestCase):
    def setUp(self):
        self.director = media_director('s26_director')
        self.zone = Zone.objects.create(name='Kebbi Central')
        self.lga = LGA.objects.create(name='Birnin Kebbi', zone=self.zone)

    def _post(self, payload):
        return self.client.post(reverse('editorial:brain_submit_item'),
                                data=json.dumps(payload), content_type='application/json', **AUTH)

    def test_news_candidate_with_lga_links_article_to_lga(self):
        response = self._post({
            'kind': 'NEWS', 'title': 'Birnin Kebbi market reopens after repairs',
            'source_url': 'https://example.com/bk-market',
            'source_name': 'Example News', 'text': 'The market in Birnin Kebbi reopened.',
            'draft': {'title': 'Birnin Kebbi market reopens after repairs',
                      'body': 'The central market in Birnin Kebbi reopened on Monday.',
                      'category': 'MARKETS', 'lga': 'birnin kebbi'}})
        self.assertEqual(response.status_code, 201, response.content[:400])
        body = response.json()
        self.assertTrue(body['published'])
        article = Campaign.objects.get(slug=body['slug'])
        self.assertEqual(article.lga, self.lga)
        self.assertTrue(ArticleLocation.objects.filter(article=article, lga=self.lga).exists())

    def test_news_candidate_with_unknown_lga_rejected(self):
        response = self._post({
            'kind': 'NEWS', 'title': 'A story from somewhere else entirely',
            'source_url': 'https://example.com/nowhere',
            'source_name': 'Example News', 'text': 'A story.',
            'draft': {'title': 'A story from somewhere else entirely',
                      'body': 'Body text.', 'category': 'GENERAL', 'lga': 'Atlantis'}})
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid_lga', response.content.decode())
        self.assertFalse(Campaign.objects.filter(title='A story from somewhere else entirely').exists())

    def _signal_payload(self, **draft_overrides):
        draft = {
            'title': 'Dry season water pressure is building across Kebbi',
            'body': 'Borehole queues are lengthening in several communities as the dry season deepens.',
            'category': 'ENVIRONMENT',
            'signal_category': 'HEALTH_SOCIAL',
            'signal_confidence': 'DEVELOPING',
            'signal_observation': 'Longer borehole queues reported in multiple LGAs this month.',
            'signal_horizon': 'the coming dry season',
            'who_is_affected': 'Rural households that depend on public boreholes.',
            'why_it_matters': 'Water pressure affects health, schooling and farm work.',
            'what_is_unknown': 'Whether the queues reflect demand growth or pump failures.',
            'signal_change_condition': 'New borehole repairs or a verified supply survey.',
            'what_to_watch': 'Repair announcements and community reports over the next month.',
        }
        draft.update(draft_overrides)
        return {
            'kind': 'SIGNAL', 'title': draft['title'],
            'source_url': 'https://example.com/kebbi-water-signal',
            'source_name': 'Example News', 'text': 'Reports of longer borehole queues.',
            'draft': draft}

    def test_signal_candidate_publishes_as_future_signal(self):
        response = self._post(self._signal_payload())
        self.assertEqual(response.status_code, 201, response.content[:400])
        body = response.json()
        self.assertTrue(body['published'])
        self.assertEqual(body['kind'], 'SIGNAL')
        article = Campaign.objects.get(slug=body['slug'])
        profile = article.story_profile
        self.assertEqual(profile.kind, 'SIGNAL')
        self.assertEqual(profile.signal_category, 'HEALTH_SOCIAL')
        self.assertEqual(profile.signal_confidence, 'DEVELOPING')
        self.assertIn('borehole queues', profile.signal_observation)
        listing = self.client.get('/api/v1/signals/')
        self.assertEqual(listing.status_code, 200)
        titles = [row['title'] for row in listing.json()['results']]
        self.assertIn('Dry season water pressure is building across Kebbi', titles)

    def test_signal_without_observation_rejected(self):
        payload = self._signal_payload()
        del payload['draft']['signal_observation']
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('missing_signal_observation', response.content.decode())

    def test_signal_with_unknown_theme_rejected(self):
        payload = self._signal_payload(signal_category='NOT_A_THEME')
        payload['source_url'] = 'https://example.com/kebbi-water-signal-2'
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid_signal_category', response.content.decode())

    def _voice_payload(self, **draft_overrides):
        import base64
        import io

        from PIL import Image

        out = io.BytesIO()
        Image.new('RGB', (32, 32), 'white').save(out, 'PNG')
        draft = {
            'title': 'Voice: youth on jobs in Birnin Kebbi',
            'body': '"We are ready to work. What we need in Birnin Kebbi is a chance to prove it."',
            'category': 'YOUTH',
            'author': 'Aisha Bello (@aishabello)',
            'platform': 'FACEBOOK',
            'location_details': 'Birnin Kebbi, Kebbi State',
            'lga': 'Birnin Kebbi',
            'why_it_matters': 'Youth employment is a standing civic concern in the state capital.',
            'image_base64': base64.b64encode(out.getvalue()).decode(),
        }
        draft.update(draft_overrides)
        return {
            'kind': 'VOICE', 'title': draft['title'],
            'source_url': 'https://facebook.com/example/posts/123',
            'source_name': 'Facebook', 'text': 'Screenshot of the original post.',
            'draft': draft}

    def test_voice_candidate_publishes_to_community_voice(self):
        from core.models import CommunityReport

        response = self._post(self._voice_payload())
        self.assertEqual(response.status_code, 201, response.content[:400])
        body = response.json()
        self.assertTrue(body['published'])
        self.assertEqual(body['kind'], 'VOICE')
        report = CommunityReport.objects.get(published_to_voice=True)
        self.assertEqual(report.status, 'APPROVED')
        self.assertIn('ready to work', report.what_happened)
        self.assertIn('Aisha Bello', report.who_was_involved)
        self.assertIn('Facebook', report.who_was_involved)
        self.assertEqual(report.lga, self.lga)
        self.assertTrue(report.evidence_image)
        self.assertIn('facebook.com/example/posts/123', report.internal_notes)
        listing = self.client.get('/api/v1/civic/community-voice/')
        self.assertEqual(listing.status_code, 200)
        rows = listing.json()['results']
        self.assertEqual(len(rows), 1)
        self.assertIn('ready to work', rows[0]['what_happened'])
        # Reporter identity is never in the public payload.
        self.assertNotIn('reporter_phone', rows[0])

    def test_voice_without_author_rejected(self):
        payload = self._voice_payload()
        del payload['draft']['author']
        payload['source_url'] = 'https://facebook.com/example/posts/124'
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('missing_voice_author', response.content.decode())

    def test_voice_with_unknown_platform_rejected(self):
        payload = self._voice_payload(platform='TIKTOK')
        payload['source_url'] = 'https://facebook.com/example/posts/125'
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid_voice_platform', response.content.decode())
