"""Consistency Round E — role-dashboard finish.

Pins: every sampled role dashboard renders for its rightful role in
the polished design language (premium stat cards, brand tones, no
legacy accent classes); wrong roles keep their previous denial
behaviour; the three additive charts (VP zone bars, LGA/Ward
coordinator community-report status bars) equal the seeded records
the pages already list. Presentation/additive-context only.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from core.models import CommunityReport
from leadership.models import LGA, RoleDefinition, Ward, Zone
from staff.models import User
from telegram_integration.models import TelegramMembership

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

LEGACY_MARKERS = ('bg-purple-100', 'text-kpn-blue', 'text-indigo',
                  'border-orange-500', 'fa-chart-line')

# Response-level checks use only markers that cannot come from the
# global base template: its nav legitimately carries 'text-kpn-blue'
# (Report a Story link) and 'fa-chart-line' (Future Signal links) on
# every page of the site. The full marker set is pinned at template
# level by DashboardTemplateHygieneTests below.
RESPONSE_MARKERS = ('bg-purple-100', 'text-indigo', 'border-orange-500')

_uid = [9100]


def role(title, seat, tier='STATE'):
    return RoleDefinition.objects.create(title=title, tier=tier,
                                         seat_number=seat)


def make_user(username, rd=None, **kw):
    kw.setdefault('phone', username)
    kw.setdefault('status', 'VERIFIED')
    user = User.objects.create_user(username=username, role_definition=rd,
                                    **kw)
    _uid[0] += 1
    TelegramMembership.objects.create(
        user=user, telegram_user_id=999200000 + _uid[0], is_verified=True,
        telegram_status='member')
    return user


@override_settings(STORAGES=STORAGES)
class PolishedDashboardRenderTests(TestCase):
    """One rightful-role render per dashboard family."""

    def setUp(self):
        self.zone = Zone.objects.create(name='Kebbi Central')
        self.lga = LGA.objects.create(name='Birnin Kebbi', zone=self.zone)
        self.ward = Ward.objects.create(name='Nassarawa Ward', lga=self.lga)

    def assert_polished(self, user, url, *markers):
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        self.assertContains(response, 'kpn-stat-card')
        self.assertContains(response, 'tone-')
        for marker in markers:
            self.assertContains(response, marker)
        for legacy in RESPONSE_MARKERS:
            self.assertNotContains(response, legacy)

    def test_treasurer_plain_cards_became_stat_cards(self):
        user = make_user('e_treasurer', role('Director of Finance', 21),
                         role='STATE')
        self.assert_polished(user, '/account/dashboards/treasurer/',
                             'Total Income', 'kpn-step-num')

    def test_financial_secretary(self):
        user = make_user('e_finsec',
                         role('Finance Operations Officer', 22), role='STATE')
        self.assert_polished(user,
                             '/account/dashboards/financial-secretary/',
                             'Members Paid')

    def test_auditor_general(self):
        user = make_user('e_auditor',
                         role('Director of Audit & Accountability', 23),
                         role='STATE')
        self.assert_polished(user, '/account/dashboards/auditor-general/',
                             'Audits Conducted')

    def test_zonal_coordinator(self):
        user = make_user('e_zonal', role('Senatorial Director', 24,
                                         tier='ZONE'),
                         role='ZONE', zone=self.zone)
        self.assert_polished(user, '/account/dashboards/zonal-coordinator/',
                             'Members in Zone')

    def test_ward_secretary_stat_card_family(self):
        user = make_user('e_wardsec',
                         role('Ward Administrative Officer', 25, tier='WARD'),
                         role='WARD', zone=self.zone, lga=self.lga,
                         ward=self.ward)
        self.assert_polished(user, '/account/dashboards/ward-secretary/',
                             'Members in Ward')

    def test_assistant_women_leader(self):
        user = make_user(
            'e_asst_women',
            role("Assistant Director of Women's Development", 26),
            role='STATE')
        self.assert_polished(user, '/account/dashboards/assistant-women-leader/',
                             'Women Members')

    def test_legal_ethics_adviser(self):
        user = make_user('e_legal',
                         role('Director of Legal Affairs & Ethics', 27),
                         role='STATE')
        self.assert_polished(user, '/account/dashboards/legal-ethics-adviser/',
                             'Cases Reviewed')

    def test_lga_publicity_officer(self):
        user = make_user('e_lgapub',
                         role('LGA Communications Officer', 28, tier='LGA'),
                         role='LGA', zone=self.zone, lga=self.lga)
        self.assert_polished(user, '/account/dashboards/lga-publicity-officer/',
                             'Announcements Made')


@override_settings(STORAGES=STORAGES)
class DashboardChartTests(TestCase):
    def setUp(self):
        self.central = Zone.objects.create(name='Kebbi Central')
        self.north = Zone.objects.create(name='Kebbi North')
        self.bk = LGA.objects.create(name='Birnin Kebbi', zone=self.central)
        self.jega = LGA.objects.create(name='Jega', zone=self.north)
        self.ward = Ward.objects.create(name='Nassarawa Ward', lga=self.bk)
        self.ward2 = Ward.objects.create(name='Gwadangwaji Ward', lga=self.bk)

    def report(self, status, lga=None, ward=None):
        return CommunityReport.objects.create(
            reporter_name='Sample Reporter', location_details='Somewhere',
            status=status, lga=lga or self.bk, ward=ward)

    def test_vice_president_zone_bars_equal_seeded_members(self):
        vp = make_user('e_vp', role('Vice President', 2), role='STATE')
        for i in range(3):
            make_user(f'e_c_{i}', role='GENERAL', zone=self.central,
                      lga=self.bk)
        make_user('e_n_0', role='GENERAL', zone=self.north, lga=self.jega)
        self.client.force_login(vp)
        response = self.client.get('/account/dashboards/vice-president/')
        self.assertEqual(response.status_code, 200)
        bars = {r['label']: r['value']
                for r in response.context['zone_member_bars']}
        self.assertEqual(bars, {'Kebbi Central': 3, 'Kebbi North': 1})
        self.assertContains(response, 'Verified members by zone')

    def test_lga_coordinator_status_bars_equal_listed_reports(self):
        lead = make_user('e_lgalead', role('LGA Network Lead', 31, tier='LGA'),
                         role='LGA', zone=self.central, lga=self.bk)
        self.report('PENDING')
        self.report('PENDING')
        self.report('APPROVED')
        self.report('PENDING', lga=self.jega)  # another LGA — excluded
        self.client.force_login(lead)
        response = self.client.get('/account/dashboards/lga-coordinator/')
        self.assertEqual(response.status_code, 200)
        bars = {r['label']: r['value'] for r in
                response.context['community_report_status_bars']}
        self.assertEqual(bars['Pending Review'], 2)
        self.assertEqual(bars['Approved for Publication'], 1)
        self.assertEqual(bars['Rejected'], 0)
        self.assertContains(response, 'Community reports by status')

    def test_ward_coordinator_status_bars_equal_listed_reports(self):
        lead = make_user('e_wardlead',
                         role('Ward Community Lead', 32, tier='WARD'),
                         role='WARD', zone=self.central, lga=self.bk,
                         ward=self.ward)
        self.report('PENDING', ward=self.ward)
        self.report('UNDER_REVIEW', ward=self.ward)
        self.report('PENDING', ward=self.ward2)  # another ward — excluded
        self.client.force_login(lead)
        response = self.client.get('/account/dashboards/ward-coordinator/')
        self.assertEqual(response.status_code, 200)
        bars = {r['label']: r['value'] for r in
                response.context['community_report_status_bars']}
        self.assertEqual(bars['Pending Review'], 1)
        self.assertEqual(bars['Under Review'], 1)
        self.assertEqual(bars['Approved for Publication'], 0)


@override_settings(STORAGES=STORAGES)
class DashboardDenialTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name='Kebbi Central')
        self.lga = LGA.objects.create(name='Birnin Kebbi', zone=self.zone)
        self.member = make_user('e_member', role='GENERAL', zone=self.zone,
                                lga=self.lga)
        self.treasurer = make_user('e_treasurer2',
                                   role('Director of Finance', 41),
                                   role='STATE')

    def test_general_member_denied_as_before(self):
        self.client.force_login(self.member)
        for url in ('/account/dashboards/treasurer/',
                    '/account/dashboards/vice-president/',
                    '/account/dashboards/lga-coordinator/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)

    def test_wrong_role_denied_as_before(self):
        self.client.force_login(self.treasurer)
        response = self.client.get('/account/dashboards/vice-president/')
        self.assertEqual(response.status_code, 302)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get('/account/dashboards/treasurer/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])


class DashboardTemplateHygieneTests(TestCase):
    def test_no_legacy_accents_left_in_any_dashboard_template(self):
        base = (Path(settings.BASE_DIR) / 'staff' / 'templates' / 'staff'
                / 'dashboards')
        offenders = []
        for path in sorted(base.rglob('*.html')):
            text = path.read_text()
            for marker in LEGACY_MARKERS:
                if marker in text:
                    offenders.append(f'{path.name}: {marker}')
        self.assertEqual(offenders, [])
