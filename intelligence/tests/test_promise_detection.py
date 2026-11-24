"""Phase 5: promise-candidate detection — quote fidelity, no invented
institutions or dates, human-gated confirmation, dismissal with a
reason, and idempotent reprocessing.

Everything runs on local fixtures — no network.
"""
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from editorial.tests.helpers import (
    assistant_media, general_member, media_director,
)
from intelligence import promise_detection, relevance
from intelligence.models import (
    EventCluster, IntelligenceCategory, PublicationLocation,
    PromiseCandidate,
)
from leadership.models import LGA
from story_intelligence.models import Institution, Promise

from .helpers import seed_directory
from .test_processing import make_item, make_source

COMMITMENT_TEXT = (
    'The Kebbi State Government has announced a new rural roads '
    'programme for Jega. The government will construct 12 kilometres '
    'of township roads in Jega, to be completed by December 2027. '
    'Officials said the work would begin immediately.'
)
PLAIN_TEXT = (
    'The governor visited Jega on Monday and inspected the ongoing '
    'road repairs. He was accompanied by the commissioner for works '
    'and other senior officials.'
)


class DetectionFixture(TestCase):
    def setUp(self):
        seed_directory()
        self.source = make_source()
        self.jega = LGA.objects.get(name='Jega')
        self.director = media_director('pd_director')
        self.assistant = assistant_media('pd_assistant')
        self.member = general_member('pd_member')
        self.institution = Institution.objects.create(
            name='Kebbi State Government', kind='OTHER')


class DetectorTests(DetectionFixture):
    def test_fires_on_commitment_language_with_exact_quote(self):
        item = make_item(self.source, 'Roads programme announced',
                         text=COMMITMENT_TEXT)
        candidates = promise_detection.detect_for_publication(item)
        quotes = [c.quote for c in candidates]
        self.assertTrue(any(
            'will construct 12 kilometres' in q for q in quotes))
        # The stored quote is a verbatim span of the source text.
        for candidate in candidates:
            self.assertIn(candidate.quote, COMMITMENT_TEXT)

    def test_does_not_fire_on_plain_reporting(self):
        item = make_item(self.source, 'Governor inspects repairs',
                         text=PLAIN_TEXT)
        self.assertEqual(promise_detection.detect_for_publication(item), [])
        self.assertEqual(PromiseCandidate.objects.count(), 0)

    def test_deadline_is_the_verbatim_phrase_never_a_date(self):
        item = make_item(self.source, 'Roads programme announced',
                         text=COMMITMENT_TEXT)
        candidates = promise_detection.detect_for_publication(item)
        phrases = {c.deadline_text for c in candidates if c.deadline_text}
        self.assertTrue(any('December 2027' in p for p in phrases))
        for candidate in candidates:
            self.assertIsInstance(candidate.deadline_text, str)

    def test_institution_recorded_only_when_named_in_text(self):
        item = make_item(self.source, 'Roads programme announced',
                         text=COMMITMENT_TEXT)
        candidates = promise_detection.detect_for_publication(item)
        named = [c for c in candidates if 'will construct' in c.quote]
        self.assertEqual(named[0].institution_name, 'Kebbi State Government')
        # A text naming no known institution records none.
        other = make_item(
            self.source, 'Council pledges support',
            text='The council chairman pledged to provide boreholes '
                 'for the riverside communities next year.')
        others = promise_detection.detect_for_publication(other)
        self.assertTrue(others)
        self.assertEqual(others[0].institution_name, '')

    def test_location_comes_from_matched_locations(self):
        item = make_item(self.source, 'Roads programme announced',
                         text=COMMITMENT_TEXT)
        PublicationLocation.objects.create(
            publication=item, match_kind='EXPLICIT', lga=self.jega,
            matched_text='Jega', confidence=1.0)
        candidates = promise_detection.detect_for_publication(item)
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].lga, self.jega)

    def test_reprocessing_never_duplicates_candidates(self):
        item = make_item(self.source, 'Roads programme announced',
                         text=COMMITMENT_TEXT)
        first = promise_detection.detect_for_publication(item)
        second = promise_detection.detect_for_publication(item)
        self.assertEqual(len(first), len(second))
        self.assertEqual(
            PromiseCandidate.objects.filter(publication=item).count(),
            len(first))

    def test_detector_runs_inside_the_processing_step(self):
        item = make_item(
            self.source, 'Government will construct roads in Jega',
            text=COMMITMENT_TEXT)
        stats = relevance.process_pending()
        item.refresh_from_db()
        self.assertIsNotNone(item.relevance)
        self.assertGreaterEqual(stats['promise_candidates'], 1)
        self.assertTrue(
            PromiseCandidate.objects.filter(publication=item).exists())
        # A second full processing run adds nothing.
        relevance.process_pending()
        count = PromiseCandidate.objects.filter(publication=item).count()
        relevance.process_pending()
        self.assertEqual(
            PromiseCandidate.objects.filter(publication=item).count(), count)


