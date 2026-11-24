"""Phase 2 collection engine: connectors, dedupe, health, intake view.

The fetcher is mocked at the intelligence.connectors boundary — no
test touches the network or a non-allowlisted host. Parsing, the age
rule, canonicalisation and storage all run for real.
"""
from datetime import timedelta
from email.utils import format_datetime
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from editorial.fetch import FetchError
from editorial.models import Source
from editorial.tests.helpers import general_member, media_director
from intelligence import connectors, cycle
from intelligence.models import RawPublication, SourceHealth
from intelligence.sources_seed import STARTER_SOURCES, seed_sources


def rfc2822(dt):
    return format_datetime(dt)


def make_source(name='Feed Source', **kw):
    defaults = {'kind': 'NEWS', 'url': 'https://feeds.example.com/feed.xml',
                'feed': True, 'enabled': True, 'connector_kind': 'RSS',
                'max_items': 5}
    defaults.update(kw)
    return Source.objects.create(name=name, **defaults)


def feed_body(items):
    entries = ''.join(
        f'<item><title>{title}</title><link>{url}</link>'
        f'<pubDate>{date}</pubDate><description>{summary}</description></item>'
        for title, url, date, summary in items)
    return (f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<rss version="2.0"><channel><title>Example</title>'
            f'{entries}</channel></rss>').encode()


ARTICLE_HTML = (
    b'<html><body><article><h1>Kebbi Approves New Water Project</h1>'
    b'<p>The state government has approved a new water project for '
    b'communities in Birnin Kebbi and Kalgo.</p></article></body></html>')


class FeedConnectorTests(TestCase):
    def setUp(self):
        self.source = make_source()
        now = timezone.now()
        self.fresh1 = now - timedelta(hours=2)
        self.fresh2 = now - timedelta(days=1)
        self.old = now - timedelta(days=10)
        body = feed_body([
            ('Kebbi Approves New Water Project',
             'https://feeds.example.com/articles/water',
             rfc2822(self.fresh1), 'Water project summary.'),
            ('Youth Training Begins in Argungu',
             'https://feeds.example.com/articles/training',
             rfc2822(self.fresh2), 'Training summary.'),
            ('Old Story From Last Week',
             'https://feeds.example.com/articles/old',
             rfc2822(self.old), 'Old summary.'),
            ('Insecure Link Story',
             'http://feeds.example.com/articles/insecure',
             rfc2822(self.fresh1), 'Skipped: not HTTPS.'),
        ])

        def fake_fetch(url, allowed):
            if url == self.source.url:
                return body, self.source.url
            if url.endswith('/articles/water'):
                return ARTICLE_HTML, url
            raise FetchError('http_404')

        self.fetch = mock.patch(
            'intelligence.connectors.permitted_fetch', side_effect=fake_fetch)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    def test_feed_parses_into_raw_items(self):
        stored = connectors.collect_feed(self.source)
        self.assertEqual(stored, 2)
        self.assertEqual(RawPublication.objects.count(), 2)
        water = RawPublication.objects.get(
            canonical_url='https://feeds.example.com/articles/water')
        self.assertEqual(water.title, 'Kebbi Approves New Water Project')
        self.assertEqual(water.fetch_status, 'CONTENT')
        self.assertIn('water project', water.text)
        self.assertIsNotNone(water.published_at)
        self.assertLess(abs((water.published_at - self.fresh1).total_seconds()), 2)
        self.assertEqual(len(water.content_fingerprint), 64)
        self.assertEqual(water.source, self.source)

    def test_failed_article_fetch_still_stores_feed_summary(self):
        connectors.collect_feed(self.source)
        training = RawPublication.objects.get(
            canonical_url='https://feeds.example.com/articles/training')
        self.assertEqual(training.fetch_status, 'FEED_ONLY')
        self.assertEqual(training.summary, 'Training summary.')

    def test_stale_and_insecure_entries_are_dropped(self):
        connectors.collect_feed(self.source)
        titles = set(RawPublication.objects.values_list('title', flat=True))
        self.assertNotIn('Old Story From Last Week', titles)
        self.assertNotIn('Insecure Link Story', titles)

    def test_second_poll_stores_nothing_twice(self):
        self.assertEqual(connectors.collect_feed(self.source), 2)
        self.assertEqual(connectors.collect_feed(self.source), 0)
        self.assertEqual(RawPublication.objects.count(), 2)

    def test_tracking_parameters_do_not_defeat_dedupe(self):
        self.assertEqual(connectors.collect_feed(self.source), 2)
        body = feed_body([
            ('Kebbi Approves New Water Project',
             'https://feeds.example.com/articles/water?utm_source=feed',
             rfc2822(self.fresh1), 'Water project summary.'),
        ])
        with mock.patch('intelligence.connectors.permitted_fetch',
                        return_value=(body, self.source.url)):
            self.assertEqual(connectors.collect_feed(self.source), 0)
        self.assertEqual(RawPublication.objects.count(), 2)


