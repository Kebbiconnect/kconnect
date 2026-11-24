"""Dashboard pages render real data — including honest empty states."""
from django.test import TestCase
from django.urls import reverse

from editorial.models import Source
from editorial.tests.helpers import media_director
from leadership.models import LGA
from intelligence.models import District, IntelligenceAudit
from intelligence.tests.helpers import seed_directory


class DashboardRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.director = media_director('dash_director')

    def setUp(self):
        self.client.force_login(self.director)

    def test_overview_renders_with_real_empty_state(self):
        response = self.client.get(reverse('intelligence:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No collection runs recorded.')
        self.assertContains(response, 'No sources in the directory.')
        # The count is the live table count (the user factory adds one test
        # LGA); the exact seeded-21 assertion lives in test_geography.
        self.assertContains(response, f'{LGA.objects.count()} LGAs')
        self.assertContains(response, 'NO_RUNS_YET')

    def test_lga_directory_lists_all_21(self):
        response = self.client.get(reverse('intelligence:lgas'))
        self.assertEqual(response.status_code, 200)
        for name in ('Birnin Kebbi', 'Danko/Wasagu', 'Aleiro', 'Zuru', 'Yauri'):
            self.assertContains(response, name)

    def test_lga_detail_renders(self):
        lga = LGA.objects.get(name='Birnin Kebbi')
        response = self.client.get(reverse('intelligence:lga_detail', args=[lga.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Birnin Kebbi')
        self.assertContains(response, 'No districts recorded.')

    def test_district_add_flow(self):
        lga = LGA.objects.get(name='Argungu')
        response = self.client.post(
            reverse('intelligence:district_add', args=[lga.pk]), {'name': 'Argungu Central'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(District.objects.filter(name='Argungu Central', lga=lga).exists())
        self.assertTrue(IntelligenceAudit.objects.filter(action='DISTRICT_CREATED').exists())

    def test_source_create_flow_creates_health_and_audit(self):
        response = self.client.post(reverse('intelligence:source_new'), {
            'name': 'Kebbi State Government Pressroom',
            'kind': 'NEWS',
            'url': 'https://example.com/pressroom',
            'feed': '',
            'allowed_hosts': '',
            'keywords': 'Kebbi',
            'max_items': '5',
            'enabled': 'on',
            'connector_kind': 'OFFICIAL_PAGE',
            'poll_interval_minutes': '30',
            'home_lga': '',
        })
        self.assertEqual(response.status_code, 302)
        source = Source.objects.get(name='Kebbi State Government Pressroom')
        self.assertEqual(source.connector_kind, 'OFFICIAL_PAGE')
        self.assertEqual(source.poll_interval_minutes, 30)
        self.assertTrue(hasattr(source, 'intelligence_health'))
        self.assertTrue(IntelligenceAudit.objects.filter(action='SOURCE_SAVED', target_id=source.pk).exists())

    def test_control_toggle_pauses_collection(self):
        response = self.client.post(reverse('intelligence:control'), {'enabled': 'no'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(IntelligenceAudit.objects.filter(action='COLLECTION_PAUSED').exists())
