"""Phase 5 (KPN Media): the existing About Us page keeps its URL,
structure and organisational content, and gains one reader-facing
KPN Media section explaining the seven pillars in plain language.

No internal or technical term from the build (app names, migration
or system talk) may leak into the rendered page.
"""

from django.test import TestCase
from django.urls import reverse


class AboutPagePreservedTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse('core:about'))
        self.html = self.response.content.decode('utf-8')

    def test_about_page_still_at_existing_url(self):
        self.assertEqual(reverse('core:about'), '/about/')
        self.assertEqual(self.response.status_code, 200)

    def test_existing_organisational_content_preserved(self):
        for marker in [
            'About Kebbi Progressive Youth Network',
            'One Voice, One Change',
            '21 Local Government Areas',
            'Our Vision',
            'Our Mission',
            'The Five Pillars of KPN',
            'KPN MEDIA',
            'KPN CIVIC',
            'KPN COMMUNITY',
            'KPN OPPORTUNITIES',
            'KPN ADVOCACY',
            'Our Network Structure',
            'State Executive',
            'Senatorial Zones',
            '225 Wards',
        ]:
            self.assertIn(marker, self.html)


class AboutKpnMediaSectionTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse('core:about'))
        self.html = self.response.content.decode('utf-8')

    def test_all_seven_pillars_explained(self):
        for pillar in [
            'Living Stories',
            'Public Promise Tracker',
            'Future Signal',
            'Community Radar',
            'Truth Layers',
            'Human Impact Files',
            'KPN Knowledge Archive',
        ]:
            self.assertIn(pillar, self.html)

    def test_verification_explained_honestly(self):
        self.assertIn('How KPN checks what it publishes', self.html)
        self.assertIn('an official statement is not the same as a '
                      'confirmed fact', self.html)

    def test_reader_facing_meaning_present(self):
        # Plain-language explanations, not feature names alone.
        self.assertIn('living record', self.html)
        self.assertIn('clearly labelled as analysis', self.html)
        self.assertIn('Story ID', self.html)

    def test_links_to_public_surfaces(self):
        self.assertIn('/promises/', self.html)
        self.assertIn('/signals/', self.html)
        self.assertIn('/impact/stories/', self.html)
        self.assertIn('/archive/', self.html)

    def test_no_internal_or_technical_terms_leak(self):
        lowered = self.html.lower()
        for term in [
            'story_intelligence',
            'migration',
            'django',
            'database',
            'capabilit',
        ]:
            self.assertNotIn(term, lowered)