LISTING_HTML = (
    b'<html><body><h1>Pressroom</h1>'
    b'<a href="/news/fresh-story">Governor flags off road project</a>'
    b'<a href="/news/old-story">Old announcement</a>'
    b'<a href="https://other.example.com/external">External story</a>'
    b'<a href="/">Home</a>'
    b'</body></html>')


def article_html(title, iso_date):
    return (
        f'<html><head><meta property="article:published_time" '
        f'content="{iso_date}"></head><body><article><h1>{title}</h1>'
        f'<p>Full text of the story about {title} in Kebbi State.</p>'
        f'</article></body></html>').encode()


class PageConnectorTests(TestCase):
    def setUp(self):
        self.source = make_source(
            name='Pressroom', url='https://gov.example.com/pressroom',
            feed=False, connector_kind='OFFICIAL_PAGE')
        self.fresh = timezone.now() - timedelta(hours=3)
        self.old = timezone.now() - timedelta(days=30)
        pages = {
            self.source.url: LISTING_HTML,
            'https://gov.example.com/news/fresh-story':
                article_html('Governor Flags Off Road Project',
                             self.fresh.isoformat()),
            'https://gov.example.com/news/old-story':
                article_html('Old Announcement', self.old.isoformat()),
        }

        def fake_fetch(url, allowed):
            if url in pages:
                return pages[url], url
            raise FetchError('http_404')

        self.fetch = mock.patch(
            'intelligence.connectors.permitted_fetch', side_effect=fake_fetch)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    def test_listing_page_extracts_fresh_articles(self):
        stored = connectors.collect_page(self.source)
        self.assertEqual(stored, 1)
        item = RawPublication.objects.get()
        self.assertEqual(
            item.canonical_url, 'https://gov.example.com/news/fresh-story')
        self.assertIn('Governor Flags Off Road Project', item.title)
        self.assertEqual(item.fetch_status, 'CONTENT')
        self.assertIsNotNone(item.published_at)
        self.assertLess(abs((item.published_at - self.fresh).total_seconds()), 2)

    def test_old_and_external_links_are_not_stored(self):
        connectors.collect_page(self.source)
        urls = set(RawPublication.objects.values_list('canonical_url', flat=True))
        self.assertNotIn('https://gov.example.com/news/old-story', urls)
        self.assertFalse(any('other.example.com' in url for url in urls))

    def test_page_without_links_is_stored_as_a_single_item(self):
        body = (b'<html><body><article><h1>Solo Announcement</h1>'
                b'<p>One monitored page with no outgoing links.</p>'
                b'</article></body></html>')
        with mock.patch('intelligence.connectors.permitted_fetch',
                        return_value=(body, self.source.url)):
            self.assertEqual(connectors.collect_page(self.source), 1)
        item = RawPublication.objects.get()
        self.assertEqual(item.canonical_url, self.source.url)
        self.assertIn('Solo Announcement', item.title)


