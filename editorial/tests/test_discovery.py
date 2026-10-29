from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from editorial import discovery
from editorial.fetch import FetchError
from editorial.models import Item, Job, Source

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example News</title>
<item><title>Kebbi youths launch reading programme</title>
<link>https://example.com/story-1</link>
<description>A programme for Kebbi youths.</description></item>
<item><title>Lagos traffic update</title>
<link>https://example.com/story-2</link>
<description>Nothing about the north.</description></item>
</channel></rss>"""

ARTICLE = ('<html><body><article><p>' + ('Kebbi reading programme details for young people in Birnin Kebbi. ' * 8) +
           '</p></article></body></html>').encode()


class EntriesTests(SimpleTestCase):
    def test_rss_entries_parsed(self):
        rows = discovery.entries(RSS, 'https://example.com/feed')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['title'], 'Kebbi youths launch reading programme')
        self.assertEqual(rows[0]['url'], 'https://example.com/story-1')

    def test_doctype_rejected_as_unsafe_xml(self):
        with self.assertRaises(FetchError):
            discovery.entries(b'<!DOCTYPE rss><rss></rss>', 'https://example.com/feed')

    def test_invalid_feed_rejected(self):
        with self.assertRaises(FetchError):
            discovery.entries(b'not xml at all', 'https://example.com/feed')

    def test_old_and_future_dates_flagged(self):
        self.assertTrue(discovery.is_old('Mon, 01 Jan 2018 00:00:00 +0000'))
        self.assertFalse(discovery.is_old(''))
        import datetime
        from django.utils import timezone
        recent = (timezone.now() - datetime.timedelta(hours=2)).strftime('%a, %d %b %Y %H:%M:%S +0000')
        self.assertFalse(discovery.is_old(recent))


@override_settings(KPN_EDITORIAL_DAILY_DRAFTS=5)
class DiscoverTests(TestCase):
    def _source(self, **kw):
        defaults = dict(name='Example', kind='NEWS', url='https://example.com/feed', enabled=True, feed=True)
        defaults.update(kw)
        return Source.objects.create(**defaults)

    def _fetch(self, url, hosts):
        if url.endswith('/feed'):
            return RSS, 'https://example.com/feed'
        return ARTICLE, url

    def test_discovers_matching_news_and_queues_drafting(self):
        source = self._source()
        with mock.patch.object(discovery, 'permitted_fetch', side_effect=self._fetch):
            count = discovery.discover(source)
        self.assertEqual(count, 1)
        item = Item.objects.get(kind='NEWS')
        self.assertEqual(item.state, 'WAITING')
        self.assertTrue(Job.objects.filter(item=item, kind='GENERATE', state='QUEUED').exists())

    def test_keyword_filter_skips_unrelated_news(self):
        source = self._source()
        with mock.patch.object(discovery, 'permitted_fetch', side_effect=self._fetch):
            discovery.discover(source)
        self.assertFalse(Item.objects.filter(title__icontains='Lagos').exists())

    def test_disabled_source_does_nothing(self):
        source = self._source(enabled=False)
        with mock.patch.object(discovery, 'permitted_fetch', side_effect=self._fetch) as fetch_mock:
            self.assertEqual(discovery.discover(source), 0)
        fetch_mock.assert_not_called()

    def test_second_run_does_not_duplicate_items(self):
        source = self._source()
        with mock.patch.object(discovery, 'permitted_fetch', side_effect=self._fetch):
            discovery.discover(source)
            discovery.discover(source)
        self.assertEqual(Item.objects.filter(kind='NEWS').count(), 1)

    def test_daily_draft_cap_stops_discovery(self):
        source = self._source()
        Item.objects.create(key='existing-today', kind='NEWS', title='Already today')
        with override_settings(KPN_EDITORIAL_DAILY_DRAFTS=1):
            with mock.patch.object(discovery, 'permitted_fetch', side_effect=self._fetch):
                self.assertEqual(discovery.discover(source), 0)

    def test_duplicate_title_creates_alert_not_draft(self):
        from campaigns.models import Campaign
        from editorial.tests.helpers import make_user
        author = make_user('dup_author', title='President')
        Campaign.objects.create(author=author, title='Kebbi youths launch reading programme',
                                slug='kebbi-youths-launch-reading-programme', status='PUBLISHED')
        source = self._source()
        with mock.patch.object(discovery, 'permitted_fetch', side_effect=self._fetch):
            discovery.discover(source)
        self.assertTrue(Item.objects.filter(kind='DUPLICATE').exists())
        self.assertFalse(Item.objects.filter(kind='NEWS').exists())
