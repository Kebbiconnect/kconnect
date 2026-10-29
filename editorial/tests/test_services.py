from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign
from core.models import Opportunity, Report
from editorial.models import Item
from editorial.services import act, save_review
from editorial.tests.helpers import assistant_media, make_user, media_director


class SaveReviewTests(TestCase):
    def setUp(self):
        self.director = media_director()
        self.item = Item.objects.create(key='svc-1', kind='NEWS', title='T', state='WAITING')

    def test_save_review_updates_draft_and_version(self):
        saved = save_review(self.director, self.item.pk, {'title': 'Edited', 'body': 'Text'}, self.item.version)
        self.assertEqual(saved.state, 'REVIEW')
        self.assertEqual(saved.draft['body'], 'Text')
        self.assertEqual(saved.version, self.item.version + 1)
        self.assertEqual(saved.reviewed_by, self.director)

    def test_save_review_version_conflict(self):
        with self.assertRaises(ValidationError):
            save_review(self.director, self.item.pk, {'title': 'X', 'body': 'Y'}, self.item.version + 3)

    def test_save_review_unknown_field_rejected(self):
        with self.assertRaises(ValidationError):
            save_review(self.director, self.item.pk, {'title': 'X', 'evil': 'Y'}, self.item.version)

    def test_member_cannot_save_review(self):
        from django.core.exceptions import PermissionDenied
        member = make_user('svc_member', title=None, role='GENERAL')
        with self.assertRaises(PermissionDenied):
            save_review(member, self.item.pk, {'title': 'X', 'body': 'Y'}, self.item.version)


class HandoffTests(TestCase):
    def setUp(self):
        self.director = media_director()

    def _news_item(self, **kw):
        defaults = dict(key='ho-news', kind='NEWS', title='Story', state='REVIEW',
                        original={'title': 'Story', 'text': 'Evidence'},
                        draft={'title': 'Story', 'body': 'First para.\n\nSecond para.', 'category': 'GENERAL'},
                        source_url='https://example.com/story')
        defaults.update(kw)
        return Item.objects.create(**defaults)

    def test_news_handoff_creates_pending_article_not_published(self):
        item = self._news_item()
        result = act(self.director, item.pk, 'handoff', item.version, confirmed=True)
        self.assertEqual(result.state, 'HANDED_OFF')
        article = Campaign.objects.get(pk=result.article_id)
        self.assertEqual(article.status, 'PENDING')
        self.assertEqual(article.author, self.director)
        self.assertIn('Source: https://example.com/story', article.content)

    def test_handoff_requires_confirmation(self):
        item = self._news_item()
        with self.assertRaises(ValidationError):
            act(self.director, item.pk, 'handoff', item.version, confirmed=False)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_synthetic_item_cannot_be_handed_off(self):
        item = self._news_item(original={'title': 'Story', 'text': 'Evidence', 'synthetic': True})
        with self.assertRaises(ValidationError):
            act(self.director, item.pk, 'handoff', item.version, confirmed=True)

    def test_handoff_rejects_unknown_category(self):
        item = self._news_item(draft={'title': 'Story', 'body': 'Body', 'category': 'NOPE'})
        with self.assertRaises(ValidationError):
            act(self.director, item.pk, 'handoff', item.version, confirmed=True)

    def test_dismiss_closes_item(self):
        item = self._news_item()
        result = act(self.director, item.pk, 'dismiss', item.version)
        self.assertEqual(result.state, 'DISMISSED')

    def test_opportunity_handoff_creates_open_opportunity(self):
        item = Item.objects.create(
            key='ho-opp', kind='OPPORTUNITY', title='Grant', state='REVIEW',
            source_url='https://example.com/grant',
            original={'title': 'Grant', 'text': 'Evidence'},
            draft={'title': 'Grant', 'body': 'About the grant', 'provider': 'Federal Govt',
                   'category': 'GRANT', 'application_link': 'https://example.com/apply',
                   'deadline': (timezone.localdate() + timedelta(days=30)).isoformat()})
        result = act(self.director, item.pk, 'handoff', item.version, confirmed=True)
        opp = Opportunity.objects.get(pk=result.opportunity_id)
        self.assertEqual(opp.status, 'OPEN')
        self.assertEqual(opp.provider, 'Federal Govt')

    def test_opportunity_handoff_needs_manage_hubs(self):
        from django.core.exceptions import PermissionDenied
        item = Item.objects.create(
            key='ho-opp-2', kind='OPPORTUNITY', title='Grant', state='REVIEW',
            source_url='https://example.com/grant',
            original={'title': 'Grant', 'text': 'Evidence'},
            draft={'title': 'Grant', 'body': 'About', 'provider': 'NGO', 'category': 'GRANT',
                   'application_link': 'https://example.com/apply', 'deadline': ''})
        with self.assertRaises(PermissionDenied):
            act(assistant_media(), item.pk, 'handoff', item.version, confirmed=True)
        self.assertEqual(Opportunity.objects.count(), 0)

    def test_opportunity_past_deadline_rejected(self):
        item = Item.objects.create(
            key='ho-opp-3', kind='OPPORTUNITY', title='Old grant', state='REVIEW',
            source_url='https://example.com/grant',
            original={'title': 'Old grant', 'text': 'Evidence'},
            draft={'title': 'Old grant', 'body': 'About', 'provider': 'NGO', 'category': 'GRANT',
                   'application_link': 'https://example.com/apply',
                   'deadline': (timezone.localdate() - timedelta(days=1)).isoformat()})
        with self.assertRaises(ValidationError):
            act(self.director, item.pk, 'handoff', item.version, confirmed=True)
        self.assertEqual(Opportunity.objects.count(), 0)


class ApplyReportEditTests(TestCase):
    def setUp(self):
        self.president = make_user('svc_pres', title='President')
        self.author = make_user('svc_author', title=None, role='LGA')
        self.report = Report.objects.create(
            title='Ward report', report_type='WARD_TO_LGA', content='Original wording',
            submitted_by=self.author, submitted_to=self.president, status='SUBMITTED')
        self.item = Item.objects.create(
            key='apply-1', kind='REPORT_EDIT', title='Ward report', state='REVIEW', report=self.report,
            original={'title': 'Ward report', 'content': 'Original wording'},
            draft={'title': 'Ward report', 'content': 'Improved wording'})

    def test_apply_changes_wording_only_and_keeps_status(self):
        result = act(self.president, self.item.pk, 'apply', self.item.version, confirmed=True)
        self.assertEqual(result.state, 'APPLIED')
        self.report.refresh_from_db()
        self.assertEqual(self.report.content, 'Improved wording')
        self.assertEqual(self.report.status, 'SUBMITTED')

    def test_apply_requires_confirmation(self):
        with self.assertRaises(ValidationError):
            act(self.president, self.item.pk, 'apply', self.item.version, confirmed=False)

    def test_apply_blocked_when_report_changed(self):
        self.report.content = 'Someone else edited this'
        self.report.save(update_fields=['content'])
        with self.assertRaises(ValidationError):
            act(self.president, self.item.pk, 'apply', self.item.version, confirmed=True)
        self.report.refresh_from_db()
        self.assertEqual(self.report.content, 'Someone else edited this')
