from unittest import mock

from django.test import TestCase, override_settings

from campaigns.models import Campaign
from editorial.tests.helpers import make_user
from telegram_integration import brain_service
from telegram_integration.models import BotOutbox, BrainQuestion

OK = {'ok': True, 'result': {'message_id': 42}}
FAIL = {'ok': False, 'error': 'chat not found'}


class OutboxTests(TestCase):
    def test_announcement_send_success(self):
        row = brain_service.enqueue_announcement('Hello KPN')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=OK) as send:
            self.assertTrue(brain_service.send_outbox_row(row))
        send.assert_called_once()
        self.assertEqual(send.call_args[0][0], brain_service.get_channel_id())
        row.refresh_from_db()
        self.assertEqual(row.state, 'SENT')
        self.assertEqual(row.telegram_message_id, 42)

    def test_send_failure_recorded(self):
        row = brain_service.enqueue_announcement('Hello KPN')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=FAIL):
            self.assertFalse(brain_service.send_outbox_row(row))
        row.refresh_from_db()
        self.assertEqual(row.state, 'FAILED')
        self.assertIn('chat not found', row.error)

    def test_drain_sends_queued_only(self):
        brain_service.enqueue_announcement('One')
        brain_service.enqueue_announcement('Two')
        done = BotOutbox.objects.create(kind='CUSTOM', text='Old', state='SENT')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=OK):
            result = brain_service.drain_outbox()
        self.assertEqual(result, {'sent': 2, 'failed': 0})


class ArticleShareTests(TestCase):
    def _article(self, **kw):
        author = make_user('tg_author', title='President')
        defaults = dict(author=author, title='Big KPN story', slug='big-kpn-story',
                        content='Story body', meta_description='A short summary.', status='PUBLISHED')
        defaults.update(kw)
        return Campaign.objects.create(**defaults)

    def test_share_text_has_title_summary_and_link(self):
        article = self._article()
        text = brain_service.article_share_text(article)
        self.assertIn('Big KPN story', text)
        self.assertIn('A short summary.', text)
        self.assertIn('/campaigns/article/big-kpn-story/', text)

    def test_enqueue_share_dedupes(self):
        article = self._article()
        first = brain_service.enqueue_article_share(article)
        second = brain_service.enqueue_article_share(article)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(BotOutbox.objects.filter(kind='ARTICLE').count(), 1)

    @override_settings(KPN_EDITORIAL_ENABLED=True, SITE_URL='https://kpn.com.ng')
    def test_publish_triggers_share_send_once(self):
        author = make_user('tg_author2', title='President')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=OK) as send:
            with self.captureOnCommitCallbacks(execute=True):
                article = Campaign.objects.create(author=author, title='Fresh story', slug='fresh-story',
                                                  content='Body', status='DRAFT')
                article.status = 'PUBLISHED'
                article.save(update_fields=['status'])
            self.assertEqual(send.call_count, 1)
            with self.captureOnCommitCallbacks(execute=True):
                article.title = 'Fresh story (updated)'
                article.save(update_fields=['title'])
            self.assertEqual(send.call_count, 1)
        self.assertEqual(BotOutbox.objects.filter(kind='ARTICLE', state='SENT').count(), 1)

    @override_settings(KPN_EDITORIAL_ENABLED=False)
    def test_publish_shares_nothing_while_brain_disabled(self):
        author = make_user('tg_author3', title='President')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=OK) as send:
            with self.captureOnCommitCallbacks(execute=True):
                Campaign.objects.create(author=author, title='Quiet story', slug='quiet-story',
                                        content='Body', status='PUBLISHED')
        send.assert_not_called()
        self.assertEqual(BotOutbox.objects.count(), 0)


class BrainQuestionTests(TestCase):
    def test_answer_delivered_and_marked_sent(self):
        q = brain_service.queue_question(555, 'How do I join KPN?')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=OK) as send:
            brain_service.answer_question(q, 'Visit the office in Birnin Kebbi.')
        self.assertEqual(send.call_args[0][0], '555')
        q.refresh_from_db()
        self.assertEqual(q.state, 'SENT')
        self.assertTrue(BotOutbox.objects.filter(kind='ANSWER', state='SENT').exists())

    def test_answer_failure_marks_question_failed(self):
        q = brain_service.queue_question(556, 'When is the meeting?')
        with mock.patch.object(brain_service, 'send_telegram_message', return_value=FAIL):
            brain_service.answer_question(q, 'Saturday 10am.')
        q.refresh_from_db()
        self.assertEqual(q.state, 'FAILED')

    def test_escalation_reply_when_no_providers(self):
        from telegram_integration.ai import ask_kpn_assistant
        with mock.patch('telegram_integration.ai.get_db_provider_order', return_value=[]), \
             mock.patch('telegram_integration.ai.get_env_provider_order', return_value=[]):
            reply = ask_kpn_assistant('What is KPN membership about?', telegram_user_id=777)
        self.assertIn('passed your question', reply)
        self.assertTrue(BrainQuestion.objects.filter(telegram_user_id=777, state='QUEUED').exists())
