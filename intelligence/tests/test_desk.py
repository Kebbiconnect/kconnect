"""Phase 4: verification desk — state machine, recorded decisions,
capability gating, merge/split with engine respect, Lane 2
human-gated draft conversion, and Lane 1 (Brain) isolation.

Everything runs on local fixtures — no network.
"""
import json
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from campaigns.services import publish_campaign
from editorial.models import Item
from editorial.tests.helpers import (
    assistant_media, general_member, make_user, media_director, president,
)
from intelligence import desk, relevance
from intelligence.connectors import _fingerprint
from intelligence.models import (
    ClusterExclusion, EventCluster, IntelligenceAudit, IntelligenceCategory,
    PublicationCategory, PublicationLocation, RawPublication,
    ReviewDecision,
)
from leadership.models import LGA
from story_intelligence.models import EvidenceRecord

from .helpers import seed_directory
from .test_processing import make_item, make_source

TOKEN = 'desk-test-token'
AUTH = {'HTTP_AUTHORIZATION': f'Bearer {TOKEN}'}

PATHS = {
    'UNDER_REVIEW': ['TRIAGE'],
    'VERIFICATION_IN_PROGRESS': ['TRIAGE', 'BEGIN_VERIFICATION'],
    'NEEDS_INFO': ['TRIAGE', 'REQUEST_INFO'],
    'VERIFIED': ['TRIAGE', 'BEGIN_VERIFICATION', 'VERIFY'],
    'APPROVED': ['TRIAGE', 'BEGIN_VERIFICATION', 'VERIFY', 'APPROVE'],
    'REJECTED': ['TRIAGE', 'REJECT'],
    'DUPLICATE': ['MARK_DUPLICATE'],
}


def walk(unit, actor, target):
    for action in PATHS[target]:
        note = 'Documented reason.' if action in ('REJECT', 'REQUEST_INFO') else ''
        desk.apply_transition(unit, actor, action, note=note)
    unit.refresh_from_db()
    return unit


def categorise(item, slug='education', primary=True):
    category = IntelligenceCategory.objects.get(slug=slug)
    PublicationCategory.objects.create(
        publication=item, category=category, is_primary=primary,
        reason='Test fixture.')
    return category


def locate(item, lga):
    return PublicationLocation.objects.create(
        publication=item, match_kind='EXPLICIT', lga=lga,
        matched_text=lga.name, confidence=1.0)


def make_cluster(items, slug='education', lga=None, title=None):
    category = IntelligenceCategory.objects.get(slug=slug)
    cluster = EventCluster.objects.create(
        title=title or items[0].title, category=category, primary_lga=lga)
    for item in items:
        item.cluster = cluster
        item.save(update_fields=['cluster'])
    return cluster


