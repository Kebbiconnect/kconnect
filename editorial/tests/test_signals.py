from django.test import TestCase, override_settings

from campaigns.models import Campaign
from core.models import CommunityReport, Report
from editorial.models import Item, Job
from editorial.tests.helpers import make_user


@override_settings(KPN_EDITORIAL_ENABLED=True)
class ReportSignalTests(TestCase):
    def setUp(self):
        self.author = make_user('sig_author', title=None, role='LGA')
        self.boss = make_user('sig_boss', title='President')

    def test_report_submission_queues_wording_item(self):
        with self.captureOnCommitCallbacks(execute=True):
            Report.objects.create(title='Ward report', report_type='WARD_TO_LGA',
                                  content='Original wording', submitted_by=self.author,
                                  submitted_to=self.boss, status='SUBMITTED')
        item = Item.objects.get(kind='REPORT_EDIT')
        self.assertTrue(Job.objects.filter(item=item, kind='GENERATE').exists())

    def test_draft_report_does_not_queue(self):
        with self.captureOnCommitCallbacks(execute=True):
            Report.objects.create(title='Draft', report_type='WARD_TO_LGA', content='X',
                                  submitted_by=self.author, submitted_to=self.boss, status='DRAFT')
        self.assertEqual(Item.objects.count(), 0)

    def test_edit_without_status_change_does_not_requeue(self):
        with self.captureOnCommitCallbacks(execute=True):
            report = Report.objects.create(title='Ward report', report_type='WARD_TO_LGA',
                                           content='Original wording', submitted_by=self.author,
                                           submitted_to=self.boss, status='SUBMITTED')
        self.assertEqual(Item.objects.filter(kind='REPORT_EDIT').count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            report.content = 'Edited wording'
            report.save(update_fields=['content'])
        self.assertEqual(Item.objects.filter(kind='REPORT_EDIT').count(), 1)

    def test_community_report_submission_queues_item(self):
        with self.captureOnCommitCallbacks(execute=True):
            CommunityReport.objects.create(reporter_name='Amina', category='EDUCATION',
                                           location_details='Birnin Kebbi',
                                           what_happened='A school needs books', status='PENDING')
        self.assertTrue(Item.objects.filter(kind='COMMUNITY_EDIT').exists())


@override_settings(KPN_EDITORIAL_ENABLED=False)
class DisabledSignalTests(TestCase):
    def test_nothing_queues_while_disabled(self):
        author = make_user('sig_author_off', title=None, role='LGA')
        boss = make_user('sig_boss_off', title='President')
        with self.captureOnCommitCallbacks(execute=True):
            Report.objects.create(title='Ward report', report_type='WARD_TO_LGA', content='X',
                                  submitted_by=author, submitted_to=boss, status='SUBMITTED')
        self.assertEqual(Item.objects.count(), 0)


@override_settings(KPN_EDITORIAL_ENABLED=True)
class CaptionSignalTests(TestCase):
    def test_publish_queues_caption_once(self):
        author = make_user('sig_cap_author', title='President')
        with self.captureOnCommitCallbacks(execute=True):
            article = Campaign.objects.create(author=author, title='Big story', slug='big-story',
                                              content='Story body', status='PUBLISHED')
            article.title = 'Big story updated'
            article.save(update_fields=['title'])
        self.assertEqual(Item.objects.filter(kind='CAPTION').count(), 1)
        self.assertEqual(Job.objects.filter(kind='GENERATE').count(), 1)

    def test_draft_article_queues_no_caption(self):
        author = make_user('sig_cap_author2', title='President')
        with self.captureOnCommitCallbacks(execute=True):
            Campaign.objects.create(author=author, title='Draft', slug='draft-x', status='DRAFT')
        self.assertEqual(Item.objects.count(), 0)