class CandidateDecisionTests(DetectionFixture):
    def setUp(self):
        super().setUp()
        self.item = make_item(self.source, 'Roads programme announced',
                              text=COMMITMENT_TEXT)
        self.candidates = promise_detection.detect_for_publication(self.item)
        self.candidate = next(
            c for c in self.candidates if 'will construct' in c.quote)

    def test_nothing_is_public_before_confirmation(self):
        self.assertEqual(Promise.objects.count(), 0)
        response = self.client.get(reverse('promises:list'))
        self.assertNotContains(response, 'township roads')

    def test_confirm_creates_a_real_promise_with_source_link(self):
        promise = promise_detection.confirm_candidate(
            self.candidate, self.director,
            institution=self.institution,
            title='Construct 12km of township roads in Jega',
            announced_on=self.item.published_at.date()
            if self.item.published_at else None)
        self.assertEqual(promise.status, 'ANNOUNCED')
        self.assertEqual(promise.institution, self.institution)
        self.assertEqual(promise.source_url, self.item.original_url)
        self.assertEqual(promise.source_name, self.source.name)
        self.assertIsNone(promise.deadline)  # phrase never auto-parsed
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, 'CONFIRMED')
        self.assertEqual(self.candidate.promise, promise)
        # Public provenance marker is wired.
        response = self.client.get(
            reverse('promises:detail', args=[promise.pk]))
        self.assertContains(response, 'Detected via KPN monitoring')

    def test_confirm_requires_manage_promises(self):
        with self.assertRaises(PermissionDenied):
            promise_detection.confirm_candidate(
                self.candidate, self.member, institution=self.institution)
        self.assertEqual(Promise.objects.count(), 0)

    def test_confirm_twice_is_refused(self):
        promise_detection.confirm_candidate(
            self.candidate, self.director, institution=self.institution)
        with self.assertRaises(promise_detection.CandidateError):
            promise_detection.confirm_candidate(
                self.candidate, self.director, institution=self.institution)
        self.assertEqual(Promise.objects.count(), 1)

    def test_dismiss_requires_and_records_a_reason(self):
        with self.assertRaises(promise_detection.CandidateError):
            promise_detection.dismiss_candidate(
                self.candidate, self.director, reason='')
        promise_detection.dismiss_candidate(
            self.candidate, self.director,
            reason='Aspirational remark, no commitment made.')
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, 'DISMISSED')
        self.assertEqual(self.candidate.decision_note,
                         'Aspirational remark, no commitment made.')
        self.assertEqual(Promise.objects.count(), 0)
        # Reprocessing never resurrects a dismissed candidate.
        promise_detection.detect_for_publication(self.item)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, 'DISMISSED')

    def test_queue_views_are_gated_and_functional(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('intelligence:promise_candidates'))
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.assistant)
        response = self.client.get(reverse('intelligence:promise_candidates'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'will construct 12 kilometres')
        # Dismiss through the view.
        response = self.client.post(
            reverse('intelligence:promise_candidate_dismiss',
                    args=[self.candidate.pk]),
            {'reason': 'Not a commitment.'})
        self.assertEqual(response.status_code, 302)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, 'DISMISSED')

    def test_confirm_through_the_view(self):
        self.client.force_login(self.assistant)
        response = self.client.post(
            reverse('intelligence:promise_candidate_confirm',
                    args=[self.candidate.pk]), {
                'institution': self.institution.pk,
                'institution_name': '',
                'title': 'Construct 12km of township roads in Jega',
                'description': self.candidate.quote,
                'announced_by': 'Kebbi State Government',
                'announced_on': '2026-11-23',
                'deadline': '',
                'sector': 'INFRASTRUCTURE',
            })
        self.assertEqual(response.status_code, 302)
        promise = Promise.objects.get()
        self.assertEqual(promise.title,
                         'Construct 12km of township roads in Jega')
        self.assertEqual(promise.source_url, self.item.original_url)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, 'CONFIRMED')
