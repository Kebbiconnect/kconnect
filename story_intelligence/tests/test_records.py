"""Story records: updates, claims + verification history, corrections."""
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from story_intelligence.models import (
    Claim, Correction, StoryAudit, StoryUpdate, VerificationEvent,
)
from story_intelligence.services import (
    set_article_verification_status, set_claim_status, story_panel_context,
)


class RecordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('rec_editor')

    def setUp(self):
        self.article = Campaign.objects.create(
            author=self.editor, title='Record Story', slug='record-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00100')

    def test_published_updates_only_in_panel_in_order(self):
        StoryUpdate.objects.create(
            article=self.article, title='First Update', body='One',
            status='PUBLISHED', published_at=timezone.now(), author=self.editor)
        StoryUpdate.objects.create(
            article=self.article, title='Draft Update', body='Hidden',
            status='DRAFT', author=self.editor)
        StoryUpdate.objects.create(
            article=self.article, title='Second Update', body='Two',
            status='PUBLISHED', published_at=timezone.now(), author=self.editor)
        panel = story_panel_context(self.article)
        self.assertEqual([u.title for u in panel['updates']],
                         ['First Update', 'Second Update'])

    def test_claim_status_change_writes_verification_event_and_audit(self):
        claim = Claim.objects.create(
            article=self.article, text='The bridge is complete.',
            status='OFFICIAL_STATEMENT', noted_by=self.editor)
        set_claim_status(claim, 'DISPUTED', self.editor, reason='Residents disagree')
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'DISPUTED')
        event = VerificationEvent.objects.get(claim=claim)
        self.assertEqual(event.field, 'claim_status')
        self.assertEqual(event.old_value, 'OFFICIAL_STATEMENT')
        self.assertEqual(event.new_value, 'DISPUTED')
        self.assertEqual(event.reason, 'Residents disagree')
        self.assertTrue(StoryAudit.objects.filter(
            action='CLAIM_STATUS_CHANGED', target_id=claim.pk).exists())

    def test_official_statement_is_not_labelled_confirmed(self):
        official = Claim(article=self.article, text='x', status='OFFICIAL_STATEMENT')
        confirmed = Claim(article=self.article, text='y', status='CONFIRMED')
        self.assertIn('not independently verified', official.status_label())
        self.assertEqual(confirmed.status_label(), 'Confirmed by KPN')
        self.assertNotEqual(official.status_label(), confirmed.status_label())

    def test_article_verification_change_writes_event(self):
        set_article_verification_status(self.article, 'VERIFIED', self.editor)
        self.article.refresh_from_db()
        self.assertEqual(self.article.verification_status, 'VERIFIED')
        event = VerificationEvent.objects.get(article=self.article)
        self.assertEqual(event.old_value, 'DEVELOPING')
        self.assertEqual(event.new_value, 'VERIFIED')

    def test_correction_links_to_update_and_claim(self):
        update = StoryUpdate.objects.create(
            article=self.article, title='Upd', body='B', status='PUBLISHED',
            published_at=timezone.now(), author=self.editor)
        claim = Claim.objects.create(
            article=self.article, text='A claim', status='DEVELOPING',
            noted_by=self.editor)
        correction = Correction.objects.create(
            article=self.article, update=update, claim=claim,
            kind='CORRECTION', text='The figure was 40, not 400.',
            created_by=self.editor)
        self.assertEqual(correction.update, update)
        self.assertEqual(correction.claim, claim)
        self.assertIn(correction, list(update.corrections.all()))
        self.assertIn(correction, list(claim.corrections.all()))
        panel = story_panel_context(self.article)
        self.assertEqual([c.text for c in panel['corrections']],
                         ['The figure was 40, not 400.'])

    def test_panel_is_none_without_story_data(self):
        plain = Campaign.objects.create(
            author=self.editor, title='Plain Story', slug='plain-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now())
        self.assertIsNone(story_panel_context(plain))