class CycleCollectionTests(TestCase):
    def test_cycle_collects_isolates_failures_and_records_health(self):
        good = make_source('Good Feed')
        broken = make_source(
            'Broken Feed', url='https://broken.example.com/feed.xml')
        now = timezone.now()
        body = feed_body([
            ('Kebbi Approves New Water Project',
             'https://feeds.example.com/articles/water',
             rfc2822(now - timedelta(hours=1)), 'Water project summary.'),
        ])

        def fake_fetch(url, allowed):
            if url == good.url:
                return body, url
            if url.endswith('/articles/water'):
                return ARTICLE_HTML, url
            raise FetchError('network_failure')

        with mock.patch('intelligence.connectors.permitted_fetch',
                        side_effect=fake_fetch):
            run = cycle.run_cycle()
        self.assertEqual(run.status, 'COMPLETED')
        self.assertEqual(run.sources_due, 2)
        self.assertEqual(run.sources_ok, 1)
        self.assertEqual(run.sources_failed, 1)
        self.assertEqual(run.items_new, 1)
        self.assertEqual(RawPublication.objects.count(), 1)

        good_health = SourceHealth.objects.get(source=good)
        self.assertIsNotNone(good_health.last_success_at)
        self.assertEqual(good_health.consecutive_failures, 0)
        self.assertEqual(good_health.state(), 'OK')

        broken_health = SourceHealth.objects.get(source=broken)
        self.assertEqual(broken_health.consecutive_failures, 1)
        self.assertIn('network_failure', broken_health.last_error)
        self.assertEqual(broken_health.state(), 'FAILING')

        broken.refresh_from_db()
        self.assertEqual(broken.consecutive_failures, 1)
        self.assertIn('network_failure', broken.last_error)


class ItemsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.director = media_director('items_director')
        cls.member = general_member('items_member')

    def setUp(self):
        self.source_a = make_source('Source A')
        self.source_b = make_source(
            'Source B', url='https://b.example.com/feed.xml')
        RawPublication.objects.create(
            source=self.source_a, canonical_url='https://a.example.com/1',
            original_url='https://a.example.com/1', title='Alpha Item',
            fetch_status='CONTENT', content_fingerprint='a' * 64)
        RawPublication.objects.create(
            source=self.source_b, canonical_url='https://b.example.com/2',
            original_url='https://b.example.com/2', title='Beta Item',
            fetch_status='FEED_ONLY', content_fingerprint='b' * 64)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse('intelligence:items'))
        self.assertEqual(response.status_code, 302)

    def test_member_without_capability_is_refused(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('intelligence:items'))
        self.assertEqual(response.status_code, 403)

    def test_director_sees_collected_items(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('intelligence:items'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Item')
        self.assertContains(response, 'Beta Item')
        self.assertContains(response, '2 items collected')

    def test_filter_by_source_and_status(self):
        self.client.force_login(self.director)
        response = self.client.get(
            reverse('intelligence:items'), {'source': self.source_a.pk})
        self.assertContains(response, 'Alpha Item')
        self.assertNotContains(response, 'Beta Item')
        response = self.client.get(
            reverse('intelligence:items'), {'status': 'FEED_ONLY'})
        self.assertNotContains(response, 'Alpha Item')
        self.assertContains(response, 'Beta Item')


class StarterSourceSeedTests(TestCase):
    def test_seed_creates_the_doc05_set_with_safe_states(self):
        created = seed_sources()
        self.assertEqual(len(created), len(STARTER_SOURCES))
        self.assertEqual(Source.objects.count(), len(STARTER_SOURCES))
        pressroom = Source.objects.get(
            url='https://kebbistate.gov.ng/governor/pressroom')
        self.assertTrue(pressroom.enabled)
        self.assertEqual(pressroom.connector_kind, 'OFFICIAL_PAGE')
        others = Source.objects.exclude(pk=pressroom.pk)
        self.assertTrue(others.exists())
        self.assertFalse(others.filter(enabled=True).exists())

    def test_seed_is_idempotent_and_preserves_edits(self):
        seed_sources()
        pressroom = Source.objects.get(
            url='https://kebbistate.gov.ng/governor/pressroom')
        pressroom.name = 'Pressroom (edited)'
        pressroom.save()
        self.assertEqual(seed_sources(), [])
        self.assertEqual(Source.objects.count(), len(STARTER_SOURCES))
        pressroom.refresh_from_db()
        self.assertEqual(pressroom.name, 'Pressroom (edited)')

    def test_seed_command_runs(self):
        call_command('seed_intelligence_sources', verbosity=0)
        self.assertEqual(Source.objects.count(), len(STARTER_SOURCES))


class MapWordingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.director = media_director('map_director')

    def test_map_helper_sentence_works_without_a_map(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('intelligence:map'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'on the map or from the location list')
        self.assertContains(
            response, 'Select a local government area to see what is being tracked there')
