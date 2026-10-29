from django.test import TestCase, override_settings

from campaigns.models import Campaign
from core.models import CommunityReport, Report
from editorial import brain
from editorial.brain import BrainError
from editorial.models import Audit, Item, Job
from editorial.tests.helpers import make_user


def news_item(**kw):
    defaults = dict(key='brain-news-1', kind='NEWS', title='Original headline',
                    source_url='https://example.com/story',
                    original={'title': 'Original headline', 'text': 'Evidence text from the source.'})
    defaults.update(kw)
    item = Item.objects.create(**defaults)
    Job.objects.create(key='generate:' + defaults['key'], kind='GENERATE', item=item)
    return item


class WaitingItemsTests(TestCase):
    def test_lists_waiting_news_with_allowed_fields(self):
        item = news_item()
        rows = brain.waiting_items()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['item_id'], item.pk)
        self.assertEqual(rows[0]['version'], item.version)
        self.assertIn('body', rows[0]['allowed_fields'])

    def test_review_items_are_not_exported(self):
        news_item()
        Item.objects.create(key='done-1', kind='NEWS', title='Already drafted', state='REVIEW')
        self.assertEqual(len(brain.waiting_items()), 1)

    def test_limit_is_respected(self):
        for i in range(3):
            news_item(key=f'brain-news-{i}', title=f'Item {i}')
        self.assertEqual(len(brain.waiting_items(limit=2)), 2)

    @override_settings(KPN_EDITORIAL_REPORT_DRAFTING_ENABLED=False)
    def test_report_items_hidden_until_owner_enables(self):
        author = make_user('brain_author', title=None, role='LGA')
        boss = make_user('brain_boss', title='President')
        report = Report.objects.create(title='R', report_type='WARD_TO_LGA', content='C',
                                       submitted_by=author, submitted_to=boss, status='SUBMITTED')
        Item.objects.create(key='brain-rep-1', kind='REPORT_EDIT', title='R', report=report,
                            original={'title': 'R', 'content': 'Reach me on 08031234567 or a@b.com'})
        self.assertEqual(brain.waiting_items(), [])

    @override_settings(KPN_EDITORIAL_REPORT_DRAFTING_ENABLED=True)
    def test_report_items_exported_with_contacts_redacted(self):
        author = make_user('brain_author2', title=None, role='LGA')
        boss = make_user('brain_boss2', title='President')
        report = Report.objects.create(title='R', report_type='WARD_TO_LGA', content='C',
                                       submitted_by=author, submitted_to=boss, status='SUBMITTED')
        Item.objects.create(key='brain-rep-2', kind='REPORT_EDIT', title='R', report=report,
                            original={'title': 'R', 'content': 'Reach me on 08031234567 or a@b.com'})
        rows = brain.waiting_items()
        self.assertEqual(len(rows), 1)
        exported = rows[0]['original']['content']
        self.assertNotIn('08031234567', exported)
        self.assertNotIn('a@b.com', exported)


