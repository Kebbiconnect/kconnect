"""Owner correction round (2026-11-23): the dedicated Kebbi tracking
map for the tracking roles, and styled intelligence forms.

Map figures must be real per-LGA counts from the Promise table; the
map markup renders at every width (owner correction 2026-11-24: the
map shows on mobile too, inside its card) and the location list is
always in the markup below it.
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from editorial.tests.helpers import general_member, make_user, media_director, president
from leadership.models import LGA
from story_intelligence.models import Institution, Promise

from intelligence.tests.helpers import seed_directory


class MapPageGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.director = media_director('map_director')
        cls.president = president('map_president')
        cls.audit_director = make_user(
            'map_audit', title='Director of Audit & Accountability')
        cls.intel_viewer = make_user(
            'map_viewer', title='LGA Coordinator', tier='LGA', role='LGA')
        cls.member = general_member('map_member')

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('intelligence:map'))
        self.assertEqual(response.status_code, 302)

    def test_tracking_roles_get_the_map(self):
        for user in (self.director, self.president, self.audit_director):
            self.client.force_login(user)
            response = self.client.get(reverse('intelligence:map'))
            self.assertEqual(response.status_code, 200, user.username)
            self.client.logout()

    def test_view_only_intelligence_role_is_refused(self):
        # VIEW_INTELLIGENCE alone (LGA tier) is not a tracking role.
        self.client.force_login(self.intel_viewer)
        response = self.client.get(reverse('intelligence:map'))
        self.assertEqual(response.status_code, 403)

    def test_general_member_is_refused(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('intelligence:map'))
        self.assertEqual(response.status_code, 403)


class MapPageDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.director = media_director('mapdata_director')
        institution = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY')
        cls.birnin = LGA.objects.get(name='Birnin Kebbi')
        cls.zuru = LGA.objects.get(name='Zuru')
        Promise.objects.create(
            institution=institution, title='Birnin road works',
            description='Test promise.', announced_on=date(2026, 3, 1),
            status='IN_PROGRESS', lga=cls.birnin)
        Promise.objects.create(
            institution=institution, title='Birnin school blocks',
            description='Test promise.', announced_on=date(2026, 2, 1),
            status='COMPLETED_VERIFIED', lga=cls.birnin)
        Promise.objects.create(
            institution=institution, title='Zuru water scheme',
            description='Test promise.', announced_on=date(2026, 1, 15),
            deadline=date(2026, 6, 30), status='DOCUMENTED', lga=cls.zuru)
        Promise.objects.create(
            institution=institution, title='Statewide announcement',
            description='No LGA recorded.', announced_on=date(2026, 4, 1),
            status='ANNOUNCED')

    def setUp(self):
        self.client.force_login(self.director)

    def _row(self, response, name):
        for row in response.context['rows']:
            if row['lga'].name == name:
                return row
        self.fail(f'no row for {name}')

    def test_context_carries_real_per_lga_counts(self):
        response = self.client.get(reverse('intelligence:map'))
        self.assertEqual(response.status_code, 200)
        birnin = self._row(response, 'Birnin Kebbi')
        self.assertEqual(
            (birnin['tracked'], birnin['in_progress'],
             birnin['verified'], birnin['delayed']),
            (2, 1, 1, 0))
        zuru = self._row(response, 'Zuru')
        # Past its announced deadline and not verified complete: delayed.
        self.assertEqual((zuru['tracked'], zuru['delayed']), (1, 1))
        aleiro = self._row(response, 'Aleiro')
        self.assertEqual(
            (aleiro['tracked'], aleiro['in_progress'],
             aleiro['delayed'], aleiro['verified']),
            (0, 0, 0, 0))
        totals = response.context['totals']
        self.assertEqual(totals['tracked'], 3)

    def test_every_directory_lga_has_verified_geometry(self):
        # The user factory adds one extra test LGA; the canonical 21
        # seeded LGAs must all be present and carry verified geometry.
        from intelligence.map_data import LGA_GEOMETRY
        response = self.client.get(reverse('intelligence:map'))
        by_name = {row['lga'].name: row for row in response.context['rows']}
        self.assertEqual(len(LGA_GEOMETRY), 21)
        for name in LGA_GEOMETRY:
            self.assertIn(name, by_name)
            self.assertIsNotNone(by_name[name]['geometry'], name)

    def test_map_markup_renders_at_all_widths_and_list_present(self):
        response = self.client.get(reverse('intelligence:map'))
        # The SVG map is in the markup inside its card, with no
        # desktop-only wrapper…
        self.assertContains(response, '<svg')
        self.assertContains(response, 'intel-map-wrap')
        self.assertNotContains(response, 'intel-map-desktop')
        # …and the old under-900px hiding rule is gone from the styles.
        self.assertNotContains(response, '@media (max-width: 899px)')
        self.assertNotContains(response, 'display: none !important')
        # The location list is always rendered below the map.
        self.assertContains(response, 'intel-lga-list')
        for name in ('Birnin Kebbi', 'Danko/Wasagu', 'Aleiro', 'Zuru'):
            self.assertContains(response, name)

    def test_selected_lga_shows_its_promises(self):
        response = self.client.get(
            reverse('intelligence:map'), {'lga': self.birnin.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['selected']['row']['lga'], self.birnin)
        self.assertContains(response, 'Birnin road works')
        self.assertContains(response, 'Birnin school blocks')
        self.assertNotContains(response, 'Zuru water scheme')

    def test_overview_links_the_map_preview(self):
        response = self.client.get(reverse('intelligence:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('intelligence:map'))
        self.assertContains(response, 'commitments tracked across')


class FormStylingTests(TestCase):
    """Intelligence forms must use the site's editorial-form styling —
    bare as_p widgets rendered clipped/invisible inputs (owner
    correction, 2026-11-23)."""

    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.director = media_director('form_director')

    def setUp(self):
        self.client.force_login(self.director)

    def test_source_form_is_styled(self):
        response = self.client.get(reverse('intelligence:source_new'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="editorial-form"')

    def test_lga_detail_add_forms_are_styled(self):
        lga = LGA.objects.get(name='Birnin Kebbi')
        response = self.client.get(
            reverse('intelligence:lga_detail', args=[lga.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="editorial-form"', count=2)

    def test_alias_add_form_is_styled(self):
        response = self.client.get(reverse('intelligence:aliases'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="editorial-form"')
