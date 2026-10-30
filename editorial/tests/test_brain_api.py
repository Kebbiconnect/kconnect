import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from editorial.models import Audit, Item

TOKEN = 'test-brain-token-with-at-least-32-characters'
AUTH = {'HTTP_AUTHORIZATION': f'Bearer {TOKEN}'}


def make_item(**kw):
    defaults = dict(key='api-1', kind='NEWS', title='API story',
                    original={'title': 'API story', 'text': 'Evidence text'})
    defaults.update(kw)
    return Item.objects.create(**defaults)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN)
class BrainApiTests(TestCase):
    def test_missing_token_header_is_401(self):
        response = self.client.get(reverse('editorial:brain_outbox'))
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_is_401(self):
        response = self.client.get(reverse('editorial:brain_outbox'),
                                   HTTP_AUTHORIZATION='Bearer wrong-token-value')
        self.assertEqual(response.status_code, 401)

    def test_outbox_returns_waiting_items(self):
        make_item()
        response = self.client.get(reverse('editorial:brain_outbox'), **AUTH)
        self.assertEqual(response.status_code, 200)
        rows = response.json()['items']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'API story')
        self.assertTrue(Audit.objects.filter(action='BRAIN_OUTBOX_READ').exists())

    def test_inbox_accepts_valid_draft(self):
        item = make_item()
        payload = [{'item_id': item.pk, 'version': item.version,
                    'draft': {'title': 'API story', 'body': 'Drafted via the API.'}}]
        response = self.client.post(reverse('editorial:brain_inbox'),
                                    data=json.dumps(payload), content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 200)
        result = response.json()['results'][0]
        self.assertEqual(result['status'], 'accepted')
        item.refresh_from_db()
        self.assertEqual(item.state, 'REVIEW')
        self.assertTrue(Audit.objects.filter(action='CLAUDE_DRAFT_READY').exists())

    def test_inbox_reports_rejections_without_failing(self):
        item = make_item()
        payload = [{'item_id': item.pk, 'version': item.version + 5,
                    'draft': {'title': 'X', 'body': 'Y'}},
                   {'item_id': item.pk, 'version': item.version,
                    'draft': {'title': 'API story', 'body': 'Good one.'}}]
        response = self.client.post(reverse('editorial:brain_inbox'),
                                    data=json.dumps(payload), content_type='application/json', **AUTH)
        results = response.json()['results']
        self.assertEqual(results[0]['status'], 'rejected')
        self.assertEqual(results[0]['code'], 'item_changed_reload')
        self.assertEqual(results[1]['status'], 'accepted')

    def test_inbox_rejects_invalid_json(self):
        response = self.client.post(reverse('editorial:brain_inbox'),
                                    data='not json', content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 400)

    def test_test_item_creates_synthetic_waiting_item(self):
        response = self.client.post(reverse('editorial:brain_test_item'), **AUTH)
        self.assertEqual(response.status_code, 201)
        item = Item.objects.get(pk=response.json()['item_id'])
        self.assertTrue(item.original['synthetic'])
        self.assertEqual(item.state, 'WAITING')

    def test_inbox_does_not_publish_while_auto_publish_is_off(self):
        # Default (owner flag off): a brain draft only ever reaches REVIEW.
        item = make_item()
        payload = [{'item_id': item.pk, 'version': item.version,
                    'draft': {'title': 'API story', 'body': 'Body.'}}]
        self.client.post(reverse('editorial:brain_inbox'),
                         data=json.dumps(payload), content_type='application/json', **AUTH)
        item.refresh_from_db()
        self.assertEqual(item.state, 'REVIEW')
        self.assertIsNone(item.article_id)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN='')
class BrainApiUnconfiguredTests(TestCase):
    def test_endpoints_do_not_exist_without_token(self):
        response = self.client.get(reverse('editorial:brain_outbox'), **AUTH)
        self.assertEqual(response.status_code, 404)


@override_settings(KPN_EDITORIAL_ENABLED=False, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN)
class BrainApiDisabledTests(TestCase):
    def test_editorial_disabled_is_503(self):
        response = self.client.get(reverse('editorial:brain_outbox'), **AUTH)
        self.assertEqual(response.status_code, 503)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN)
