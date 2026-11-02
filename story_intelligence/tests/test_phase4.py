"""Phase 4 (v2.8.0) — Future Signal + Human Impact Files.

Pins the two editorial formats built on the Phase 1 spine:
- Future Signal: kind=SIGNAL framing via the story desk, evidence
  linking (a signal with no evidence is flagged on the desk), the
  public /signals/ list, and the analysis framing on the article page.
- Human Impact Files: kind=IMPACT plus the consent guard — a story
  flagged as featuring identifiable people cannot publish on ANY
  publish path until a consent record is on file; anonymised files
  publish normally; consent internals never appear publicly.
"""
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from campaigns.services import publish_campaign, archive_campaign, restore_campaign
from editorial import publish as brain_publish
from editorial import services as editorial_services
from editorial.brain import BrainError
from editorial.models import Item
from editorial.tests.helpers import general_member, media_director
from story_intelligence.models import (
    Claim, ConsentRecord, Correction, StoryProfile,
)
from story_intelligence.services import (
    ConsentRequiredError, REDACTION_MARKER, perform_redaction,
)

DESCRIPTOR = 'INTERNAL-DESCRIPTOR-7f3a'
CONSENT_NOTES = 'INTERNAL-CONSENT-NOTES-9b1c'


def make_article(author, title, status='PENDING', **kwargs):
    kwargs.setdefault('content', 'Article body text.')
    return Campaign.objects.create(
        author=author, title=title,
        slug=title.lower().replace(' ', '-').replace(',', ''),
        status=status, **kwargs)


def make_profile(article, kind, **kwargs):
    return StoryProfile.objects.create(article=article, kind=kind, **kwargs)


def publish_via_service(article, actor):
    return publish_campaign(article, actor)


# ─── Future Signal: story desk ────────────────────────────────────────────────

class SignalDeskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('sig_editor')
        cls.member = general_member('sig_member')

    def setUp(self):
        self.article = make_article(self.editor, 'Rain Pattern Signal')
        self.client.force_login(self.editor)

    def _profile_post(self, **extra):
        data = {
            'kind': 'SIGNAL',
            'why_it_matters': 'Planting decisions depend on it.',
            'who_is_affected': 'Farmers across Kebbi.',
            'what_is_unknown': 'When the rains will settle.',
            'what_to_watch': 'Weekly rainfall reports.',
            'signal_observation': 'Early rains arrived, then stopped for two weeks.',
            'signal_confidence': 'DEVELOPING',
            'signal_horizon': 'This farming season',
            'signal_change_condition': 'Three consecutive weeks of steady rain.',
            'related_stories': [],
            'impact_story': '',
        }
        data.update(extra)
        return self.client.post(
            reverse('story_intelligence:save_profile', args=[self.article.pk]),
            data)

    def test_editor_can_designate_signal_and_save_framing(self):
        response = self._profile_post()
        self.assertEqual(response.status_code, 302)
        profile = StoryProfile.objects.get(article=self.article)
        self.assertEqual(profile.kind, 'SIGNAL')
        self.assertEqual(profile.signal_observation,
                         'Early rains arrived, then stopped for two weeks.')
        self.assertEqual(profile.signal_confidence, 'DEVELOPING')
        self.assertEqual(profile.signal_horizon, 'This farming season')
        self.assertEqual(profile.signal_change_condition,
                         'Three consecutive weeks of steady rain.')

    def test_non_editor_cannot_save_profile(self):
        self.client.force_login(self.member)
        response = self._profile_post()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StoryProfile.objects.filter(article=self.article).exists())

    def test_signal_without_evidence_is_flagged_on_desk(self):
        self._profile_post()
        response = self.client.get(
            reverse('story_intelligence:desk', args=[self.article.pk]))
        self.assertContains(response, 'no evidence linked yet')

    def test_signal_with_claim_is_not_flagged(self):
        self._profile_post()
        Claim.objects.create(
            article=self.article, text='Rainfall stopped for two weeks.',
            status='DEVELOPING', noted_by=self.editor)
        response = self.client.get(
            reverse('story_intelligence:desk', args=[self.article.pk]))
        self.assertNotContains(response, 'no evidence linked yet')

    def test_signal_with_related_story_is_not_flagged(self):
        base = make_article(self.editor, 'Early Rains Arrive', status='PUBLISHED',
                            published_at=timezone.now())
        self._profile_post(related_stories=[base.pk])
        profile = StoryProfile.objects.get(article=self.article)
        self.assertEqual(list(profile.related_stories.all()), [base])
        response = self.client.get(
            reverse('story_intelligence:desk', args=[self.article.pk]))
        self.assertNotContains(response, 'no evidence linked yet')


