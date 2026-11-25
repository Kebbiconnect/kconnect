"""Dashboard charts (Android 2.0.3): additive `charts` array on
dashboards/me/ and dashboards/finance/, computed from real querysets."""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from donations.models import Donation
from editorial.tests.helpers import general_member, make_user, president
from staff.models import User
from telegram_integration.models import TelegramMembership

API = '/api/v1/'


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def chart_by_key(data, key):
    for chart in data.get('charts', []):
        if chart['key'] == key:
            return chart
    return None


class MyDashboardChartsTests(TestCase):
    def setUp(self):
        self.president = president('chart_president')
        TelegramMembership.objects.create(
            user=self.president, telegram_user_id=987654,
            telegram_username='chart_president', telegram_status='member',
            is_verified=True)
        self.member = general_member('chart_member')
        self.pending = make_user(
            'chart_pending', title=None, role='GENERAL', status='PENDING')
        self.unassigned = make_user(
            'chart_unassigned', title=None, role='GENERAL', status='PENDING')
        self.unassigned.zone = None
        self.unassigned.save(update_fields=['zone'])

    def test_charts_present_and_sum_to_scoped_count(self):
        response = client_for(self.president).get(API + 'dashboards/me/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('charts', response.data)
        scoped = User.objects.filter(is_superuser=False).count()
        by_status = chart_by_key(response.data, 'members_by_status')
        self.assertIsNotNone(by_status)
        self.assertEqual(by_status['type'], 'pie')
        self.assertEqual(
            sum(r['value'] for r in by_status['rows']), scoped)
        labels = {r['label'] for r in by_status['rows']}
        self.assertIn('Verified', labels)
        self.assertIn('Pending', labels)
        by_zone = chart_by_key(response.data, 'members_by_zone')
        self.assertIsNotNone(by_zone)
        self.assertEqual(by_zone['type'], 'pie')
        self.assertEqual(sum(r['value'] for r in by_zone['rows']), scoped)
        zone_labels = {r['label']: r['value'] for r in by_zone['rows']}
        self.assertEqual(zone_labels.get('Unassigned'), 1)


class FinanceDashboardChartsTests(TestCase):
    def setUp(self):
        self.finance = make_user(
            'chart_finance', title='Director of Finance', tier='STATE',
            role='STATE')
        Donation.objects.create(
            donor_name='Donor A', amount='1000.00', reference='REF-CHART-1',
            status='VERIFIED')
        Donation.objects.create(
            donor_name='Donor B', amount='2000.00', reference='REF-CHART-2',
            status='UNVERIFIED')
        Donation.objects.create(
            donor_name='Donor C', amount='3000.00', reference='REF-CHART-3',
            status='UNVERIFIED')

    def test_finance_charts(self):
        response = client_for(self.finance).get(API + 'dashboards/finance/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('charts', response.data)
        self.assertIn('blocks', response.data)
        by_status = chart_by_key(response.data, 'donations_by_status')
        self.assertIsNotNone(by_status)
        self.assertEqual(by_status['type'], 'pie')
        self.assertEqual(
            sum(r['value'] for r in by_status['rows']),
            Donation.objects.count())
        by_month = chart_by_key(response.data, 'donations_by_month')
        self.assertIsNotNone(by_month)
        self.assertEqual(by_month['type'], 'bars')
        self.assertEqual(len(by_month['rows']), 6)
        self.assertEqual(
            by_month['rows'][-1]['label'],
            timezone.now().strftime('%b %Y'))
        self.assertEqual(
            sum(r['value'] for r in by_month['rows']),
            Donation.objects.count())