class DeskFixture(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('desk_director')
        self.assistant = assistant_media('desk_assistant')
        self.monitoring = make_user(
            'desk_monitoring', title='Director of Monitoring & Compliance')
        self.president = president('desk_president')
        self.member = general_member('desk_member')
        self.source = make_source('Desk Source')
        self.jega = LGA.objects.get(name='Jega')

    def make_unit(self, slug='education', items=2):
        base = RawPublication.objects.count()
        pubs = []
        for index in range(items):
            pub = make_item(
                self.source, f'Jega School Report {base + index + 1}',
                text=f'Body of report {index + 1} about a school in Jega.',
                published_at=timezone.now() - timedelta(hours=index + 1))
            categorise(pub, slug)
            locate(pub, self.jega)
            pubs.append(pub)
        if len(pubs) == 1:
            return pubs[0]
        return make_cluster(pubs, slug=slug, lga=self.jega)


class StateMachineTests(DeskFixture):
    def test_happy_path_cluster_records_every_decision(self):
        unit = self.make_unit()
        walk(unit, self.director, 'APPROVED')
        self.assertEqual(unit.desk_state, 'APPROVED')
        decisions = list(unit.review_decisions.all())
        self.assertEqual(
            [d.action for d in decisions],
            ['TRIAGE', 'BEGIN_VERIFICATION', 'VERIFY', 'APPROVE'])
        self.assertEqual(decisions[0].from_state, 'DISCOVERED')
        self.assertEqual(decisions[0].to_state, 'UNDER_REVIEW')
        self.assertEqual(decisions[-1].to_state, 'APPROVED')
        self.assertTrue(all(d.actor == self.director for d in decisions))
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='DESK_VERIFY', target_type='EventCluster',
            target_id=unit.pk).exists())

    def test_happy_path_standalone_item(self):
        unit = self.make_unit(items=1)
        walk(unit, self.assistant, 'VERIFIED')
        self.assertEqual(unit.desk_state, 'VERIFIED')
        self.assertEqual(unit.review_decisions.count(), 3)

    def test_illegal_transitions_are_refused(self):
        unit = self.make_unit()
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'VERIFY')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'APPROVE')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'BEGIN_VERIFICATION')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'NOT_A_REAL_ACTION')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'DISCOVERED')
        self.assertEqual(unit.review_decisions.count(), 0)

    def test_terminal_states_accept_no_transitions(self):
        unit = self.make_unit()
        walk(unit, self.director, 'REJECTED')
        desk.apply_transition(unit, self.director, 'ARCHIVE')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'TRIAGE')

    def test_reject_requires_a_reason(self):
        unit = self.make_unit()
        desk.apply_transition(unit, self.director, 'TRIAGE')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'REJECT', note='  ')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'UNDER_REVIEW')
        desk.apply_transition(unit, self.director, 'REJECT',
                              note='Single unverified social post.')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'REJECTED')
        decision = unit.review_decisions.get(action='REJECT')
        self.assertEqual(decision.note, 'Single unverified social post.')

    def test_request_info_requires_note_and_resume_returns(self):
        unit = self.make_unit()
        desk.apply_transition(unit, self.director, 'TRIAGE')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'REQUEST_INFO')
        desk.apply_transition(unit, self.director, 'REQUEST_INFO',
                              note='Need the official statement.')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'NEEDS_INFO')
        desk.apply_transition(unit, self.director, 'RESUME')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'UNDER_REVIEW')

    def test_dispute_and_reopen(self):
        unit = self.make_unit()
        walk(unit, self.director, 'VERIFIED')
        desk.apply_transition(unit, self.director, 'DISPUTE',
                              note='Figures conflict between reports.')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'DISPUTED')
        desk.apply_transition(unit, self.director, 'REOPEN')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'VERIFICATION_IN_PROGRESS')

    def test_mark_duplicate_from_discovered(self):
        unit = self.make_unit(items=1)
        desk.apply_transition(unit, self.assistant, 'MARK_DUPLICATE')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'DUPLICATE')


class CapabilityGatingTests(DeskFixture):
    def test_member_cannot_transition(self):
        unit = self.make_unit()
        with self.assertRaises(PermissionDenied):
            desk.apply_transition(unit, self.member, 'TRIAGE')

    def test_verify_needs_verify_capability(self):
        # The President can view intelligence but holds no desk
        # transition capability at all.
        unit = self.make_unit()
        with self.assertRaises(PermissionDenied):
            desk.apply_transition(unit, self.president, 'TRIAGE')

    def test_sensitive_approval_needs_second_capability(self):
        unit = self.make_unit(slug='security-public-safety')
        walk(unit, self.assistant, 'VERIFIED')
        # Assistant holds APPROVE_INTELLIGENCE but not APPROVE_SENSITIVE.
        with self.assertRaises(PermissionDenied):
            desk.apply_transition(unit, self.assistant, 'APPROVE')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'VERIFIED')
        # The President holds APPROVE_SENSITIVE but not
        # APPROVE_INTELLIGENCE (security-desk holders per D6).
        with self.assertRaises(PermissionDenied):
            desk.apply_transition(unit, self.president, 'APPROVE')
        # The Director of Media holds both.
        desk.apply_transition(unit, self.director, 'APPROVE')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'APPROVED')

    def test_plain_approval_by_assistant(self):
        unit = self.make_unit()
        walk(unit, self.assistant, 'APPROVED')
        self.assertEqual(unit.desk_state, 'APPROVED')

    def test_assign_reviewer_records_decision(self):
        unit = self.make_unit()
        desk.assign_reviewer(unit, self.director, self.assistant)
        unit.refresh_from_db()
        self.assertEqual(unit.assigned_to, self.assistant)
        decision = unit.review_decisions.get(action='ASSIGN')
        self.assertEqual(decision.from_state, decision.to_state)

    def test_assign_requires_desk_capable_assignee(self):
        unit = self.make_unit()
        with self.assertRaises(desk.DeskError):
            desk.assign_reviewer(unit, self.director, self.member)

    def test_desk_pages_gate_by_capability(self):
        unit = self.make_unit()
        self.client.force_login(self.president)
        self.assertEqual(self.client.get(reverse('intelligence:desk')).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('intelligence:desk_cluster',
                                    args=[unit.pk])).status_code, 403)
        self.client.force_login(self.assistant)
        self.assertEqual(self.client.get(reverse('intelligence:desk')).status_code, 200)
        response = self.client.get(
            reverse('intelligence:desk_cluster', args=[unit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jega School Report 1')
        self.assertContains(response, 'Desk Source')

    def test_transition_post_gate(self):
        unit = self.make_unit(items=1)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('intelligence:desk_transition',
                    kwargs={'kind': 'item', 'pk': unit.pk}),
            {'action': 'TRIAGE'})
        self.assertEqual(response.status_code, 403)
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'DISCOVERED')
        self.client.force_login(self.assistant)
        self.client.post(
            reverse('intelligence:desk_transition',
                    kwargs={'kind': 'item', 'pk': unit.pk}),
            {'action': 'TRIAGE'})
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'UNDER_REVIEW')


