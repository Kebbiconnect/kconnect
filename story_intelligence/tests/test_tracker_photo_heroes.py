"""Photo heroes for the tracker pages (owner instruction 2026-11-24):
the Promise Tracker was built with a plain brand-green gradient hero
before the standing rule that every public page carries a real Kebbi
photographic hero. These tests pin the .kpn-page-hero-photo treatment
(photo background via the --hero variable, brand-green overlay) on the
tracker list and detail pages, and pin that no credit line renders."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from editorial.tests.helpers import media_director
from story_intelligence.models import Institution, Promise


class PromisePhotoHeroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('hero_editor')
        institution = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY')
        cls.promise = Promise.objects.create(
            institution=institution,
            title='Rebuild the Argungu township road',
            description='What was promised.',
            announced_on=timezone.localdate() - timedelta(days=5),
            created_by=cls.editor)

    def test_list_hero_is_a_photo_hero(self):
        response = self.client.get(reverse('promises:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpn-page-hero-photo')
        self.assertContains(response, 'promises-hero')

    def test_detail_hero_is_a_photo_hero(self):
        response = self.client.get(
            reverse('promises:detail', args=[self.promise.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpn-page-hero-photo')
        self.assertContains(response, 'promises-hero')

    def test_no_credit_line_on_tracker_pages(self):
        for url in (reverse('promises:list'),
                    reverse('promises:detail', args=[self.promise.pk])):
            response = self.client.get(url)
            self.assertNotContains(response, 'kpn-hero-credit')
            self.assertNotContains(response, 'Photo:')