# ─── Future Signal: public surfaces ───────────────────────────────────────────

class SignalPublicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('sig_pub_editor')

    def setUp(self):
        self.base = make_article(self.editor, 'Early Rains Arrive In Kebbi')
        publish_via_service(self.base, self.editor)
        self.signal = make_article(self.editor, 'A Farming Season At Risk')
        profile = make_profile(
            self.signal, 'SIGNAL',
            why_it_matters='Planting decisions depend on it.',
            what_to_watch='Weekly rainfall reports.',
            signal_observation='Early rains arrived, then stopped.',
            signal_confidence='DEVELOPING',
            signal_horizon='This farming season',
            signal_change_condition='Three weeks of steady rain.')
        profile.related_stories.add(self.base)
        publish_via_service(self.signal, self.editor)
        # A draft signal and a published news story: neither may appear.
        self.draft_signal = make_article(self.editor, 'Unpublished Signal Draft',
                                         status='DRAFT')
        make_profile(self.draft_signal, 'SIGNAL',
                     signal_observation='Not yet published.')

    def test_signals_page_lists_only_published_signals(self):
        response = self.client.get(reverse('signals:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A Farming Season At Risk')
        self.assertNotContains(response, 'Unpublished Signal Draft')
        self.assertNotContains(response, 'Early Rains Arrive In Kebbi</a>')
        self.assertContains(response, reverse('campaigns:article_detail',
                                              args=[self.signal.slug]))

    def test_signals_page_uses_field_labels_without_explainer_copy(self):
        response = self.client.get(reverse('signals:list'))
        # The field labels over the editor-entered content stay.
        self.assertContains(response, 'What we are seeing')
        self.assertContains(response, 'Why it matters')
        self.assertContains(response, 'What to watch')
        # v2.9.2: the intro paragraph explaining the feature was
        # removed on the owner's instruction — the page opens
        # straight into its heading and content.
        self.assertNotContains(response, 'not predictions')
        self.assertNotContains(response, 'reports of established fact')
        self.assertNotContains(response, 'judge for yourself')
        self.assertNotContains(response, 'what our editors are seeing')

    def test_article_page_renders_signal_framing(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.signal.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Future Signal — KPN analysis')
        # v2.9.2: the disclaimer sentence that used to sit under the
        # panel heading was removed on the owner's instruction; the
        # "KPN analysis" label itself stays.
        self.assertNotContains(response, 'not a prediction')
        self.assertNotContains(response, 'not a report of established fact')
        self.assertContains(response, 'Early rains arrived, then stopped.')
        self.assertContains(response, 'Developing — the evidence is growing')
        self.assertContains(response, 'Three weeks of steady rain.')
        self.assertContains(response, 'Early Rains Arrive In Kebbi')


# ─── Human Impact: the consent guard ──────────────────────────────────────────

class ConsentGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('impact_editor')

    def _impact_article(self, title='Widows Of Argungu Market', flag=True):
        article = make_article(self.editor, title)
        make_profile(article, 'IMPACT',
                     who_is_affected='Market women in Argungu.',
                     features_identifiable_people=flag)
        return article

    def _add_consent(self, article, basis='WRITTEN', withdrawn=False):
        return ConsentRecord.objects.create(
            article=article, subject_descriptor=DESCRIPTOR,
            consent_basis=basis, recorded_by=self.editor,
            notes=CONSENT_NOTES, withdrawn=withdrawn)

    def test_identifiable_impact_without_consent_blocked_on_web(self):
        article = self._impact_article()
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('campaigns:publish_article', args=[article.pk]), follow=True)
        self.assertContains(response, 'no consent record is on file')
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')
        self.assertIsNone(article.story_id)

    def test_identifiable_impact_without_consent_blocked_on_api(self):
        article = self._impact_article('Api Blocked Impact')
        client = APIClient()
        client.force_authenticate(self.editor)
        response = client.post(
            f'/api/v1/articles/{article.pk}/decision/', {'action': 'publish'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('consent', str(response.data).lower())
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')
        self.assertIsNone(article.story_id)

    def test_identifiable_impact_without_consent_blocked_in_service(self):
        article = self._impact_article('Service Blocked Impact')
        with self.assertRaises(ConsentRequiredError):
            publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')

    def test_identifiable_impact_with_consent_publishes(self):
        article = self._impact_article('Consented Impact Story')
        self._add_consent(article)
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('campaigns:publish_article', args=[article.pk]))
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertTrue(article.story_id.startswith('KPN-SI-'))

    def test_not_required_basis_counts_as_recorded(self):
        article = self._impact_article('Public Official Impact')
        self._add_consent(article, basis='NOT_REQUIRED')
        publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')

    def test_withdrawn_consent_does_not_count(self):
        article = self._impact_article('Withdrawn Consent Impact')
        self._add_consent(article, withdrawn=True)
        with self.assertRaises(ConsentRequiredError):
            publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')

    def test_anonymised_impact_publishes_without_consent(self):
        article = self._impact_article('Anonymised Impact Story', flag=False)
        publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertTrue(article.story_id.startswith('KPN-SI-'))

    def test_news_story_with_flag_set_is_not_blocked(self):
        # The guard is scoped to kind == IMPACT only.
        article = make_article(self.editor, 'Ordinary News Story')
        make_profile(article, 'NEWS', features_identifiable_people=True)
        publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')

    def test_story_without_profile_is_not_blocked(self):
        article = make_article(self.editor, 'Profileless News Story')
        publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')

    def test_restore_blocked_when_consent_withdrawn(self):
        article = self._impact_article('Restorable Impact Story')
        consent = self._add_consent(article)
        publish_campaign(article, self.editor)
        archive_campaign(article, actor=self.editor)
        consent.withdrawn = True
        consent.save(update_fields=['withdrawn'])
        with self.assertRaises(ConsentRequiredError):
            restore_campaign(article, actor=self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'ARCHIVED')

    def test_brain_publish_path_runs_the_guard(self):
        # Brain items create brand-new articles (no profile), so the
        # guard passes in production; this pins the WIRING: if the
        # guard ever raises on the brain path, the publish must roll
        # back with the stable 'consent_required' code and the item
        # must stay in REVIEW, untouched.
        item = Item.objects.create(
            key='phase4-brain-guard', kind='NEWS', title='Brain Guard Story',
            state='REVIEW', source_url='https://example.com/story',
            original={'title': 'Brain Guard Story', 'text': 'Evidence.',
                      'source_url': 'https://example.com/story'},
            draft={'title': 'Brain Guard Story', 'body': 'Body text.',
                   'category': 'GENERAL'})
        with mock.patch(
                'story_intelligence.services.ensure_consent_for_publish',
                side_effect=ConsentRequiredError('blocked')):
            with self.assertRaises(BrainError) as ctx:
                brain_publish.publish_brain_item(item)
        self.assertEqual(str(ctx.exception), 'consent_required')
        item.refresh_from_db()
        self.assertEqual(item.state, 'REVIEW')
        self.assertFalse(Campaign.objects.filter(
            title='Brain Guard Story').exists())

    @override_settings(KPN_EDITORIAL_AUTO_PUBLISH=True)
    def test_handoff_path_runs_the_guard(self):
        item = Item.objects.create(
            key='phase4-handoff-guard', kind='NEWS', title='Handoff Guard Story',
            state='REVIEW', source_url='https://example.com/story',
            original={'title': 'Handoff Guard Story', 'text': 'Evidence.',
                      'source_url': 'https://example.com/story'},
            draft={'title': 'Handoff Guard Story', 'body': 'Body text.',
                   'category': 'GENERAL'})
        with mock.patch(
                'story_intelligence.services.ensure_consent_for_publish',
                side_effect=ConsentRequiredError('blocked by consent guard')):
            with self.assertRaises(ValidationError) as ctx:
                editorial_services.act(
                    self.editor, item.pk, 'handoff', item.version,
                    confirmed=True)
        self.assertIn('blocked by consent guard', str(ctx.exception))
        item.refresh_from_db()
        self.assertEqual(item.state, 'REVIEW')
        self.assertFalse(Campaign.objects.filter(
            title='Handoff Guard Story').exists())


# ─── Human Impact: public surfaces and privacy ────────────────────────────────

class ImpactPublicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('impact_pub_editor')

    def setUp(self):
        self.story = make_article(self.editor, 'The Women Who Rebuilt The Market')
        make_profile(self.story, 'IMPACT',
                     who_is_affected='Market women in Argungu.',
                     why_it_matters='The fire destroyed 40 stalls.',
                     what_to_watch='Whether the stalls are rebuilt.',
                     features_identifiable_people=True)
        ConsentRecord.objects.create(
            article=self.story, subject_descriptor=DESCRIPTOR,
            consent_basis='WRITTEN', recorded_by=self.editor,
            notes=CONSENT_NOTES)
        publish_via_service(self.story, self.editor)
        self.draft = make_article(self.editor, 'Unpublished Impact Draft',
                                  status='DRAFT')
        make_profile(self.draft, 'IMPACT', who_is_affected='Nobody yet.')

    def test_impact_page_lists_published_impact_stories(self):
        response = self.client.get(reverse('impact_files:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The Women Who Rebuilt The Market')
        self.assertContains(response, 'Market women in Argungu.')
        self.assertNotContains(response, 'Unpublished Impact Draft')
        self.assertContains(response, reverse('campaigns:article_detail',
                                              args=[self.story.slug]))

    def test_impact_page_never_exposes_consent_internals(self):
        response = self.client.get(reverse('impact_files:list'))
        self.assertNotContains(response, DESCRIPTOR)
        self.assertNotContains(response, CONSENT_NOTES)

    def test_article_page_renders_impact_framing_without_consent_data(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.story.slug]))
        self.assertEqual(response.status_code, 200)
        # The panel keeps its kind badge and the impact framing labels
        # over the editor-entered content.
        self.assertContains(response, 'Human Impact')
        self.assertContains(response, 'Who is affected')
        self.assertContains(response, 'Their situation')
        # v2.9.2: the explainer sentence that used to open the impact
        # panel was removed on the owner's instruction.
        self.assertNotContains(response, 'people behind this issue')
        self.assertNotContains(response, 'shared with consent')
        self.assertContains(response, 'Market women in Argungu.')
        self.assertNotContains(response, DESCRIPTOR)
        self.assertNotContains(response, CONSENT_NOTES)

    def test_api_never_exposes_consent_internals(self):
        response = self.client.get(f'/api/v1/newsroom/{self.story.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(DESCRIPTOR, str(response.data))
        self.assertNotIn(CONSENT_NOTES, str(response.data))
        self.assertNotIn('consent', {key.lower() for key in response.data.keys()})

    def test_core_impact_page_still_works(self):
        # /impact/ remains core's organisational impact page, untouched.
        response = self.client.get(reverse('core:impact'))
        self.assertEqual(response.status_code, 200)


# ─── Phase 4 interplay: redaction, archive, navigation ────────────────────────

class Phase4InterplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('phase4_editor')

    def test_redaction_works_on_impact_story(self):
        article = make_article(
            self.editor, 'Impact Redaction Story', status='PUBLISHED',
            content='Body naming a private person.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00404')
        make_profile(article, 'IMPACT', features_identifiable_people=True)
        ConsentRecord.objects.create(
            article=article, subject_descriptor=DESCRIPTOR,
            consent_basis='WRITTEN', recorded_by=self.editor)
        result = perform_redaction(
            actor=self.editor, target_type='article', target_id=article.pk,
            reason_category='CONSENT_WITHDRAWN')
        article.refresh_from_db()
        self.assertEqual(article.content, REDACTION_MARKER)
        correction = Correction.objects.get(pk=result['correction_id'])
        self.assertEqual(correction.kind, 'REDACTION')
        self.assertNotIn(DESCRIPTOR, correction.text)

    def test_archive_finds_signal_and_impact_stories(self):
        signal = make_article(self.editor, 'Zuru Harvest Outlook')
        make_profile(signal, 'SIGNAL',
                     signal_observation='Granaries are filling early.')
        publish_via_service(signal, self.editor)
        impact = make_article(self.editor, 'Zuru Flood Families')
        make_profile(impact, 'IMPACT', who_is_affected='Families in Zuru.')
        publish_via_service(impact, self.editor)
        for term, title in (('Harvest', 'Zuru Harvest Outlook'),
                            ('Flood', 'Zuru Flood Families')):
            response = self.client.get(reverse('archive:home'), {'q': term})
            self.assertEqual(response.status_code, 200)
            self.assertGreaterEqual(response.context['stories_total'], 1)
            self.assertContains(response, title)

    def test_nav_links_present(self):
        response = self.client.get(reverse('signals:list'))
        self.assertContains(response, 'Future Signal')
        self.assertContains(response, '/signals/')
        self.assertContains(response, 'Human Impact')
        self.assertContains(response, '/impact/stories/')
