"""Photo heroes for the Project Tracker and public LGA pages (owner
instruction 2026-11-24): these pages were built with plain brand-green
gradient heroes before the standing rule that every public page
carries a real Kebbi photographic hero. These tests pin the
.kpn-page-hero-photo treatment (photo background via the --hero
variable, brand-green overlay) on the project list/detail and LGA
index/detail pages, and pin that no credit line renders."""
from django.test import TestCase
from django.urls import reverse

from editorial.tests.helpers import media_director
from intelligence import projects as project_service
from intelligence.tests.helpers import seed_directory
from leadership.models import LGA
from story_intelligence.models import Institution


class TrackerPhotoHeroTests(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('hero_director')
        self.jega = LGA.objects.get(name='Jega')
        institution = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY')
        self.project = project_service.create_project(
            self.director, title='Reconstruction of Jega Township Roads',
            lga=self.jega, institution=institution)

    def assert_photo_hero(self, url, image):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpn-page-hero-photo')
        self.assertContains(response, image)
        self.assertNotContains(response, 'kpn-hero-credit')
        self.assertNotContains(response, 'Photo:')

    def test_project_list_hero_is_a_photo_hero(self):
        self.assert_photo_hero(
            reverse('projects:list'), 'projects-hero')

    def test_project_detail_hero_is_a_photo_hero(self):
        self.assert_photo_hero(
            reverse('projects:detail', args=[self.project.pk]),
            'projects-hero')

    def test_lga_index_hero_is_a_photo_hero(self):
        self.assert_photo_hero(
            reverse('lga_news:index'), 'lga-hero')

    def test_lga_detail_hero_is_a_photo_hero(self):
        self.assert_photo_hero(
            reverse('lga_news:detail', args=['jega']), 'lga-hero')
