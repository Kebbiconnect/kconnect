"""Page-by-Page Upgrade Priority 4 — Story Archive (brief §G, D-13).

The archive's existing behaviour (search, Story ID lookup, filters,
privacy) is pinned by test_archive.py and must not regress. These
tests cover what Priority 4 adds: the photographic hero, the topic
axis (section membership via StoryProfile.kind / Promise records),
claims search, record-status markers derived from Correction and
StoryUpdate existence, section badging and cross-links (Promise
Tracker / Human Impact Files / Future Signal — linked records, not
copies), related stories, and the premium empty states.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from leadership.models import LGA, Ward, Zone
from story_intelligence.models import (
    Claim, Correction, Institution, Promise, StoryProfile, StoryUpdate,
)

ARCHIVE_URL = reverse('archive:home')


def aware_days_ago(days):
    return timezone.now() - timedelta(days=days)


class Priority4Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p4_editor')
        cls.zone = Zone.objects.create(name='Kebbi Central')
        cls.lga = LGA.objects.create(name='Argungu', zone=cls.zone)
        cls.other_lga = LGA.objects.create(name='Yauri', zone=cls.zone)
        cls.ward = Ward.objects.create(name='Gulma', lga=cls.lga)

        cls.news_story = Campaign.objects.create(
            author=cls.editor, title='Market Reopens in Argungu',
            slug='market-reopens-argungu', status='PUBLISHED',
            content='Traders returned to the stalls on Monday.',
            category='MARKETS', lga=cls.lga, location='Argungu',
            story_id='KPN-SI-2026-00201', published_at=aware_days_ago(3))
        # Same LGA, different category — related to the news story.
        cls.neighbour = Campaign.objects.create(
            author=cls.editor, title='Clinic Outreach Visits Gulma',
            slug='clinic-outreach-gulma', status='PUBLISHED',
            content='A health team visited the ward this week.',
            category='HEALTH', ward=cls.ward,
            story_id='KPN-SI-2026-00202', published_at=aware_days_ago(1))
        # Different LGA and category, no profile — plain news, and NOT
        # related to the Argungu market story.
        cls.far_story = Campaign.objects.create(
            author=cls.editor, title='Yauri Farmers Count the Harvest',
            slug='yauri-farmers-harvest', status='PUBLISHED',
            content='Rice yields were weighed at the cooperative.',
            category='AGRICULTURE', lga=cls.other_lga,
            story_id='KPN-SI-2026-00203', published_at=aware_days_ago(2))

        cls.impact_story = Campaign.objects.create(
            author=cls.editor, title='The Widow Who Rebuilt Her Stall',
            slug='widow-rebuilt-stall', status='PUBLISHED',
            content='Her story, told with her consent.',
            category='HUMAN_INTEREST', lga=cls.lga,
            story_id='KPN-SI-2026-00204', published_at=aware_days_ago(4))
        StoryProfile.objects.create(
            article=cls.impact_story, kind='IMPACT',
            who_is_affected='Traders at the Argungu market')

        cls.signal_story = Campaign.objects.create(
            author=cls.editor, title='Dry Season Water Levels to Watch',
            slug='dry-season-water-levels', status='PUBLISHED',
            content='An evidence-led look at the river levels.',
            category='ENVIRONMENT', lga=cls.other_lga,
            story_id='KPN-SI-2026-00205', published_at=aware_days_ago(5))
        StoryProfile.objects.create(
            article=cls.signal_story, kind='SIGNAL',
            signal_observation='River levels are falling earlier.')

        # A published update and a published correction on the news
        # story; a draft update and an unpublished correction must
        # never be counted.
        cls.update = StoryUpdate.objects.create(
            article=cls.news_story, title='Stall Allocation List Published',
            body='The council published the allocation list.',
            status='PUBLISHED', published_at=aware_days_ago(1),
            author=cls.editor)
        StoryUpdate.objects.create(
            article=cls.news_story, title='Draft Follow Up',
            body='Not yet published.', status='DRAFT', author=cls.editor)
        Correction.objects.create(
            article=cls.news_story, kind='CORRECTION',
            text='The market has 240 stalls, not 420.',
            published=True, created_by=cls.editor)
        Correction.objects.create(
            article=cls.news_story, kind='CLARIFICATION',
            text='An unpublished clarification.', published=False,
            created_by=cls.editor)
        # A correction attached to the update itself.
        Correction.objects.create(
            article=cls.news_story, update=cls.update, kind='CORRECTION',
            text='The list covers 240 stalls.', published=True,
            created_by=cls.editor)

        # Public claims: searchable, and the only claim text a reader
        # can already see on the article's Story File panel.
        Claim.objects.create(
            article=cls.news_story, status='CONFIRMED',
            text='The council allocated 240 stalls to traders.')
        Claim.objects.create(
            article=cls.news_story, update=cls.update, status='DEVELOPING',
            text='Allocation letters carry a quorix verification code.')

        cls.institution = Institution.objects.create(
            name='Argungu Local Government', kind='LGA_GOVERNMENT')
        cls.promise = Promise.objects.create(
            institution=cls.institution,
            title='Rebuild the Argungu market stalls',
            description='The council promised new stalls at the market.',
            announced_on='2026-09-01', lga=cls.lga, created_by=cls.editor)
        cls.promise.stories.add(cls.news_story)

    def slugs(self, response, key='stories_page'):
        return [a.slug for a in response.context[key].object_list]


class Priority4HeroAndChromeTests(Priority4Fixture):
    def test_hero_photo_renders_without_credit(self):
        response = self.client.get(ARCHIVE_URL)
        content = response.content.decode()
        # Manifest storage hash-suffixes the file name in the URL.
        self.assertIn('archive-hero', content)
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotIn(
            'Kanta Museum, Argungu, Kebbi State — Photo: Türkiye Today',
            content)
        self.assertNotIn('kpn-hero-credit', content)
        # Brief §G purpose wording, verbatim.
        self.assertIn('searchable institutional memory', content)

    def test_topic_filter_is_offered_with_d13_choices(self):
        response = self.client.get(ARCHIVE_URL)
        content = response.content.decode()
        self.assertIn('name="topic"', content)
        for label in ['News', 'Human Impact Files', 'Future Signal',
                      'Promise Tracker']:
            self.assertIn(label, content)

    def test_institution_filter_behaviour_is_documented(self):
        response = self.client.get(ARCHIVE_URL)
        self.assertIn('applies to Promise Tracker records',
                      response.content.decode())

    def test_record_counts_and_connected_sections_band(self):
        response = self.client.get(ARCHIVE_URL)
        counts = response.context['record_counts']
        self.assertEqual(counts['stories'], 5)
        self.assertEqual(counts['promises'], 1)
        self.assertEqual(counts['impact'], 1)
        self.assertEqual(counts['signal'], 1)
        content = response.content.decode()
        self.assertIn(reverse('promises:list'), content)
        self.assertIn(reverse('impact_files:list'), content)
        self.assertIn(reverse('signals:list'), content)


class Priority4TopicFilterTests(Priority4Fixture):
    def test_topic_impact_returns_only_impact_stories(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'impact'})
        self.assertEqual(self.slugs(response), ['widow-rebuilt-stall'])
        self.assertEqual(response.context['promises_total'], 0)

    def test_topic_signal_returns_only_signal_stories(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'signal'})
        self.assertEqual(self.slugs(response), ['dry-season-water-levels'])

    def test_topic_news_covers_unprofiled_and_news_profile_stories(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'news'})
        self.assertEqual(set(self.slugs(response)), {
            'market-reopens-argungu', 'clinic-outreach-gulma',
            'yauri-farmers-harvest'})

    def test_topic_promise_returns_only_promises(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'promise'})
        self.assertEqual(response.context['stories_total'], 0)
        self.assertEqual(response.context['promises_total'], 1)

    def test_topic_composes_with_search_and_type(self):
        response = self.client.get(
            ARCHIVE_URL, {'topic': 'impact', 'q': 'Widow'})
        self.assertEqual(self.slugs(response), ['widow-rebuilt-stall'])
        response = self.client.get(
            ARCHIVE_URL, {'topic': 'news', 'q': 'Widow'})
        self.assertEqual(response.context['stories_total'], 0)

    def test_invalid_topic_is_ignored(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'banana'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['params']['topic'], '')


class Priority4ClaimsSearchTests(Priority4Fixture):
    def test_story_found_by_its_claim_text(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'allocated 240 stalls'})
        self.assertEqual(self.slugs(response), ['market-reopens-argungu'])

    def test_update_found_by_its_claim_text(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'quorix'})
        self.assertEqual(response.context['updates_total'], 1)
        update = response.context['updates_page'].object_list[0]
        self.assertEqual(update.title, 'Stall Allocation List Published')

    def test_claim_match_does_not_duplicate_the_story(self):
        # 'stalls' matches the story title, body and a claim at once.
        response = self.client.get(
            ARCHIVE_URL, {'q': 'stalls', 'type': 'story'})
        self.assertEqual(
            self.slugs(response).count('market-reopens-argungu'), 1)


class Priority4RowMarkerTests(Priority4Fixture):
    def test_corrected_and_updated_markers_come_from_records(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Market Reopens'})
        story = response.context['stories_page'].object_list[0]
        # Two published corrections sit on the story's record (one on
        # the article, one on its update — both show on the article's
        # Story File); the unpublished clarification never counts.
        # One published update (the draft update is excluded).
        self.assertEqual(story.correction_count, 2)
        self.assertEqual(story.update_count, 1)
        content = response.content.decode()
        self.assertIn('Corrected', content)
        self.assertIn('Updated', content)
        self.assertIn('Record status: Published', content)

    def test_story_without_history_has_no_markers(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Yauri Farmers'})
        story = response.context['stories_page'].object_list[0]
        self.assertEqual(story.correction_count, 0)
        self.assertEqual(story.update_count, 0)

    def test_update_row_carries_its_own_correction_count(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Allocation List'})
        update = response.context['updates_page'].object_list[0]
        self.assertEqual(update.correction_count, 1)


class Priority4CrossLinkTests(Priority4Fixture):
    def test_impact_row_badges_and_links_to_its_section(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'impact'})
        content = response.content.decode()
        self.assertIn('Human Impact File', content)
        self.assertIn(reverse('impact_files:list'), content)
        story = response.context['stories_page'].object_list[0]
        self.assertEqual(story.section_kind, 'IMPACT')

    def test_signal_row_badges_and_links_to_its_section(self):
        response = self.client.get(ARCHIVE_URL, {'topic': 'signal'})
        content = response.content.decode()
        self.assertIn('Future Signal', content)
        self.assertIn(reverse('signals:list'), content)

    def test_story_row_links_its_tracked_promise(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Market Reopens'})
        story = response.context['stories_page'].object_list[0]
        self.assertEqual([p.pk for p in story.linked_promises],
                         [self.promise.pk])
        self.assertIn(reverse('promises:detail', args=[self.promise.pk]),
                      response.content.decode())

    def test_promise_row_links_back_to_its_story(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'market stalls'})
        promise = response.context['promises_page'].object_list[0]
        self.assertEqual([s.slug for s in promise.linked_stories],
                         ['market-reopens-argungu'])
        self.assertIn('Covered in:', response.content.decode())


class Priority4RelatedStoriesTests(Priority4Fixture):
    def test_related_stories_share_lga_or_category(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Market Reopens'})
        story = response.context['stories_page'].object_list[0]
        related = {s.slug for s in story.related_stories}
        # Same LGA (via the ward) — related. Different LGA and
        # category — not related.
        self.assertIn('clinic-outreach-gulma', related)
        self.assertNotIn('yauri-farmers-harvest', related)
        self.assertNotIn('market-reopens-argungu', related)

    def test_related_stories_are_published_only(self):
        Campaign.objects.create(
            author=self.editor, title='Draft Neighbour',
            slug='draft-neighbour', status='DRAFT',
            content='Not public.', category='MARKETS', lga=self.lga)
        response = self.client.get(ARCHIVE_URL, {'q': 'Market Reopens'})
        story = response.context['stories_page'].object_list[0]
        self.assertNotIn('draft-neighbour',
                         {s.slug for s in story.related_stories})


class Priority4EmptyStateTests(TestCase):
    def test_empty_archive_browsing_state(self):
        response = self.client.get(ARCHIVE_URL)
        content = response.content.decode()
        self.assertIn('No stories in the archive yet', content)

    def test_no_match_search_state(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'zzzznothing'})
        content = response.content.decode()
        self.assertIn('No records match your search', content)
        self.assertEqual(response.context['total_results'], 0)