class SubmitDraftTests(TestCase):
    def test_news_draft_accepted_and_job_closed(self):
        item = news_item()
        result = brain.submit_draft(item.pk, {'title': 'New headline', 'body': 'Draft body.', 'category': 'GENERAL'}, item.version)
        result.refresh_from_db()
        self.assertEqual(result.state, 'REVIEW')
        self.assertEqual(result.title, 'New headline')
        self.assertEqual(result.version, item.version + 1)
        self.assertEqual(Job.objects.get(item=result).state, 'DONE')
        self.assertTrue(Audit.objects.filter(item=result, action='CLAUDE_DRAFT_READY').exists())

    def test_wrong_version_rejected(self):
        item = news_item()
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'T', 'body': 'B'}, item.version + 5)
        self.assertEqual(ctx.exception.code, 'item_changed_reload')
        item.refresh_from_db()
        self.assertEqual(item.state, 'WAITING')

    def test_missing_item_rejected(self):
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(99999, {'title': 'T', 'body': 'B'}, 1)
        self.assertEqual(ctx.exception.code, 'item_not_found')

    def test_already_reviewed_item_rejected(self):
        item = news_item(state='REVIEW')
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'T', 'body': 'B'}, item.version)
        self.assertEqual(ctx.exception.code, 'item_not_waiting')

    def test_unknown_field_rejected(self):
        item = news_item()
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'T', 'body': 'B', 'publish_now': 'yes'}, item.version)
        self.assertEqual(ctx.exception.code, 'invalid_draft_fields')

    def test_missing_body_rejected(self):
        item = news_item()
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'T', 'body': '  '}, item.version)
        self.assertEqual(ctx.exception.code, 'missing_draft_content')

    def test_oversized_value_rejected(self):
        item = news_item()
        with self.assertRaises(BrainError):
            brain.submit_draft(item.pk, {'title': 'T', 'body': 'x' * 20001}, item.version)

    def test_opportunity_link_must_come_from_evidence(self):
        item = Item.objects.create(
            key='brain-opp-1', kind='OPPORTUNITY', title='Opp',
            source_url='https://example.com/opp',
            original={'title': 'Opp', 'text': 'Details', 'source_url': 'https://example.com/opp',
                      'application_links': [{'url': 'https://example.com/apply', 'label': 'Apply'}]})
        draft = {'title': 'Opp', 'body': 'Body', 'provider': 'NGO', 'category': 'JOB',
                 'application_link': 'https://unknown.example.net/apply', 'deadline': ''}
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, draft, item.version)
        self.assertEqual(ctx.exception.code, 'unsupported_application_link')
        draft['application_link'] = 'https://example.com/apply'
        result = brain.submit_draft(item.pk, draft, item.version)
        self.assertEqual(result.state, 'REVIEW')

    def test_caption_too_long_rejected(self):
        author = make_user('cap_author', title='President')
        article = Campaign.objects.create(author=author, title='Pub', slug='pub-1', status='PUBLISHED')
        item = Item.objects.create(key='brain-cap-1', kind='CAPTION', title='Pub', article=article,
                                   original={'title': 'Pub', 'text': 'x'})
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'Pub', 'body': 'y' * 1001}, item.version)
        self.assertEqual(ctx.exception.code, 'caption_too_long')

    def test_caption_for_unpublished_article_rejected(self):
        author = make_user('cap_author2', title='President')
        article = Campaign.objects.create(author=author, title='Draft', slug='draft-1', status='DRAFT')
        item = Item.objects.create(key='brain-cap-2', kind='CAPTION', title='Draft', article=article,
                                   original={'title': 'Draft', 'text': 'x'})
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'Draft', 'body': 'Short'}, item.version)
        self.assertEqual(ctx.exception.code, 'article_not_published')

    @override_settings(KPN_EDITORIAL_REPORT_DRAFTING_ENABLED=False)
    def test_report_draft_rejected_while_owner_has_not_enabled(self):
        author = make_user('brain_author3', title=None, role='LGA')
        boss = make_user('brain_boss3', title='President')
        report = Report.objects.create(title='R', report_type='WARD_TO_LGA', content='Original wording',
                                       submitted_by=author, submitted_to=boss, status='SUBMITTED')
        item = Item.objects.create(key='brain-rep-3', kind='REPORT_EDIT', title='R', report=report,
                                   original={'title': 'R', 'content': 'Original wording'})
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'R', 'content': 'Improved wording'}, item.version)
        self.assertEqual(ctx.exception.code, 'report_drafting_not_enabled')

    @override_settings(KPN_EDITORIAL_REPORT_DRAFTING_ENABLED=True)
    def test_stale_report_draft_rejected(self):
        author = make_user('brain_author4', title=None, role='LGA')
        boss = make_user('brain_boss4', title='President')
        report = Report.objects.create(title='R', report_type='WARD_TO_LGA', content='Original wording',
                                       submitted_by=author, submitted_to=boss, status='SUBMITTED')
        item = Item.objects.create(key='brain-rep-4', kind='REPORT_EDIT', title='R', report=report,
                                   original={'title': 'R', 'content': 'Original wording'})
        report.content = 'Changed after export'
        report.save(update_fields=['content'])
        with self.assertRaises(BrainError) as ctx:
            brain.submit_draft(item.pk, {'title': 'R', 'content': 'Improved wording'}, item.version)
        self.assertEqual(ctx.exception.code, 'stale_report')
