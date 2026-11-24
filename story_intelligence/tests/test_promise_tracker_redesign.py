"""Promise Tracker public redesign (2026-11-23): the At a Glance
figures are computed from real records, every filter in the panel
narrows the register, the delayed figure is honest (explicit DELAYED
or past the announced deadline without verified completion), the
empty state is real, and the page is public."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from editorial.tests.helpers import media_director
from leadership.models import LGA, Zone
from story_intelligence.models import Institution, Promise


def make_promise(editor, institution, **kw):
    defaults = {
        'institution': institution,
        'title': 'A tracked promise',
        'description': 'What was promised.',
        'announced_on': timezone.localdate() - timedelta(days=5),
        'created_by': editor,
    }
    defaults.update(kw)
    return Promise.objects.create(**defaults)


class TrackerFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.editor = media_director('ptr_editor')
        cls.works = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY')
        cls.education = Institution.objects.create(
            name='Ministry of Education', kind='MINISTRY')
        zone = Zone.objects.create(name='Kebbi Central')
        cls.birnin = LGA.objects.create(name='Birnin Kebbi', zone=zone)
        cls.zuru = LGA.objects.create(name='Zuru', zone=zone)

    def titles(self, response):
        return [p.title for p in response.context['promises']]


class PromiseTrackerStatsTests(TrackerFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        today = cls.today
        cls.in_progress = make_promise(
            cls.editor, cls.works, title='Rebuild the Argungu township road',
            status='IN_PROGRESS', sector='INFRASTRUCTURE', lga=cls.birnin,
            deadline=today + timedelta(days=30),
            announced_on=today - timedelta(days=10))
        cls.completed = make_promise(
            cls.editor, cls.education, title='Renovate secondary schools',
            status='COMPLETED_VERIFIED', sector='EDUCATION', lga=cls.zuru,
            deadline=today - timedelta(days=20),
            announced_on=today - timedelta(days=100))
        cls.delayed_explicit = make_promise(
            cls.editor, cls.works, title='Rural electrification phase two',
            status='DELAYED', sector='INFRASTRUCTURE', lga=cls.zuru,
            deadline=today + timedelta(days=10),
            announced_on=today - timedelta(days=50))
        cls.overdue = make_promise(
            cls.editor, cls.education, title='Free fertiliser distribution',
            status='DOCUMENTED', sector='AGRICULTURE', lga=cls.birnin,
            deadline=today - timedelta(days=5),
            announced_on=today - timedelta(days=60))
        cls.announced = make_promise(
            cls.editor, cls.works, title='New township stadium',
            status='ANNOUNCED', sector='', lga=None,
            announced_on=today - timedelta(days=5))

    def test_stats_are_computed_from_real_records(self):
        response = self.client.get(reverse('promises:list'))
        self.assertEqual(response.status_code, 200)
        stats = response.context['stats']
        self.assertEqual(stats['total'], 5)
        self.assertEqual(stats['in_progress'], 1)
        self.assertEqual(stats['completed_verified'], 1)
        # Explicit DELAYED + the overdue DOCUMENTED promise; the
        # completed promise is past its deadline but never counts.
        self.assertEqual(stats['delayed'], 2)

    def test_delayed_flag_matches_the_statistic(self):
        response = self.client.get(reverse('promises:list'))
        flags = {p.title: p.delayed_flag for p in response.context['promises']}
        self.assertTrue(flags['Rural electrification phase two'])
        self.assertTrue(flags['Free fertiliser distribution'])
        self.assertFalse(flags['Rebuild the Argungu township road'])
        self.assertFalse(flags['Renovate secondary schools'])
        self.assertFalse(flags['New township stadium'])

    def test_is_delayed_model_rule(self):
        self.assertTrue(self.delayed_explicit.is_delayed(self.today))
        self.assertTrue(self.overdue.is_delayed(self.today))
        self.assertFalse(self.completed.is_delayed(self.today))
        self.assertFalse(self.in_progress.is_delayed(self.today))

    def test_public_code_is_display_format_from_pk(self):
        self.assertEqual(self.in_progress.public_code,
                         f'KPN-PT-{self.in_progress.pk:04d}')
        response = self.client.get(reverse('promises:list'))
        self.assertIn(self.in_progress.public_code, response.content.decode())

    def test_last_updated_is_real_when_records_exist(self):
        response = self.client.get(reverse('promises:list'))
        self.assertIsNotNone(response.context['last_updated'])
        self.assertIn('Last Updated:', response.content.decode())


class PromiseTrackerFilterTests(TrackerFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        today = cls.today
        make_promise(cls.editor, cls.works, title='Alpha road project',
                     status='IN_PROGRESS', sector='INFRASTRUCTURE',
                     lga=cls.birnin, announced_on=today)
        make_promise(cls.editor, cls.education, title='Beta school books',
                     status='DOCUMENTED', sector='EDUCATION', lga=cls.zuru,
                     announced_on=today - timedelta(days=400))
        make_promise(cls.editor, cls.education, title='Gamma clinic upgrade',
                     status='DELAYED', sector='HEALTH', lga=cls.birnin,
                     announced_on=today - timedelta(days=10))

    def get(self, **params):
        return self.client.get(reverse('promises:list'), params)

    def test_no_filters_lists_everything(self):
        self.assertEqual(len(self.titles(self.get())), 3)

    def test_search_matches_title_institution_and_lga(self):
        self.assertEqual(self.titles(self.get(q='Alpha')), ['Alpha road project'])
        self.assertEqual(sorted(self.titles(self.get(q='Education'))),
                         ['Beta school books', 'Gamma clinic upgrade'])
        self.assertEqual(self.titles(self.get(q='Zuru')), ['Beta school books'])

    def test_sector_filter_narrows(self):
        self.assertEqual(self.titles(self.get(sector='EDUCATION')),
                         ['Beta school books'])

    def test_lga_filter_narrows(self):
        self.assertEqual(sorted(self.titles(self.get(lga=self.birnin.pk))),
                         ['Alpha road project', 'Gamma clinic upgrade'])

    def test_institution_filter_narrows(self):
        self.assertEqual(sorted(self.titles(self.get(institution=self.education.pk))),
                         ['Beta school books', 'Gamma clinic upgrade'])

    def test_status_filter_narrows(self):
        self.assertEqual(self.titles(self.get(status='DELAYED')),
                         ['Gamma clinic upgrade'])

    def test_period_filters_narrow_by_announced_date(self):
        self.assertEqual(sorted(self.titles(self.get(period='this_year'))),
                         ['Alpha road project', 'Gamma clinic upgrade'])
        self.assertEqual(self.titles(self.get(period='last_year')),
                         ['Beta school books'])
        self.assertEqual(sorted(self.titles(self.get(period='last_30'))),
                         ['Alpha road project', 'Gamma clinic upgrade'])

    def test_filters_combine_and_preserve_selection(self):
        response = self.get(sector='HEALTH', lga=self.birnin.pk)
        self.assertEqual(self.titles(response), ['Gamma clinic upgrade'])
        self.assertEqual(response.context['params']['sector'], 'HEALTH')
        self.assertEqual(response.context['params']['lga'], self.birnin.pk)
        self.assertTrue(response.context['has_filters'])

    def test_invalid_filter_values_are_ignored(self):
        response = self.get(sector='NOPE', status='NOPE', period='NOPE',
                            lga='abc', institution='99999')
        self.assertEqual(len(self.titles(response)), 3)

    def test_filter_with_no_match_shows_filtered_empty_state(self):
        response = self.get(q='nothing-matches-this')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), [])
        self.assertIn('No commitments match these filters',
                      response.content.decode())


class PromiseTrackerEmptyStateTests(TestCase):
    def test_empty_tracker_renders_premium_honest_zero_state(self):
        response = self.client.get(reverse('promises:list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Public Commitments.', content)
        self.assertIn('At a Glance', content)
        stats = response.context['stats']
        self.assertEqual(stats, {'total': 0, 'in_progress': 0,
                                 'delayed': 0, 'completed_verified': 0})
        self.assertIn('No commitments tracked yet', content)
        # No records means no "Last Updated" line is invented.
        self.assertIsNone(response.context['last_updated'])
        self.assertNotIn('Last Updated:', content)


class PromiseTrackerPublicAccessTests(TrackerFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.promise = make_promise(
            cls.editor, cls.works, title='Rebuild the Argungu township road',
            status='IN_PROGRESS', sector='INFRASTRUCTURE', lga=cls.birnin)

    def test_anonymous_can_open_list(self):
        response = self.client.get(reverse('promises:list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Commitment Register', response.content.decode())

    def test_anonymous_can_open_detail_with_public_code(self):
        response = self.client.get(
            reverse('promises:detail', args=[self.promise.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Rebuild the Argungu township road', content)
        self.assertIn(f'KPN-PT-{self.promise.pk:04d}', content)
        self.assertIn('Infrastructure', content)


class BrandGreenTests(TrackerFixture):
    """Owner correction (2026-11-23): the tracker uses the KPN brand
    green, never the navy of the first redesign pass."""

    def test_list_page_uses_brand_green_not_navy(self):
        response = self.client.get(reverse('promises:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '--pt-green: #176b36')
        self.assertNotContains(response, 'pt-navy')
        self.assertNotContains(response, '#0a2a4a')

    def test_detail_page_uses_brand_green_not_navy(self):
        promise = make_promise(self.editor, self.works, status='ANNOUNCED')
        response = self.client.get(reverse('promises:detail', args=[promise.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '--pt-green: #176b36')
        self.assertNotContains(response, 'pt-navy')
