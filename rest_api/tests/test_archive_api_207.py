"""Story Archive API — 2.0.7 fixes.

Root causes pinned by these tests (all in the shared query layer,
story_intelligence.archive, plus the API view's Story ID trigger):

1. The Story ID path only fired when the whole query was exactly the
   canonical ID. An ID typed/pasted with a label or punctuation
   ("Story ID: KPN-SI-…", a trailing ".") fell through to a text
   search for the decorated string and returned zero results.
2. A reversed From–To pair filtered published_at >= the later date
   AND <= the earlier one — a combination that can never match.
3. ISO-datetime date values (what a mobile date-range picker emits)
   were rejected by the date parser, silently dropping the filter.
4. Date filtering used the `__date` transform, whose result depends
   on the database session timezone; it is now an explicit
   Africa/Lagos day-boundary range, so a story published at any time
   ON the To date — including just after midnight Lagos time —
   always matches, on SQLite and Postgres alike.
"""
from datetime import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from editorial.tests.helpers import media_director

API = '/api/v1/'
LAGOS = timezone.get_default_timezone()


def lagos_dt(year, month, day, hour=12, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute),
                               LAGOS)


class ArchiveApi207Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('archive207_editor')

    def setUp(self):
        self.client = APIClient()
        # Published 15 June 2026, 14:30 Lagos time.
        self.story = Campaign.objects.create(
            author=self.editor, title='Archive Target Story',
            slug='archive-target-story', status='PUBLISHED',
            content='Target body text.', story_id='KPN-SI-2026-00421',
            published_at=lagos_dt(2026, 6, 15, 14, 30))
        # Published ON the same date, just after midnight Lagos time
        # (23:30 UTC on 14 June) — the timezone-boundary case.
        self.early = Campaign.objects.create(
            author=self.editor, title='Early Morning Story',
            slug='early-morning-story', status='PUBLISHED',
            content='Early body text.', story_id='KPN-SI-2026-00422',
            published_at=lagos_dt(2026, 6, 15, 0, 30))
        # Outside every June range used below.
        self.other = Campaign.objects.create(
            author=self.editor, title='May Story', slug='may-story',
            status='PUBLISHED', content='May body text.',
            story_id='KPN-SI-2026-00423',
            published_at=lagos_dt(2026, 5, 20, 10, 0))

    def slugs(self, response):
        return {row['slug'] for row in response.data['stories']}

    # (i) Exact Story ID search.
    def test_exact_story_id_returns_the_story(self):
        response = self.client.get(API + 'archive/',
                                   {'q': 'KPN-SI-2026-00421'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['match_type'], 'story_id')
        self.assertEqual(response.data['story']['slug'], self.story.slug)
        self.assertEqual(response.data['story']['story_id'],
                         'KPN-SI-2026-00421')

    def test_lowercase_story_id_returns_the_story(self):
        response = self.client.get(API + 'archive/',
                                   {'q': 'kpn-si-2026-00421'})
        self.assertEqual(response.data['match_type'], 'story_id')
        self.assertEqual(response.data['story']['slug'], self.story.slug)

    def test_decorated_story_id_returns_the_story(self):
        for q in ('Story ID: KPN-SI-2026-00421', 'KPN-SI-2026-00421.',
                  '  KPN-SI-2026-00421  '):
            response = self.client.get(API + 'archive/', {'q': q})
            self.assertEqual(response.data['match_type'], 'story_id', q)
            self.assertEqual(response.data['story']['slug'],
                             self.story.slug, q)

    def test_story_id_parameter_returns_the_story(self):
        response = self.client.get(API + 'archive/',
                                   {'story_id': 'KPN-SI-2026-00421'})
        self.assertEqual(response.data['match_type'], 'story_id')
        self.assertEqual(response.data['story']['slug'], self.story.slug)

    def test_unknown_story_id_still_falls_through_to_empty_search(self):
        response = self.client.get(API + 'archive/',
                                   {'q': 'KPN-SI-2026-99999'})
        self.assertEqual(response.data['match_type'], 'search')
        self.assertEqual(response.data['stories_total'], 0)

    # (ii) A date range whose To equals the story's date.
    def test_to_date_equal_to_publication_date_matches(self):
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-15', 'date_to': '2026-06-15'})
        self.assertEqual(response.data['stories_total'], 2)
        self.assertEqual(self.slugs(response),
                         {self.story.slug, self.early.slug})

    def test_early_morning_story_matches_its_lagos_date(self):
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-14', 'date_to': '2026-06-14'})
        self.assertNotIn(self.early.slug, self.slugs(response))
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-15', 'date_to': '2026-06-15'})
        self.assertIn(self.early.slug, self.slugs(response))

    # (iii) A range spanning the story's date.
    def test_spanning_range_matches(self):
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-01', 'date_to': '2026-06-30'})
        self.assertEqual(response.data['stories_total'], 2)
        self.assertEqual(self.slugs(response),
                         {self.story.slug, self.early.slug})

    def test_range_excluding_the_story_does_not_match(self):
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-16', 'date_to': '2026-06-30'})
        self.assertEqual(response.data['stories_total'], 0)

    # Reversed and alternate-format ranges must not silently zero or
    # silently drop the filter.
    def test_reversed_range_is_ordered_not_zeroed(self):
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-30', 'date_to': '2026-06-01'})
        self.assertEqual(response.data['stories_total'], 2)
        self.assertEqual(response.data['params']['date_from'],
                         '2026-06-01')
        self.assertEqual(response.data['params']['date_to'], '2026-06-30')

    def test_datetime_form_dates_apply_the_filter(self):
        response = self.client.get(
            API + 'archive/',
            {'date_from': '2026-06-15T00:00:00',
             'date_to': '2026-06-15T23:59:59'})
        self.assertEqual(response.data['stories_total'], 2)

    def test_from_to_aliases_apply_the_filter(self):
        response = self.client.get(
            API + 'archive/',
            {'from': '2026-06-01', 'to': '2026-06-30'})
        self.assertEqual(response.data['stories_total'], 2)

    def test_text_search_within_range_still_works(self):
        response = self.client.get(
            API + 'archive/',
            {'q': 'Archive Target', 'date_from': '2026-06-01',
             'date_to': '2026-06-30'})
        self.assertEqual(response.data['stories_total'], 1)
        self.assertEqual(self.slugs(response), {self.story.slug})
