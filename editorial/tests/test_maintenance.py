from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from editorial import maintenance
from editorial.models import Item, LinkCheck, Source
from core.models import Opportunity


def make_opp(**kw):
    defaults = dict(title='Test opportunity', slug='test-opp-' + str(Opportunity.objects.count()),
                    provider='NGO', description='Details', status='OPEN',
                    application_link='https://example.com/apply', deadline=None)
    defaults.update(kw)
    return Opportunity.objects.create(**defaults)


class DeadlineReminderTests(TestCase):
    def test_reminders_at_7_3_1_0_days(self):
        today = maintenance.local_day()
        for offset in (7, 3, 1, 0):
            make_opp(deadline=today + timedelta(days=offset), title=f'Opp in {offset}')
        make_opp(deadline=today + timedelta(days=5), title='Opp in 5')
        maintenance.deadline_reminders()
        titles = set(Item.objects.filter(kind='DEADLINE').values_list('title', flat=True))
        self.assertEqual(len(titles), 4)
        self.assertFalse(any('Opp in 5' in t for t in titles))

    def test_reminders_are_idempotent_per_day(self):
        make_opp(deadline=maintenance.local_day())
        maintenance.deadline_reminders()
        maintenance.deadline_reminders()
        self.assertEqual(Item.objects.filter(kind='DEADLINE').count(), 1)

    def test_closed_opportunities_get_no_reminder(self):
        make_opp(deadline=maintenance.local_day(), status='CLOSED')
        maintenance.deadline_reminders()
        self.assertEqual(Item.objects.filter(kind='DEADLINE').count(), 0)


class BriefingTests(TestCase):
    def test_briefing_and_weekly_items_created(self):
        Item.objects.create(key='m-news', kind='NEWS', title='Pending draft', state='REVIEW')
        maintenance.briefings()
        self.assertTrue(Item.objects.filter(kind='BRIEFING').exists())
        self.assertTrue(Item.objects.filter(kind='WEEKLY').exists())
        briefing = Item.objects.get(kind='BRIEFING')
        self.assertIn('News drafts needing review: 1', briefing.draft['body'])

    def test_briefing_refresh_does_not_duplicate(self):
        maintenance.briefings()
        maintenance.briefings()
        self.assertEqual(Item.objects.filter(kind='BRIEFING').count(), 1)


class LinkCheckTests(TestCase):
    def test_broken_link_creates_alert_and_record(self):
        opp = make_opp()
        with mock.patch.object(maintenance, 'fetch', return_value=(404, b'', opp.application_link)):
            maintenance.link_checks()
        self.assertTrue(Item.objects.filter(kind='LINK_ALERT').exists())
        self.assertEqual(LinkCheck.objects.get(opportunity=opp).state, 'BROKEN')

    def test_ok_link_no_alert(self):
        opp = make_opp()
        with mock.patch.object(maintenance, 'fetch', return_value=(200, b'', opp.application_link)):
            maintenance.link_checks()
        self.assertFalse(Item.objects.filter(kind='LINK_ALERT').exists())
        self.assertEqual(LinkCheck.objects.get(opportunity=opp).state, 'OK')

    def test_restricted_link_is_not_called_broken(self):
        opp = make_opp()
        with mock.patch.object(maintenance, 'fetch', return_value=(403, b'', opp.application_link)):
            maintenance.link_checks()
        self.assertFalse(Item.objects.filter(kind='LINK_ALERT').exists())
        self.assertEqual(LinkCheck.objects.get(opportunity=opp).state, 'RESTRICTED')

    def test_unapproved_host_stays_unverified(self):
        opp = make_opp(application_link='https://unknown.example.net/apply')
        Source.objects.create(name='Other', kind='OPPORTUNITY', url='https://example.com/feed', enabled=True)
        with mock.patch.object(maintenance, 'fetch', side_effect=maintenance.FetchError('host_not_approved')):
            maintenance.link_checks()
        self.assertEqual(LinkCheck.objects.get(opportunity=opp).state, 'UNVERIFIED')
        self.assertFalse(Item.objects.filter(kind='LINK_ALERT').exists())

    def test_same_day_recheck_is_skipped(self):
        opp = make_opp()
        with mock.patch.object(maintenance, 'fetch', return_value=(200, b'', opp.application_link)) as fetch_mock:
            maintenance.link_checks()
            maintenance.link_checks()
        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(LinkCheck.objects.filter(opportunity=opp).count(), 1)