class MergeSplitTests(DeskFixture):
    def test_merge_moves_members_and_retires_source(self):
        first = self.make_unit()
        second = self.make_unit()
        desk.merge_clusters(self.director, first, second,
                            note='Same event, two clusters.')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.publications.count(), 4)
        self.assertEqual(second.state, 'MERGED')
        self.assertEqual(second.merged_into, first)
        self.assertTrue(first.review_decisions.filter(action='MERGE').exists())
        self.assertTrue(second.review_decisions.filter(action='MERGE').exists())
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='CLUSTER_MERGED', target_id=first.pk).exists())

    def test_merge_rejects_self_and_retired(self):
        first = self.make_unit()
        second = self.make_unit()
        with self.assertRaises(desk.DeskError):
            desk.merge_clusters(self.director, first, first)
        desk.merge_clusters(self.director, first, second)
        with self.assertRaises(desk.DeskError):
            desk.merge_clusters(self.director, first, second)

    def test_split_two_items_forms_new_cluster(self):
        unit = self.make_unit(items=3)
        members = list(unit.publications.order_by('pk'))
        new_cluster = desk.split_cluster(
            self.director, unit, [members[1].pk, members[2].pk],
            note='Different school, different event.')
        self.assertIsNotNone(new_cluster)
        unit.refresh_from_db()
        self.assertEqual(unit.publications.count(), 1)
        self.assertEqual(new_cluster.publications.count(), 2)
        self.assertEqual(new_cluster.created_from, 'MANUAL')
        self.assertEqual(new_cluster.desk_state, 'DISCOVERED')
        self.assertTrue(unit.review_decisions.filter(action='SPLIT').exists())
        # Pairwise exclusions between the split groups, both directions.
        self.assertTrue(ClusterExclusion.objects.filter(
            publication=members[1], other_publication=members[0]).exists())
        self.assertTrue(ClusterExclusion.objects.filter(
            publication=members[0], other_publication=members[1]).exists())

    def test_split_single_item_unclusters_with_cluster_exclusion(self):
        unit = self.make_unit()
        members = list(unit.publications.order_by('pk'))
        result = desk.split_cluster(self.director, unit, [members[0].pk])
        self.assertIsNone(result)
        members[0].refresh_from_db()
        self.assertIsNone(members[0].cluster)
        self.assertTrue(ClusterExclusion.objects.filter(
            publication=members[0], cluster=unit).exists())

    def test_split_all_items_refused(self):
        unit = self.make_unit()
        members = list(unit.publications.values_list('pk', flat=True))
        with self.assertRaises(desk.DeskError):
            desk.split_cluster(self.director, unit, members)

    def test_merge_clears_split_exclusions(self):
        unit = self.make_unit(items=3)
        members = list(unit.publications.order_by('pk'))
        new_cluster = desk.split_cluster(
            self.director, unit, [members[1].pk, members[2].pk])
        self.assertTrue(ClusterExclusion.objects.exists())
        desk.merge_clusters(self.director, unit, new_cluster)
        self.assertFalse(ClusterExclusion.objects.filter(
            publication__in=[members[1], members[2]],
            other_publication=members[0]).exists())
        unit.refresh_from_db()
        self.assertEqual(unit.publications.count(), 3)

    def test_engine_never_undoes_a_split(self):
        other_source = make_source('Second Desk Source')
        now = timezone.now()
        first = make_item(
            self.source, 'Fire Outbreak Destroys Shops at Jega Market',
            text='A night fire has destroyed several shops at the Jega '
                 'main market, with traders counting losses estimated '
                 'in millions of naira as firefighters battled the '
                 'blaze for hours.',
            published_at=now - timedelta(hours=1))
        second = make_item(
            other_source, 'Fire Outbreak Guts Shops in Jega Market',
            text='Shop owners in Jega woke to the aftermath of an '
                 'inferno that gutted rows of stalls overnight, while '
                 'officials promised an investigation into the cause '
                 'of the fire.',
            published_at=now)
        relevance.process_pending()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.cluster)
        self.assertEqual(first.cluster, second.cluster)
        cluster = first.cluster
        # Staff decide the second report is a different incident.
        desk.split_cluster(self.director, cluster, [second.pk],
                           note='Different market section, later date.')
        second.refresh_from_db()
        self.assertIsNone(second.cluster)
        # Reprocessing must not pull it back in.
        relevance.process_publication(second)
        second.refresh_from_db()
        self.assertIsNone(second.cluster)
        self.assertEqual(EventCluster.objects.filter(state='OPEN').count(), 1)

    def test_pairwise_exclusion_blocks_repairing(self):
        first = make_item(
            self.source, 'Fire Outbreak Destroys Shops at Jega Market',
            text='A night fire has destroyed several shops at the Jega '
                 'main market, with traders counting losses.',
            published_at=timezone.now() - timedelta(hours=1))
        second = make_item(
            self.source, 'Fire Outbreak Guts Shops in Jega Market',
            text='Shop owners in Jega woke to the aftermath of an '
                 'inferno that gutted rows of stalls overnight.',
            published_at=timezone.now())
        ClusterExclusion.objects.create(
            publication=first, other_publication=second,
            created_by=self.director, reason='Staff separated these.')
        relevance.process_publication(first)
        relevance.process_publication(second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.cluster)
        self.assertIsNone(second.cluster)
        self.assertEqual(EventCluster.objects.count(), 0)


