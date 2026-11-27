"""President dashboard API — 2.0.7 audit addition.

The web President dashboard (staff.views.president_dashboard) shows
org-wide figures that no existing API endpoint could serve to the
President: verified leaders and the gender split, member growth this
month and the rolling 7-day growth windows, org-wide campaign totals,
org-wide programme totals, the is_reviewed-based report totals, the
VERIFIED-only donation total and the total FAQ count.
GET /api/v1/dashboards/president/ mirrors the web view's querysets
exactly and is gated on the same role title the web uses.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from campaigns.models import Campaign
from core.models import FAQ, Report
from donations.models import Donation, Expense
from editorial.tests.helpers import general_member, make_user, media_director, president
from staff.models import WomensProgram, YouthProgram
from telegram_integration.models import TelegramMembership

API = '/api/v1/'


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def block_items(data, key):
    for entry in data['blocks']:
        if entry['key'] == key:
            return {i['key']: i['value'] for i in entry['items']}
    return {}


class PresidentDashboardApiTests(TestCase):
    def setUp(self):
        self.president = president('pres_dash_president')
        TelegramMembership.objects.create(
            user=self.president, telegram_user_id=555001,
            telegram_username='pres_dash_president',
            telegram_status='member', is_verified=True)
        # Verified members: the president (STATE role) plus a male
        # general member; one pending applicant; one female leader.
        self.male = make_user('pres_dash_male', title=None,
                              role='GENERAL', gender='M')
        self.female_leader = make_user(
            'pres_dash_female', title='General Secretary', gender='F')
        self.pending = make_user('pres_dash_pending', title=None,
                                 role='GENERAL', status='PENDING')
        self.editor = media_director('pres_dash_editor')
        Campaign.objects.create(
            author=self.editor, title='Published One', slug='pres-pub',
            status='PUBLISHED', content='x')
        Campaign.objects.create(
            author=self.editor, title='Pending One', slug='pres-pen',
            status='PENDING', content='x')
        Campaign.objects.create(
            author=self.president, title='Draft One', slug='pres-draft',
            status='DRAFT', content='x')
        Donation.objects.create(
            donor_name='Donor A', amount=Decimal('5000'),
            status='VERIFIED', reference='REF-A')
        Donation.objects.create(
            donor_name='Donor B', amount=Decimal('7000'),
            status='UNVERIFIED', reference='REF-B')
        Expense.objects.create(
            description='Fuel', amount=Decimal('1500'),
            category='OPERATIONS', date=date(2026, 6, 1))
        Report.objects.create(
            title='Ward report', report_type='WARD_TO_LGA', content='c',
            submitted_by=self.male, status='SUBMITTED',
            is_reviewed=False)
        Report.objects.create(
            title='LGA report', report_type='LGA_TO_ZONAL', content='c',
            submitted_by=self.male, status='APPROVED', is_reviewed=True)
        WomensProgram.objects.create(title='Tailoring cohort')
        YouthProgram.objects.create(title='Coding cohort')
        YouthProgram.objects.create(title='Football cohort')
        FAQ.objects.create(question='Q1', answer='A1', is_active=True)
        FAQ.objects.create(question='Q2', answer='A2', is_active=False)

    def test_president_receives_web_dashboard_figures(self):
        response = client_for(self.president).get(
            API + 'dashboards/president/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['dashboard_key'], 'president')
        membership = block_items(response.data, 'membership')
        # Verified: president, male member, female leader, editor.
        self.assertEqual(membership['verified_members'], 4)
        # Leaders = verified minus GENERAL-role (the male member).
        self.assertEqual(membership['total_leaders'], 3)
        self.assertEqual(membership['male_members'], 1)
        self.assertEqual(membership['female_members'], 1)
        self.assertEqual(membership['pending_approvals'], 1)
        self.assertEqual(membership['member_growth_this_month'], 4)
        campaigns = block_items(response.data, 'campaigns')
        self.assertEqual(campaigns['total_campaigns'], 3)
        self.assertEqual(campaigns['active_campaigns'], 1)
        self.assertEqual(campaigns['pending_campaigns'], 1)
        finance = block_items(response.data, 'finance')
        self.assertEqual(finance['total_donations'], '5000')
        self.assertEqual(finance['pending_donations'], 1)
        self.assertEqual(finance['total_expenses'], '1500')
        oversight = block_items(response.data, 'oversight')
        self.assertEqual(oversight['pending_reports'], 1)
        self.assertEqual(oversight['total_reports'], 2)
        programs = block_items(response.data, 'programs')
        self.assertEqual(programs['womens_programs'], 1)
        self.assertEqual(programs['youth_programs'], 2)
        self.assertEqual(programs['welfare_programs'], 0)
        content = block_items(response.data, 'content')
        # The view counts every FAQ row; the test DB also carries the 21
        # rows seeded by migration core/0015 (FAQ expansion), so compare
        # against the live count rather than this test's own 2 rows.
        self.assertEqual(content['total_faqs'], FAQ.objects.count())
        charts = {c['key']: c for c in response.data['charts']}
        self.assertIn('membership_growth', charts)
        growth = charts['membership_growth']['rows']
        self.assertEqual(len(growth), 5)
        # All four verified members joined within the past 7 days.
        self.assertEqual(growth[-1]['label'], 'Past 7 days')
        self.assertEqual(growth[-1]['value'], 4)
        self.assertEqual(
            sum(r['value'] for r in charts['members_by_status']['rows']),
            5)  # every user, mirroring the web status donut

    def test_non_presidents_are_denied(self):
        for user in (self.editor, self.male):
            response = client_for(user).get(API + 'dashboards/president/')
            self.assertEqual(response.status_code, 403, user.username)

    def test_anonymous_is_denied(self):
        response = APIClient().get(API + 'dashboards/president/')
        self.assertEqual(response.status_code, 401)
