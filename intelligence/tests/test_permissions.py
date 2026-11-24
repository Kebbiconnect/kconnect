"""Intelligence capabilities and dashboard gating (Doc 07 mapping)."""
from django.test import TestCase
from django.urls import reverse

from editorial.tests.helpers import (
    assistant_media, general_member, make_user, media_director, president,
)
from leadership.capabilities import capabilities_for
from leadership.models import LGA
from intelligence.models import GeoAlias, District, IntelligenceAudit
from intelligence.tests.helpers import seed_directory

ALL_INTEL_CAPS = {
    'VIEW_INTELLIGENCE', 'MANAGE_SOURCES', 'REVIEW_INTELLIGENCE',
    'VERIFY_INTELLIGENCE', 'APPROVE_INTELLIGENCE', 'APPROVE_SENSITIVE',
    'MANAGE_PROJECTS', 'VERIFY_PROJECTS', 'VIEW_SECURITY_DESK',
    'HANDLE_SECURITY_ALERTS', 'SUBMIT_FIELD_REPORTS', 'VIEW_INTELLIGENCE_REPORTS',
}


def lga_viewer(username='intel_lga_viewer'):
    return make_user(username, title='LGA Coordinator', tier='LGA', role='LGA')


class CapabilityGrantTests(TestCase):
    def test_media_director_holds_all_intelligence_capabilities(self):
        caps = set(capabilities_for(media_director('intel_director')))
        self.assertTrue(ALL_INTEL_CAPS.issubset(caps))

    def test_assistant_director_is_news_editor_without_source_or_security_control(self):
        caps = set(capabilities_for(assistant_media('intel_asst')))
        self.assertTrue({'VIEW_INTELLIGENCE', 'REVIEW_INTELLIGENCE', 'VERIFY_INTELLIGENCE',
                         'APPROVE_INTELLIGENCE', 'VIEW_INTELLIGENCE_REPORTS'}.issubset(caps))
        self.assertTrue({'MANAGE_SOURCES', 'VIEW_SECURITY_DESK', 'APPROVE_SENSITIVE'}.isdisjoint(caps))

    def test_president_reads_but_does_not_manage_sources(self):
        caps = set(capabilities_for(president('intel_president')))
        self.assertIn('VIEW_INTELLIGENCE', caps)
        self.assertIn('VIEW_INTELLIGENCE_REPORTS', caps)
        self.assertNotIn('MANAGE_SOURCES', caps)

    def test_president_holds_security_desk(self):
        # Owner decision D6 (23 Nov 2026): the Security Desk holders
        # are exactly the Director of Media & Communications and the
        # President.
        caps = set(capabilities_for(president('intel_president_d6')))
        self.assertTrue({'VIEW_SECURITY_DESK', 'HANDLE_SECURITY_ALERTS',
                         'APPROVE_SENSITIVE'}.issubset(caps))

    def test_monitoring_director_no_longer_holds_security_desk(self):
        # D6 supersedes Doc 07's original proposal of the Monitoring
        # Director as a security-desk holder.
        user = make_user('intel_monitor', title='Director of Monitoring & Compliance')
        caps = set(capabilities_for(user))
        self.assertTrue({'VIEW_SECURITY_DESK', 'HANDLE_SECURITY_ALERTS',
                         'APPROVE_SENSITIVE'}.isdisjoint(caps))
        self.assertIn('VIEW_INTELLIGENCE', caps)

    def test_audit_director_holds_project_capabilities(self):
        user = make_user('intel_audit_dir', title='Director of Audit & Accountability')
        caps = set(capabilities_for(user))
        self.assertTrue({'MANAGE_PROJECTS', 'VERIFY_PROJECTS'}.issubset(caps))

    def test_lga_tier_officer_can_view(self):
        self.assertIn('VIEW_INTELLIGENCE', capabilities_for(lga_viewer()))

    def test_trusted_reporter_can_submit_field_reports(self):
        user = make_user('intel_reporter', title=None, role='GENERAL', is_trusted_reporter=True)
        self.assertIn('SUBMIT_FIELD_REPORTS', capabilities_for(user))

    def test_general_member_and_ward_officer_have_no_intelligence_capabilities(self):
        member = general_member('intel_member')
        self.assertTrue(ALL_INTEL_CAPS.isdisjoint(set(capabilities_for(member))))
        ward = make_user('intel_ward', title='Ward Communications Officer', tier='WARD', role='WARD')
        self.assertTrue(ALL_INTEL_CAPS.isdisjoint(set(capabilities_for(ward))))


class DashboardGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.director = media_director('gate_director')
        cls.viewer = lga_viewer('gate_viewer')
        cls.member = general_member('gate_member')

    def test_dashboard_lives_under_editorial_prefix(self):
        self.assertEqual(reverse('intelligence:overview'), '/editorial/intelligence/')

    def test_anonymous_redirected_to_login(self):
        for name in ('overview', 'sources', 'lgas', 'aliases'):
            response = self.client.get(reverse(f'intelligence:{name}'))
            self.assertEqual(response.status_code, 302, name)

    def test_member_without_capability_refused(self):
        self.client.force_login(self.member)
        for name in ('overview', 'sources', 'lgas', 'aliases'):
            response = self.client.get(reverse(f'intelligence:{name}'))
            self.assertEqual(response.status_code, 403, name)

    def test_viewer_can_read_but_not_manage(self):
        self.client.force_login(self.viewer)
        for name in ('overview', 'sources', 'lgas', 'aliases'):
            response = self.client.get(reverse(f'intelligence:{name}'))
            self.assertEqual(response.status_code, 200, name)
        self.assertEqual(self.client.get(reverse('intelligence:source_new')).status_code, 403)
        lga = LGA.objects.get(name='Birnin Kebbi')
        self.assertEqual(
            self.client.get(reverse('intelligence:lga_detail', args=[lga.pk])).status_code, 200)

    def test_director_can_open_source_form(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(reverse('intelligence:source_new')).status_code, 200)

    def test_alias_approval_requires_manage_sources(self):
        lga = LGA.objects.get(name='Zuru')
        district = District.objects.create(name='Gate District', lga=lga)
        alias = GeoAlias.objects.create(alias='Gateville', target_kind='DISTRICT', district=district)
        self.client.force_login(self.viewer)
        response = self.client.post(reverse('intelligence:alias_approve', args=[alias.pk]))
        self.assertEqual(response.status_code, 403)
        alias.refresh_from_db()
        self.assertEqual(alias.status, 'PENDING')
        self.client.force_login(self.director)
        response = self.client.post(reverse('intelligence:alias_approve', args=[alias.pk]))
        self.assertEqual(response.status_code, 302)
        alias.refresh_from_db()
        self.assertEqual(alias.status, 'APPROVED')
        self.assertTrue(IntelligenceAudit.objects.filter(action='ALIAS_APPROVED', target_id=alias.pk).exists())
