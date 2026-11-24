"""Phase 3: relevance engine, category rules, dedupe, clustering.

Everything runs on local fixtures — no network. The geographic
directory is the real seeded one (21 LGAs + approved starter aliases),
so alias behaviour is tested against production-shaped data.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from editorial.models import Source
from editorial.tests.helpers import (
    assistant_media, general_member, media_director, president,
)
from intelligence import cycle, relevance
from intelligence.connectors import _fingerprint
from intelligence.models import (
    Community, EventCluster, GeoAlias, GeoEntity, IntelligenceAudit,
    RawPublication,
)
from leadership.models import LGA

from .helpers import seed_directory


def make_source(name='Feed Source', **kw):
    defaults = {'kind': 'NEWS', 'url': 'https://feeds.example.com/feed.xml',
                'feed': True, 'enabled': True, 'connector_kind': 'RSS',
                'max_items': 5}
    defaults.update(kw)
    return Source.objects.create(name=name, **defaults)


def make_item(source, title, text='', summary='', published_at=None,
              discovered_at=None):
    count = RawPublication.objects.count() + 1
    url = f'https://example.com/story-{count}'
    return RawPublication.objects.create(
        source=source, canonical_url=url, original_url=url, title=title,
        summary=summary, text=text, published_at=published_at,
        discovered_at=discovered_at or timezone.now(),
        fetch_status='CONTENT',
        content_fingerprint=_fingerprint(title, text or summary))


class RelevanceEngineTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()
        self.jega = LGA.objects.get(name='Jega')
        self.argungu = LGA.objects.get(name='Argungu')

    def test_explicit_lga_mention_is_confirmed_with_reason(self):
        item = make_item(
            self.source, 'Governor Idris Flags Off Road Repairs in Jega',
            text='The governor flagged off township road repairs in Jega '
                 'on Monday, promising completion before the rains.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        locations = list(item.locations.all())
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0].lga, self.jega)
        self.assertEqual(locations[0].match_kind, 'EXPLICIT')
        details = ' '.join(r['detail'] for r in item.relevance_reasons)
        self.assertIn('Jega', details)

    def test_state_mention_is_confirmed(self):
        item = make_item(
            self.source, 'Kebbi State Government Releases Funds',
            text='The Kebbi State Government has released funds for '
                 'civil servants across the state.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        self.assertTrue(any(r['rule'] == 'state_mention'
                            for r in item.relevance_reasons))

    def test_approved_alias_only_mention_resolves(self):
        # "Wasagu" is an approved starter alias for Danko/Wasagu.
        item = make_item(
            self.source, 'Wasagu Farmers Receive Inputs',
            text='Farmers in Wasagu received fertiliser for the season.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        lgas = {loc.lga.name for loc in item.locations.all() if loc.lga}
        self.assertEqual(len(lgas), 1)
        self.assertIn('Wasagu', list(lgas)[0])

    def test_pending_alias_does_not_match_until_approved(self):
        community = Community.objects.create(name='Rafin Gora', lga=self.jega)
        alias = GeoAlias.objects.create(
            alias='Gora Town', target_kind='COMMUNITY', community=community,
            status='PENDING')
        item = make_item(
            self.source, 'Gora Town Residents Celebrate New Borehole',
            text='Residents of Gora Town turned out for the commissioning.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'NOT_RELEVANT')
        self.assertEqual(item.locations.count(), 0)
        # Once a reviewer approves the alias, reprocessing resolves it.
        alias.status = 'APPROVED'
        alias.save(update_fields=['status'])
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        self.assertEqual(item.locations.first().community, community)

    def test_geo_entity_mention_is_contextual_strong_possible(self):
        GeoEntity.objects.create(
            name='Sir Ahmadu Bello International Airport', kind='LANDMARK',
            lga=LGA.objects.get(name='Birnin Kebbi'))
        item = make_item(
            self.source, 'Flights Resume After Weather Delay',
            text='Passengers stranded overnight at the Sir Ahmadu Bello '
                 'International Airport finally departed on Tuesday.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'STRONG_POSSIBLE')
        location = item.locations.get()
        self.assertEqual(location.match_kind, 'CONTEXTUAL')
        self.assertIsNotNone(location.geo_entity)
        self.assertEqual(location.lga.name, 'Birnin Kebbi')

    def test_ambiguous_name_is_contextual_not_confirmed(self):
        Community.objects.create(name='Tungan Daji', lga=self.jega)
        Community.objects.create(
            name='Tungan Daji', lga=LGA.objects.get(name='Yauri'))
        item = make_item(
            self.source, 'Tungan Daji Market Reopens',
            text='Traders returned to Tungan Daji market on Saturday.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'STRONG_POSSIBLE')
        self.assertEqual(item.locations.count(), 2)
        self.assertTrue(all(loc.match_kind == 'CONTEXTUAL'
                            for loc in item.locations.all()))

    def test_source_home_lga_only_is_uncertain(self):
        local = make_source('Jega Community Radio', home_lga=self.jega)
        item = make_item(
            local, 'Traders Count Losses After Weekend Trading',
            text='Traders at the central market counted their losses '
                 'after a slow weekend of trading.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'UNCERTAIN')
        location = item.locations.get()
        self.assertEqual(location.lga, self.jega)
        self.assertEqual(location.match_kind, 'CONTEXTUAL')

    def test_non_kebbi_item_is_not_relevant(self):
        item = make_item(
            self.source, 'Lagos Governor Commissions Bridge in Ikeja',
            text='The Lagos State governor commissioned a new bridge '
                 'in Ikeja on Friday amid celebrations.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'NOT_RELEVANT')
        self.assertEqual(item.locations.count(), 0)
        self.assertTrue(any(r['rule'] == 'no_match'
                            for r in item.relevance_reasons))

    def test_multi_location_item_keeps_all_locations(self):
        item = make_item(
            self.source, 'Governor Inspects Projects in Jega and Argungu',
            text='The governor inspected projects in Jega in the morning '
                 'and travelled to Argungu later in the day.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        names = {loc.lga.name for loc in item.locations.all()}
        self.assertEqual(names, {'Jega', 'Argungu'})

    def test_reprocessing_is_idempotent(self):
        item = make_item(
            self.source, 'Flood Destroys Homes in Argungu',
            text='A flood destroyed homes in Argungu overnight as '
                 'relief materials arrived for displaced families.')
        relevance.process_publication(item)
        first = (item.locations.count(), item.category_links.count(),
                 len(item.relevance_reasons))
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(
            (item.locations.count(), item.category_links.count(),
             len(item.relevance_reasons)), first)
        self.assertEqual(EventCluster.objects.count(), 0)


class CategoryRuleTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()

    def test_category_rules_fire_with_reasons(self):
        item = make_item(
            self.source, 'Flood Destroys Homes in Argungu',
            text='A flood destroyed homes in Argungu overnight as '
                 'relief materials arrived for displaced families.')
        relevance.process_publication(item)
        slugs = {link.category.slug for link in item.category_links.all()}
        self.assertIn('emergencies-disasters', slugs)
        self.assertIn('humanitarian-affairs', slugs)
        primary = item.category_links.filter(is_primary=True)
        self.assertEqual(primary.count(), 1)
        for link in item.category_links.all():
            self.assertIn('Keywords matched', link.reason)

    def test_fire_outbreak_does_not_suggest_healthcare(self):
        item = make_item(
            self.source, 'Fire Outbreak Destroys Shops at Jega Market',
            text='A night fire destroyed several shops at the market '
                 'as firefighters battled the blaze for hours.')
        relevance.process_publication(item)
        slugs = {link.category.slug for link in item.category_links.all()}
        self.assertIn('emergencies-disasters', slugs)
        self.assertNotIn('healthcare', slugs)

    def test_no_rule_match_leaves_item_uncategorised(self):
        item = make_item(
            self.source, 'Global Oil Prices Rise Amid Supply Concerns',
            text='Prices climbed on Tuesday as traders assessed supply '
                 'data from Asia and Europe.')
        relevance.process_publication(item)
        self.assertEqual(item.category_links.count(), 0)


class DedupeTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()
        self.other = make_source('Second Source')

    def test_near_duplicate_titles_are_linked_not_deleted(self):
        first = make_item(
            self.source,
            'Governor Idris Flags Off Birnin Kebbi Township Road Repairs',
            text='The governor flagged off the repairs on Monday.')
        second = make_item(
            self.other,
            'Governor Idris Flags Off Birnin Kebbi Township Road Repair Works',
            text='Reports say the governor launched the road works '
                 'in the state capital on Monday.')
        relevance.process_publication(first)
        relevance.process_publication(second)
        second.refresh_from_db()
        self.assertEqual(second.duplicate_of, first)
        # Evidence preservation: both records still exist.
        self.assertEqual(RawPublication.objects.count(), 2)

    def test_identical_content_fingerprint_is_linked(self):
        body = 'The state government has approved the project.'
        first = make_item(self.source, 'Water Project Approved', text=body)
        second = make_item(self.other, 'Water Project Approved', text=body)
        self.assertEqual(first.content_fingerprint, second.content_fingerprint)
        relevance.process_publication(second)
        second.refresh_from_db()
        self.assertEqual(second.duplicate_of, first)

    def test_dissimilar_titles_are_not_linked(self):
        first = make_item(
            self.source, 'Kebbi Approves New Water Project',
            text='The state government approved a water project.')
        second = make_item(
            self.other, 'Argungu Fishing Festival Committee Meets',
            text='The organising committee met to plan the festival.')
        relevance.process_publication(first)
        relevance.process_publication(second)
        second.refresh_from_db()
        self.assertIsNone(second.duplicate_of)


class ClusteringTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()
        self.other = make_source('Second Source')
        self.now = timezone.now()

    def _fire_items(self):
        first = make_item(
            self.source, 'Fire Outbreak Destroys Shops at Jega Market',
            text='A night fire has destroyed several shops at the Jega '
                 'main market, with traders counting losses estimated '
                 'in millions of naira as firefighters battled the '
                 'blaze for hours.',
            published_at=self.now - timedelta(hours=1))
        second = make_item(
            self.other, 'Fire Outbreak Guts Shops in Jega Market',
            text='Shop owners in Jega woke to the aftermath of an '
                 'inferno that gutted rows of stalls overnight, while '
                 'officials promised an investigation into the cause '
                 'of the fire.',
            published_at=self.now)
        return first, second

    def test_same_event_items_cluster(self):
        first, second = self._fire_items()
        relevance.process_pending()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(EventCluster.objects.count(), 1)
        cluster = EventCluster.objects.get()
        self.assertIsNotNone(first.cluster)
        self.assertEqual(first.cluster, second.cluster)
        self.assertEqual(cluster.publications.count(), 2)
        self.assertEqual(cluster.category.slug, 'emergencies-disasters')
        self.assertEqual(cluster.primary_lga.name, 'Jega')
        earliest, latest = cluster.member_times()
        self.assertEqual(earliest, self.now - timedelta(hours=1))
        self.assertEqual(latest, self.now)

    def test_similar_titles_in_different_lgas_do_not_cluster(self):
        first = make_item(
            self.source, 'Kebbi Government Approves New Classrooms in Jega',
            text='The government approved new classrooms for schools '
                 'in Jega on Monday.')
        second = make_item(
            self.other, 'Kebbi Government Approves New Classrooms in Argungu',
            text='The government approved new classrooms for schools '
                 'in Argungu on Monday.')
        relevance.process_pending()
        self.assertEqual(EventCluster.objects.count(), 0)

    def test_different_categories_same_lga_do_not_cluster(self):
        first, _second = self._fire_items()
        other = make_item(
            self.other, 'Jega Market Traders Elect New Chairman',
            text='Traders at the Jega market elected a new chairman '
                 'for their association on Saturday.',
            published_at=self.now)
        relevance.process_pending()
        first.refresh_from_db()
        other.refresh_from_db()
        if first.cluster_id and other.cluster_id:
            self.assertNotEqual(first.cluster_id, other.cluster_id)
        self.assertTrue(first.cluster_id is None or other.cluster_id is None
                        or first.cluster_id != other.cluster_id)

    def test_clustering_is_idempotent_on_reprocess(self):
        first, second = self._fire_items()
        relevance.process_pending()
        self.assertEqual(EventCluster.objects.count(), 1)
        relevance.process_publication(first)
        relevance.process_publication(second)
        self.assertEqual(EventCluster.objects.count(), 1)
        self.assertEqual(EventCluster.objects.get().publications.count(), 2)


class ManualOverrideTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()
        self.director = media_director()

    def test_manual_classification_survives_reprocessing(self):
        item = make_item(
            self.source, 'Governor Idris Flags Off Road Repairs in Jega',
            text='The governor flagged off township road repairs in Jega.')
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        relevance.set_manual_relevance(item, 'UNCERTAIN', self.director)
        relevance.process_publication(item)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'UNCERTAIN')
        self.assertTrue(item.relevance_manual)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='RELEVANCE_MANUAL', target_id=item.pk).exists())
        self.assertTrue(any(r['rule'] == 'manual_override'
                            for r in item.relevance_reasons))

    def test_reclassify_view_requires_review_capability(self):
        item = make_item(self.source, 'A Story From Somewhere',
                         text='Nothing geographic is named here.')
        relevance.process_publication(item)
        url = reverse('intelligence:item_reclassify', args=[item.pk])
        # The President can view intelligence but cannot review it.
        self.client.force_login(president())
        response = self.client.post(url, {'relevance': 'UNCERTAIN'})
        self.assertEqual(response.status_code, 403)
        # The Assistant Director holds REVIEW_INTELLIGENCE.
        self.client.force_login(assistant_media())
        response = self.client.post(url, {'relevance': 'UNCERTAIN'})
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'UNCERTAIN')
        self.assertTrue(item.relevance_manual)


class DashboardProcessingTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()
        self.director = media_director()
        self.member = general_member()

    def test_items_filter_by_relevance(self):
        confirmed = make_item(
            self.source, 'Governor Idris Flags Off Road Repairs in Jega',
            text='The governor flagged off township road repairs in Jega.')
        irrelevant = make_item(
            self.source, 'Lagos Governor Commissions Bridge in Ikeja',
            text='The Lagos State governor commissioned a bridge in Ikeja.')
        relevance.process_pending()
        self.client.force_login(self.director)
        response = self.client.get(
            reverse('intelligence:items'), {'relevance': 'CONFIRMED'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, confirmed.title)
        self.assertNotContains(response, irrelevant.title)
        self.assertContains(response, 'Confirmed relevance')

    def test_clusters_views_gating_and_detail(self):
        first = make_item(
            self.source, 'Fire Outbreak Destroys Shops at Jega Market',
            text='A night fire destroyed several shops at the Jega main '
                 'market as firefighters battled the blaze for hours.',
            published_at=timezone.now() - timedelta(hours=1))
        second = make_item(
            self.source, 'Fire Outbreak Guts Shops in Jega Market',
            text='Shop owners in Jega woke to an inferno that gutted '
                 'rows of stalls overnight, while officials promised '
                 'an investigation.',
            published_at=timezone.now())
        relevance.process_pending()
        cluster = EventCluster.objects.get()
        list_url = reverse('intelligence:clusters')
        detail_url = reverse('intelligence:cluster_detail', args=[cluster.pk])
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 302)  # anonymous -> login
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(list_url).status_code, 403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(list_url).status_code, 200)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first.title)
        self.assertContains(response, second.title)


class CycleProcessingTests(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source(enabled=False)

    def test_cycle_processes_waiting_items(self):
        item = make_item(
            self.source, 'Governor Idris Flags Off Road Repairs in Jega',
            text='The governor flagged off township road repairs in Jega.')
        run = cycle.run_cycle(trigger='MANUAL')
        self.assertEqual(run.status, 'COMPLETED')
        item.refresh_from_db()
        self.assertEqual(item.relevance, 'CONFIRMED')
        self.assertIsNotNone(item.processed_at)
        stats = relevance.process_pending()
        self.assertEqual(stats['processed'], 0)
