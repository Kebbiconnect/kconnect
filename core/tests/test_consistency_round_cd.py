"""Consistency Rounds C+D — authenticated pages & dashboards.

Pins: upgraded pages render for their rightful role in the design
language; forbidden roles keep their previous denial behaviour; every
chart/map figure equals the seeded records; aggregates carry no PII.
Presentation/additive-context only — no workflow behaviour changes.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from campaigns.models import Campaign
from core.models import CommunityReport
from donations.models import Donation, Expense
from editorial.models import Item
from editorial.tests.helpers import general_member as ed_member
from editorial.tests.helpers import media_director as ed_director
from leadership.models import LGA, RoleDefinition, Ward, Zone
from staff.models import User
from telegram_integration.models import TelegramMembership

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def role(title, seat):
    return RoleDefinition.objects.create(title=title, tier='STATE',
                                         seat_number=seat)


def make_user(username, rd=None, **kw):
    kw.setdefault('phone', username)
    kw.setdefault('status', 'VERIFIED')
    return User.objects.create_user(
        username=username, role_definition=rd, **kw)


def telegram_verify(user, uid):
    TelegramMembership.objects.create(
        user=user, telegram_user_id=uid, is_verified=True,
        telegram_status='member')


@override_settings(STORAGES=STORAGES)
class PresidentDistributionTests(TestCase):
    def setUp(self):
        self.central = Zone.objects.create(name='Kebbi Central')
        self.north = Zone.objects.create(name='Kebbi North')
        self.bk = LGA.objects.create(name='Birnin Kebbi', zone=self.central)
        self.jega = LGA.objects.create(name='Jega', zone=self.north)
        self.president = make_user(
            'cd_president', role('President', 1), role='STATE')
        telegram_verify(self.president, 999100001)
        for i in range(3):
            make_user(f'cd_bk_{i}', role='GENERAL', zone=self.central,
                      lga=self.bk, first_name='Verifiedperson',
                      last_name='Secretname')
        for i in range(2):
            make_user(f'cd_jega_{i}', role='GENERAL', zone=self.north,
                      lga=self.jega)
        make_user('cd_pending', role='GENERAL', status='PENDING',
                  zone=self.central, lga=self.bk)

    def test_distribution_figures_equal_seeded_records(self):
        self.client.force_login(self.president)
        response = self.client.get('/account/dashboards/president/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Member Distribution')
        self.assertContains(response, 'kpn-cov-svg')
        zone_bars = {r['label']: r['value']
                     for r in response.context['member_zone_bars']}
        self.assertEqual(zone_bars, {'Kebbi Central': 3, 'Kebbi North': 2})
        lga_bars = {r['label']: r['value']
                    for r in response.context['member_lga_bars']}
        self.assertEqual(lga_bars, {'Birnin Kebbi': 3, 'Jega': 2})
        donut = response.context['member_status_donut']
        self.assertEqual(donut['total'], 7)
        status = {r['label']: r['value'] for r in donut['rows']}
        self.assertEqual(status['Verified'], 6)
        self.assertEqual(status['Pending'], 1)

    def test_aggregates_carry_no_member_names(self):
        self.client.force_login(self.president)
        response = self.client.get('/account/dashboards/president/')
        self.assertNotContains(response, 'Secretname')

    def test_general_member_is_denied_as_before(self):
        member = User.objects.get(username='cd_bk_0')
        self.client.force_login(member)
        response = self.client.get('/account/dashboards/president/')
        self.assertEqual(response.status_code, 302)


@override_settings(STORAGES=STORAGES)
class MemberFootprintTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name='Kebbi Central')
        self.lga = LGA.objects.create(name='Birnin Kebbi', zone=self.zone)
        self.ward = Ward.objects.create(name='Nassarawa Ward', lga=self.lga)
        self.member = make_user('cd_member', role='GENERAL', zone=self.zone,
                                lga=self.lga, ward=self.ward)
        other = make_user('cd_other', role='GENERAL', zone=self.zone,
                          lga=self.lga, ward=self.ward)
        for i in range(2):
            CommunityReport.objects.create(
                reporter_name='Sample Reporter', submitted_by=self.member,
                location_details='Birnin Kebbi', category='COMMUNITY',
                what_happened=f'Sample report {i}')
        CommunityReport.objects.create(
            reporter_name='Other Reporter', submitted_by=other,
            location_details='Jega', category='YOUTH',
            what_happened='Someone else\u2019s report')
        Campaign.objects.create(
            title='Sample Member Article', author=self.member,
            status='DRAFT')

    def test_own_counts_and_lga_map(self):
        self.client.force_login(self.member)
        response = self.client.get('/account/dashboards/general-member/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My KPN Footprint')
        self.assertEqual(response.context['my_reports_count'], 2)
        self.assertEqual(response.context['my_articles_count'], 1)
        self.assertContains(response, 'Your LGA — Birnin Kebbi')
        self.assertContains(response, 'kpn-chart-map-own')

    def test_member_without_lga_gets_no_map(self):
        user = make_user('cd_nolga', role='GENERAL')
        self.client.force_login(user)
        response = self.client.get('/account/dashboards/general-member/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['my_lga_map'])
        self.assertNotContains(response, 'kpn-chart-map-own')


@override_settings(STORAGES=STORAGES)
class FinanceChartTests(TestCase):
    def setUp(self):
        self.treasurer = make_user(
            'cd_treasurer', role('Director of Finance', 7), role='STATE')
        self.finsec = make_user(
            'cd_finsec', role('Finance Operations Officer', 8),
            role='STATE')
        Donation.objects.create(
            donor_name='Donor Alpha', amount=Decimal('5000'),
            reference='CD-UNV-1', status='UNVERIFIED')
        Donation.objects.create(
            donor_name='Donor Beta', amount=Decimal('10000'),
            reference='CD-VER-1', status='VERIFIED')
        Donation.objects.create(
            donor_name='Donor Gamma', amount=Decimal('20000'),
            reference='CD-VER-2', status='VERIFIED')
        Donation.objects.create(
            donor_name='Donor Delta', amount=Decimal('7000'),
            reference='CD-REC-1', status='RECORDED')
        Expense.objects.create(
            description='Sample expense', amount=Decimal('3000'),
            category='OPERATIONS', date='2026-11-24',
            recorded_by=self.finsec)

    def test_treasurer_charts_equal_records(self):
        self.client.force_login(self.treasurer)
        response = self.client.get('/finance/treasurer/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Donations by status (count)')
        status = {r['label']: r['value']
                  for r in response.context['donation_status_bars']}
        self.assertEqual(
            status, {'Unverified': 1, 'Verified': 2, 'Recorded': 1})
        months = {r['label']: r['value']
                  for r in response.context['donation_month_bars']}
        self.assertEqual(sum(months.values()), 42000)

    def test_finsec_charts_exclude_unverified(self):
        self.client.force_login(self.finsec)
        response = self.client.get('/finance/financial-secretary/')
        self.assertEqual(response.status_code, 200)
        labels = [r['label']
                  for r in response.context['donation_status_bars']]
        self.assertEqual(labels, ['Verified', 'Recorded'])
        months = {r['label']: r['value']
                  for r in response.context['donation_month_bars']}
        self.assertEqual(sum(months.values()), 37000)

    def test_financial_reports_charts(self):
        self.client.force_login(self.finsec)
        response = self.client.get('/finance/reports/')
        self.assertEqual(response.status_code, 200)
        income = {r['label']: r['value']
                  for r in response.context['income_month_bars']}
        self.assertEqual(sum(income.values()), 7000)
        expenses = {r['label']: r['value']
                    for r in response.context['expense_month_bars']}
        self.assertEqual(sum(expenses.values()), 3000)

    def test_finance_roles_denied_each_others_pages_as_before(self):
        self.client.force_login(self.finsec)
        self.assertEqual(self.client.get('/finance/treasurer/').status_code,
                         302)
        self.client.force_login(self.treasurer)
        self.assertEqual(
            self.client.get('/finance/financial-secretary/').status_code,
            302)


@override_settings(STORAGES=STORAGES)
class EditorialChartTests(TestCase):
    def setUp(self):
        self.director = ed_director('cd_ed_director')
        self.member = ed_member('cd_ed_member')
        Item.objects.create(key='cd1', kind='NEWS', title='First queue '
                            'story', state='WAITING')
        Item.objects.create(key='cd2', kind='NEWS', title='Second queue '
                            'story', state='WAITING')
        Item.objects.create(key='cd3', kind='NEWS', title='Review story',
                            state='REVIEW')

    def test_director_charts_equal_scoped_records(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('editorial:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Items by workflow state')
        states = {r['label']: r['value']
                  for r in response.context['chart_state_bars']}
        self.assertEqual(states['Waiting for processing'], 2)
        self.assertEqual(states['Needs human review'], 1)
        days = response.context['chart_day_bars']
        self.assertEqual(len(days), 14)
        self.assertEqual(days[-1]['value'], 3)

    def test_member_charts_are_scoped_to_nothing(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('editorial:index'))
        self.assertEqual(response.status_code, 200)
        total = sum(r['value']
                    for r in response.context['chart_state_bars'])
        self.assertEqual(total, 0)
        self.assertNotContains(response, 'First queue story')


@override_settings(STORAGES=STORAGES)
class LegacyUpgradeSmokeTests(TestCase):
    def setUp(self):
        self.director = ed_director('cd_smoke_director')
        telegram_verify(self.director, 999100002)
        self.member = ed_member('cd_smoke_member')

    def test_event_calendar_renders_in_design_language(self):
        self.client.force_login(self.member)
        response = self.client.get('/events/calendar/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpn-page')
        self.assertContains(response, 'kpn-h1')

    def test_my_articles_renders_in_design_language(self):
        self.client.force_login(self.director)
        response = self.client.get('/campaigns/my-articles/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpn-page')

    def test_manage_opportunities_renders_in_design_language(self):
        self.client.force_login(self.director)
        response = self.client.get('/account/manage-opportunities/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpn-page')

    def test_anonymous_still_redirected_to_login(self):
        response = self.client.get('/events/calendar/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/account/login/', response.url)