class ConversionTests(DeskFixture):
    def test_conversion_requires_approved_state(self):
        unit = self.make_unit()
        with self.assertRaises(desk.DeskError):
            desk.convert_to_draft(unit, self.director)
        self.assertFalse(Campaign.objects.exists())

    def test_conversion_creates_draft_with_evidence(self):
        unit = self.make_unit()
        walk(unit, self.director, 'APPROVED')
        article = desk.convert_to_draft(unit, self.director)
        self.assertEqual(article.status, 'DRAFT')
        self.assertIsNone(article.story_id)
        self.assertIsNone(article.published_at)
        self.assertEqual(article.category, 'EDUCATION')
        self.assertEqual(article.reporter_credit, 'KPN_EDITORIAL')
        self.assertEqual(article.source_name, 'Desk Source')
        self.assertTrue(article.source_url.startswith('https://example.com/'))
        evidence = EvidenceRecord.objects.filter(article=article)
        self.assertEqual(evidence.count(), 2)
        self.assertEqual({row.kind for row in evidence}, {'SOURCE_LINK'})
        unit.refresh_from_db()
        self.assertEqual(unit.article, article)
        # Conversion alone publishes nothing and marks nothing published.
        self.assertEqual(unit.desk_state, 'APPROVED')
        self.assertTrue(unit.review_decisions.filter(
            action='CONVERT').exists())
        with self.assertRaises(desk.DeskError):
            desk.convert_to_draft(unit, self.director)

    def test_unit_published_only_when_article_publishes(self):
        unit = self.make_unit()
        walk(unit, self.director, 'APPROVED')
        article = desk.convert_to_draft(unit, self.director)
        publish_campaign(article, self.director)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertTrue(article.story_id.startswith('KPN-SI-'))
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'PUBLISHED')
        decision = unit.review_decisions.get(action='PUBLISH')
        self.assertEqual(decision.from_state, 'APPROVED')
        self.assertEqual(decision.to_state, 'PUBLISHED')

    def test_conversion_http_needs_confirmation(self):
        unit = self.make_unit()
        walk(unit, self.director, 'APPROVED')
        url = reverse('intelligence:desk_convert',
                      kwargs={'kind': 'cluster', 'pk': unit.pk})
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(url).status_code, 200)
        # A POST without the confirmation value creates nothing.
        self.client.post(url, {})
        self.assertFalse(Campaign.objects.exists())
        unit.refresh_from_db()
        self.assertIsNone(unit.article)
        # With confirmation, exactly one DRAFT appears.
        response = self.client.post(url, {'confirm': 'yes'})
        self.assertEqual(Campaign.objects.count(), 1)
        article = Campaign.objects.get()
        self.assertEqual(article.status, 'DRAFT')
        self.assertEqual(response.status_code, 302)

    def test_conversion_http_capability_gate(self):
        unit = self.make_unit()
        walk(unit, self.director, 'APPROVED')
        url = reverse('intelligence:desk_convert',
                      kwargs={'kind': 'cluster', 'pk': unit.pk})
        self.client.force_login(self.president)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.post(url, {'confirm': 'yes'}).status_code, 403)
        self.assertFalse(Campaign.objects.exists())