class SubmitItemApiTests(TestCase):
    def _payload(self, **over):
        payload = {
            'kind': 'NEWS',
            'title': 'Kebbi cyclist earns Guinness World Record',
            'source_url': 'https://www.channelstv.com/2026/10/29/young-nigerian-cyclist/',
            'source_name': 'Channels TV',
            'text': 'A young cyclist from Kebbi State earned Guinness World Records recognition.',
            'draft': {'title': 'Kebbi cyclist earns Guinness World Record',
                      'body': 'A young cyclist from Kebbi State has earned Guinness World Records recognition.'},
        }
        payload.update(over)
        return payload

    def _post(self, payload):
        return self.client.post(reverse('editorial:brain_submit_item'),
                                data=json.dumps(payload), content_type='application/json', **AUTH)

    def test_candidate_lands_in_review_with_audit(self):
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 201)
        item = Item.objects.get(pk=response.json()['item_id'])
        self.assertEqual(item.state, 'REVIEW')
        self.assertEqual(item.original['found_by'], 'claude-external-search')
        self.assertTrue(item.audit.filter(action='CLAUDE_DRAFT_READY').exists())

    def test_duplicate_source_url_rejected(self):
        self.assertEqual(self._post(self._payload()).status_code, 201)
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'duplicate_candidate')
        self.assertEqual(Item.objects.count(), 1)

    def test_http_source_url_rejected(self):
        response = self._post(self._payload(source_url='http://example.com/story'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'invalid_source_url')

    def test_opportunity_candidate_with_evidence_link(self):
        payload = self._payload(
            kind='OPPORTUNITY', title='LCA Scholarship 2026',
            source_url='https://www.afterschoolafrica.com/100124/liberty-career-academy-scholarships/',
            text='Liberty Career Academy scholarships, deadline 3 November 2026.',
            draft={'title': 'LCA Scholarship 2026', 'body': 'Scholarships for Nigerian students.',
                   'provider': 'Liberty Career Academy', 'category': 'SCHOLARSHIP',
                   'deadline': '2026-11-03',
                   'application_link': 'https://www.afterschoolafrica.com/100124/liberty-career-academy-scholarships/'})
        response = self._post(payload)
        self.assertEqual(response.status_code, 201)
        item = Item.objects.get(pk=response.json()['item_id'])
        self.assertEqual(item.kind, 'OPPORTUNITY')

    def test_candidate_requires_auth(self):
        response = self.client.post(reverse('editorial:brain_submit_item'),
                                    data=json.dumps(self._payload()), content_type='application/json')
        self.assertEqual(response.status_code, 401)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN)
class TelegramKbApiTests(TestCase):
    def test_proposals_are_created_inactive(self):
        from telegram_integration.models import BotKnowledgeBase
        payload = {'entries': [{'topic': 'KPN Membership',
                                'content': 'How to join KPN and what members do.'}]}
        response = self.client.post(reverse('editorial:brain_telegram_kb'),
                                    data=json.dumps(payload), content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 201)
        row = BotKnowledgeBase.objects.get(pk=response.json()['created_inactive'][0])
        self.assertFalse(row.is_active)
        self.assertTrue(Audit.objects.filter(action='BRAIN_KB_PROPOSED').exists())

    def test_malformed_entry_rejected(self):
        payload = {'entries': [{'topic': '', 'content': 'x'}]}
        response = self.client.post(reverse('editorial:brain_telegram_kb'),
                                    data=json.dumps(payload), content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 400)


@override_settings(KPN_EDITORIAL_ENABLED=True, KPN_EDITORIAL_BRAIN_TOKEN=TOKEN)
class TelegramControlApiTests(TestCase):
    def test_post_announcement_sends_and_audits(self):
        from telegram_integration import brain_service
        from telegram_integration.models import BotOutbox
        with mock.patch.object(brain_service, 'send_telegram_message',
                               return_value={'ok': True, 'result': {'message_id': 7}}):
            response = self.client.post(reverse('editorial:brain_telegram_post'),
                                        data=json.dumps({'text': 'KPN general meeting on Saturday.'}),
                                        content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['sent'])
        self.assertTrue(BotOutbox.objects.filter(kind='ANNOUNCEMENT', state='SENT').exists())
        self.assertTrue(Audit.objects.filter(action='BRAIN_TELEGRAM_POST').exists())

    def test_post_requires_text(self):
        response = self.client.post(reverse('editorial:brain_telegram_post'),
                                    data=json.dumps({'text': '  '}),
                                    content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 400)

    def test_questions_listed_and_answered(self):
        from telegram_integration import brain_service
        from telegram_integration.models import BrainQuestion
        q = BrainQuestion.objects.create(telegram_user_id=909, question='How do I join KPN?')
        response = self.client.get(reverse('editorial:brain_telegram_questions'), **AUTH)
        self.assertEqual([r['id'] for r in response.json()['questions']], [q.pk])
        with mock.patch.object(brain_service, 'send_telegram_message',
                               return_value={'ok': True, 'result': {'message_id': 9}}):
            response = self.client.post(reverse('editorial:brain_telegram_answer'),
                                        data=json.dumps({'question_id': q.pk, 'answer': 'Fill the membership form.'}),
                                        content_type='application/json', **AUTH)
        self.assertEqual(response.json()['state'], 'SENT')
        response = self.client.get(reverse('editorial:brain_telegram_questions'), **AUTH)
        self.assertEqual(response.json()['questions'], [])

    def test_telegram_endpoints_require_auth(self):
        response = self.client.get(reverse('editorial:brain_telegram_questions'))
        self.assertEqual(response.status_code, 401)