@override_settings(KPN_EDITORIAL_ENABLED=True,
                   KPN_EDITORIAL_BRAIN_TOKEN=TOKEN,
                   KPN_EDITORIAL_AUTO_PUBLISH=True)
class LaneOneIsolationTests(DeskFixture):
    def test_brain_publish_does_not_touch_intelligence_units(self):
        unit = self.make_unit()
        walk(unit, self.director, 'APPROVED')
        item = Item.objects.create(
            key='lane1-news', kind='NEWS', title='Kebbi market reopens',
            state='REVIEW', source_url='https://example.com/kebbi-market',
            original={'title': 'Kebbi market reopens',
                      'text': 'A market in Kebbi reopened.',
                      'source_url': 'https://example.com/kebbi-market'},
            draft={'title': 'Kebbi market reopens',
                   'body': 'A market in Kebbi reopened.',
                   'category': 'MARKETS'})
        response = self.client.post(
            reverse('editorial:brain_publish_item'),
            data=json.dumps({'item_id': item.pk}),
            content_type='application/json', **AUTH)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['published'])
        article = Campaign.objects.get(slug=response.json()['slug'])
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertFalse(article.intelligence_clusters.exists())
        self.assertFalse(article.intelligence_publications.exists())
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'APPROVED')
        self.assertIsNone(unit.article)
        self.assertFalse(unit.review_decisions.filter(
            action='PUBLISH').exists())


class DeskQueueAndCredibilityTests(DeskFixture):
    def test_queue_filters_by_state(self):
        waiting = self.make_unit()
        done = self.make_unit()
        walk(done, self.director, 'REJECTED')
        self.client.force_login(self.assistant)
        response = self.client.get(reverse('intelligence:desk'))
        self.assertContains(response, waiting.title)
        response = self.client.get(
            reverse('intelligence:desk'), {'state': 'REJECTED'})
        self.assertContains(response, done.title)
        self.assertNotContains(response, waiting.title)

    def test_source_credibility_counts(self):
        verified = self.make_unit()
        walk(verified, self.director, 'VERIFIED')
        rejected = self.make_unit(items=1)
        walk(rejected, self.director, 'REJECTED')
        record = desk.source_credibility(self.source)
        self.assertEqual(record['items_collected'], 3)
        self.assertEqual(record['units_verified'], 1)
        self.assertEqual(record['units_rejected'], 1)

    def test_detail_page_shows_evidence_and_record(self):
        unit = self.make_unit()
        self.client.force_login(self.assistant)
        response = self.client.get(
            reverse('intelligence:desk_item', args=[999999]))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            reverse('intelligence:desk_cluster', args=[unit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Evidence')
        self.assertContains(response, 'Source record')
        self.assertContains(response, 'Items collected from this source: 2')
