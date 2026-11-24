"""Page-by-Page Upgrade Priority 3 — Human Impact Files + Future Signal.

Pins:
- the additive StoryProfile fields (impact_category, signal_category,
  who_contributed) and the D-10 effective-theme rule (explicit label
  wins, presentation mapping from the news category otherwise);
- the rebuilt /impact/stories/ hub: featured file, theme browsing,
  honest empty states, the brief §C consent wording, real heroes;
- the impact article page's six-part documentary structure and its
  related-files rail;
- the consent guard, re-proven AFTER the presentation rebuild: an
  identifiable-people impact story still cannot publish without a
  consent record on file;
- the rebuilt /signals/ hub: theme + evidence-strength filters and
  the brief §F methodology wording (in the brief's own phrasing);
- the signal article page's six questions with the epistemic groups
  kept visibly separate — confirmed facts never share a group with
  official statements — and confidence rendered as evidence strength,
  never as probability.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from campaigns.services import publish_campaign
from editorial.tests.helpers import media_director
from intelligence.models import ArticleLocation
from leadership.models import LGA, Zone
from story_intelligence.models import (
    Claim, ConsentRecord, StoryProfile, StoryUpdate,
)
from story_intelligence.services import ConsentRequiredError


def make_article(author, title, status='PUBLISHED', **kwargs):
    kwargs.setdefault('content', 'Article body text.')
    kwargs.setdefault('published_at', timezone.now())
    return Campaign.objects.create(
        author=author, title=title,
        slug=title.lower().replace(' ', '-').replace(',', ''),
        status=status, **kwargs)


def make_profile(article, kind, **kwargs):
    return StoryProfile.objects.create(article=article, kind=kind, **kwargs)


# ─── Fields and the effective-theme rule ─────────────────────────────────────

class Priority3FieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p3_fields_editor')

    def test_new_fields_default_blank(self):
        article = make_article(self.editor, 'Plain Impact Story')
        profile = make_profile(article, 'IMPACT')
        self.assertEqual(profile.impact_category, '')
        self.assertEqual(profile.signal_category, '')
        self.assertEqual(profile.who_contributed, '')

    def test_effective_category_explicit_label_wins(self):
        article = make_article(self.editor, 'Mapped Story',
                               category='EDUCATION')
        profile = make_profile(article, 'IMPACT', impact_category='UNSUNG')
        self.assertEqual(profile.effective_impact_category, 'UNSUNG')
        self.assertEqual(profile.impact_category_label,
                         'Unsung Community Contributors')

    def test_effective_category_falls_back_to_news_mapping(self):
        article = make_article(self.editor, 'School Story',
                               category='EDUCATION')
        profile = make_profile(article, 'IMPACT')
        self.assertEqual(profile.effective_impact_category,
                         'EDUCATION_OPPORTUNITY')

    def test_effective_category_unmapped_news_category_is_blank(self):
        article = make_article(self.editor, 'Governance Story',
                               category='GOVERNANCE')
        profile = make_profile(article, 'IMPACT')
        self.assertEqual(profile.effective_impact_category, '')
        self.assertEqual(profile.impact_category_label, '')

    def test_desk_form_carries_the_new_fields(self):
        from story_intelligence.forms import StoryProfileForm
        form = StoryProfileForm()
        for field in ('impact_category', 'signal_category', 'who_contributed'):
            self.assertIn(field, form.fields)


# ─── Human Impact hub ────────────────────────────────────────────────────────

class ImpactHubPriority3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p3_impact_editor')

    def setUp(self):
        now = timezone.now()
        self.older = make_article(
            self.editor, 'The School Feeding Mothers',
            category='EDUCATION', published_at=now - timedelta(days=3))
        make_profile(self.older, 'IMPACT',
                     who_is_affected='Mothers running school kitchens.')
        self.newer = make_article(
            self.editor, 'The Trader Who Rebuilt Her Stall',
            category='GENERAL', published_at=now - timedelta(days=1))
        make_profile(self.newer, 'IMPACT', impact_category='UNSUNG',
                     who_is_affected='A market trader in Birnin Kebbi.')
        StoryUpdate.objects.create(
            article=self.older, title='Kitchen Reopens', body='It reopened.',
            status='PUBLISHED', published_at=now, author=self.editor)
        self.draft = make_article(self.editor, 'Unpublished Impact File',
                                  status='DRAFT')
        make_profile(self.draft, 'IMPACT', who_is_affected='Nobody yet.')

    def test_hub_lists_published_only_with_real_hero_no_credit(self):
        response = self.client.get(reverse('impact_files:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The Trader Who Rebuilt Her Stall')
        self.assertContains(response, 'The School Feeding Mothers')
        self.assertNotContains(response, 'Unpublished Impact File')
        self.assertContains(response, 'img/impact-hero')
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotContains(
            response,
            'Rice farmers at harvest, Kebbi State — Photo: AgroBroadcast')
        self.assertNotContains(response, 'kpn-hero-credit')

    def test_featured_file_is_the_latest_story(self):
        response = self.client.get(reverse('impact_files:list'))
        content = response.content.decode()
        featured_at = content.find('Featured story')
        self.assertGreater(featured_at, -1)
        self.assertGreater(content.find('The Trader Who Rebuilt Her Stall'),
                           featured_at)

    def test_category_filter_uses_the_news_category_mapping(self):
        response = self.client.get(
            reverse('impact_files:list'),
            {'category': 'EDUCATION_OPPORTUNITY'})
        self.assertContains(response, 'The School Feeding Mothers')
        self.assertNotContains(response, 'The Trader Who Rebuilt Her Stall')

    def test_category_filter_uses_the_explicit_impact_label(self):
        response = self.client.get(
            reverse('impact_files:list'), {'category': 'UNSUNG'})
        self.assertContains(response, 'The Trader Who Rebuilt Her Stall')
        self.assertNotContains(response, 'The School Feeding Mothers')

    def test_empty_category_shows_an_honest_empty_state(self):
        response = self.client.get(
            reverse('impact_files:list'), {'category': 'HEALTH_WELFARE'})
        self.assertContains(
            response, 'No stories filed under Health and Welfare yet')
        self.assertNotContains(response, 'The School Feeding Mothers')

    def test_unknown_category_falls_back_to_all_stories(self):
        response = self.client.get(
            reverse('impact_files:list'), {'category': 'NOT_A_THEME'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The School Feeding Mothers')

    def test_followed_story_shows_its_update_count(self):
        response = self.client.get(reverse('impact_files:list'))
        self.assertContains(response, '1 update over time')

    def test_ethics_note_uses_the_briefs_consent_wording(self):
        response = self.client.get(reverse('impact_files:list'))
        self.assertContains(
            response,
            'Consent procedures and appropriate safeguards are essential.')
        self.assertContains(
            response,
            'do not publish sensitive personal information without proper '
            'justification and safeguards.')


# ─── Human Impact article page: six parts + the consent guard ────────────────

class ImpactDetailPriority3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p3_impact_detail_editor')

    def setUp(self):
        self.story = make_article(
            self.editor, 'The Women Who Rebuilt The Market',
            category='COMMUNITY')
        make_profile(
            self.story, 'IMPACT',
            who_is_affected='Market women in Argungu.',
            why_it_matters='The fire destroyed 40 stalls.',
            who_contributed='The traders association rebuilt the stalls '
                            'with support from the LGA council.',
            what_is_unknown='Compensation has not been confirmed.',
            what_to_watch='Whether the stalls are rebuilt.',
            features_identifiable_people=True)
        ConsentRecord.objects.create(
            article=self.story, subject_descriptor='INTERNAL-DESC-P3',
            consent_basis='WRITTEN', recorded_by=self.editor,
            notes='INTERNAL-NOTES-P3')
        Claim.objects.create(
            article=self.story, text='Forty stalls were destroyed.',
            status='CONFIRMED', noted_by=self.editor)
        StoryUpdate.objects.create(
            article=self.story, title='Stalls Reopen', body='Trading resumed.',
            status='PUBLISHED', published_at=timezone.now(),
            author=self.editor)
        self.other = make_article(
            self.editor, 'A Borehole For Maiyama', category='COMMUNITY')
        make_profile(self.other, 'IMPACT',
                     who_is_affected='Households in Maiyama.')
        self.draft_other = make_article(
            self.editor, 'Draft Impact File', status='DRAFT',
            category='COMMUNITY')
        make_profile(self.draft_other, 'IMPACT',
                     who_is_affected='Not published.')

    def test_six_part_structure_labels_render(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.story.slug]))
        self.assertEqual(response.status_code, 200)
        for label in ('The story in six parts',
                      'Part 1 · Who is affected',
                      'Part 2 · Their situation',
                      'Part 3 · Who contributed to the change',
                      'Part 4 · What the evidence shows',
                      'Part 5 · How the story developed',
                      'Part 6 · What remains'):
            self.assertContains(response, label)
        self.assertContains(
            response, 'The traders association rebuilt the stalls')
        self.assertContains(response, 'What is still unclear')
        self.assertContains(response, 'What they need — and what to watch')

    def test_related_impact_files_render_published_only(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.story.slug]))
        content = response.content.decode()
        rail = content.find('More Human Impact Files')
        self.assertGreater(rail, -1)
        self.assertGreater(content.find('A Borehole For Maiyama'), rail)
        self.assertNotContains(response, 'Draft Impact File')

    def test_consent_internals_stay_off_the_detail_page(self):
        response = self.client.get(
            reverse('campaigns:article_detail', args=[self.story.slug]))
        self.assertNotContains(response, 'INTERNAL-DESC-P3')
        self.assertNotContains(response, 'INTERNAL-NOTES-P3')

    def test_consent_guard_still_blocks_identifiable_story(self):
        article = make_article(
            self.editor, 'Identifiable Without Consent', status='PENDING')
        make_profile(article, 'IMPACT', features_identifiable_people=True,
                     who_is_affected='A named trader.')
        with self.assertRaises(ConsentRequiredError):
            publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertNotEqual(article.status, 'PUBLISHED')

    def test_consent_guard_passes_with_a_record_on_file(self):
        article = make_article(
            self.editor, 'Identifiable With Consent', status='PENDING')
        make_profile(article, 'IMPACT', features_identifiable_people=True,
                     who_is_affected='A named trader.')
        ConsentRecord.objects.create(
            article=article, subject_descriptor='Trader, Argungu',
            consent_basis='WRITTEN', recorded_by=self.editor)
        publish_campaign(article, self.editor)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')


# ─── Future Signal hub ───────────────────────────────────────────────────────

class SignalHubPriority3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p3_signal_editor')

    def setUp(self):
        self.agri = make_article(self.editor, 'Rainfall And The Harvest')
        make_profile(self.agri, 'SIGNAL', signal_category='AGRICULTURE_FOOD',
                     signal_confidence='DEVELOPING',
                     signal_observation='Rains started early, then stopped.')
        self.econ = make_article(self.editor, 'Youth Work Outlook')
        make_profile(self.econ, 'SIGNAL', signal_category='ECONOMIC_OUTLOOK',
                     signal_confidence='EMERGING',
                     signal_observation='Employers ask for digital skills.')
        self.unthemed = make_article(self.editor, 'An Unthemed Signal')
        make_profile(self.unthemed, 'SIGNAL',
                     signal_observation='Something is shifting.')

    def test_hub_lists_all_signals_with_hero_no_credit(self):
        response = self.client.get(reverse('signals:list'))
        self.assertEqual(response.status_code, 200)
        for title in ('Rainfall And The Harvest', 'Youth Work Outlook',
                      'An Unthemed Signal'):
            self.assertContains(response, title)
        self.assertContains(response, 'img/signals-hero')
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotContains(
            response, 'Threshing the rice harvest, Kebbi State — Photo: Reuters')
        self.assertNotContains(response, 'kpn-hero-credit')

    def test_methodology_note_uses_the_briefs_wording(self):
        response = self.client.get(reverse('signals:list'))
        self.assertContains(
            response, 'never presents predictions as established facts')
        self.assertContains(response, 'confirmed facts, estimates, '
                                      'projections and analyst judgments')
        self.assertNotContains(response, 'not predictions')

    def test_theme_filter_shows_only_that_theme(self):
        response = self.client.get(
            reverse('signals:list'), {'theme': 'AGRICULTURE_FOOD'})
        self.assertContains(response, 'Rainfall And The Harvest')
        self.assertNotContains(response, 'Youth Work Outlook')
        self.assertNotContains(response, 'An Unthemed Signal')

    def test_confidence_filter_shows_only_that_strength(self):
        response = self.client.get(
            reverse('signals:list'), {'confidence': 'EMERGING'})
        self.assertContains(response, 'Youth Work Outlook')
        self.assertNotContains(response, 'Rainfall And The Harvest')

    def test_unthemed_signal_browses_under_all_only(self):
        response = self.client.get(
            reverse('signals:list'), {'theme': 'ECONOMIC_OUTLOOK'})
        self.assertNotContains(response, 'An Unthemed Signal')
        self.assertContains(response, 'Youth Work Outlook')


# ─── Future Signal article page: six questions, separated epistemics ─────────

class SignalDetailPriority3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p3_signal_detail_editor')

    def setUp(self):
        zone = Zone.objects.create(name='P3 Test Zone')
        self.lga = LGA.objects.create(name='Jega', zone=zone)
        self.base = make_article(self.editor, 'Early Rains Arrive In Kebbi')
        self.signal = make_article(
            self.editor, 'A Farming Season At Risk', category='AGRICULTURE')
        profile = make_profile(
            self.signal, 'SIGNAL',
            signal_observation='Early rains arrived, then stopped.',
            why_it_matters='Planting decisions depend on it.',
            who_is_affected='Rain-fed farmers across the state.',
            what_is_unknown='Whether the rains will return in time.',
            what_to_watch='Weekly rainfall reports.',
            signal_confidence='DEVELOPING',
            signal_horizon='This farming season',
            signal_change_condition='Three weeks of steady rain.',
            signal_category='AGRICULTURE_FOOD')
        profile.related_stories.add(self.base)
        Claim.objects.create(
            article=self.signal,
            text='Rainfall in May was below the seasonal average.',
            status='CONFIRMED', noted_by=self.editor)
        Claim.objects.create(
            article=self.signal,
            text='The ministry projects a late harvest.',
            status='OFFICIAL_STATEMENT', source_name='State ministry',
            noted_by=self.editor)
        Claim.objects.create(
            article=self.signal,
            text='Dry spells may lengthen in June.',
            status='DEVELOPING', noted_by=self.editor)
        ArticleLocation.objects.create(
            article=self.signal, lga=self.lga, kind='MANUAL')

    def _page(self):
        return self.client.get(
            reverse('campaigns:article_detail', args=[self.signal.slug]))

    def test_six_question_headings_render(self):
        response = self._page()
        self.assertEqual(response.status_code, 200)
        for label in ('1 · What we are seeing',
                      '2 · What evidence is available?',
                      '3 · Who could be affected?',
                      '4 · Why it matters to Kebbi',
                      '5 · What remains uncertain?',
                      '6 · What is KPN watching next?'):
            self.assertContains(response, label)

    def test_epistemic_groups_are_labelled_and_kept_apart(self):
        response = self._page()
        content = response.content.decode()
        for label in ('Confirmed facts', 'Estimates and official statements',
                      'Still being established', 'Analyst judgment',
                      'Projections — forward-looking'):
            self.assertIn(label, content)
        facts = content.find('Confirmed facts')
        estimates = content.find('Estimates and official statements')
        confirmed_claim = content.find('Rainfall in May was below')
        official_claim = content.find('The ministry projects a late harvest.')
        # The confirmed claim sits inside the facts group; the official
        # statement sits inside its own group, after the facts group.
        self.assertLess(facts, confirmed_claim)
        self.assertLess(confirmed_claim, estimates)
        self.assertGreater(official_claim, estimates)

    def test_confidence_is_evidence_strength_never_probability(self):
        response = self._page()
        self.assertContains(
            response, 'Developing — the evidence is growing')
        content = response.content.decode().lower()
        self.assertNotIn('probabilit', content)
        self.assertNotIn('likelihood', content)

    def test_recorded_lga_reach_renders_with_its_public_page_link(self):
        response = self._page()
        self.assertContains(response, 'Jega LGA')
        self.assertContains(response, '/newsroom/lga/jega/')

    def test_evidence_base_and_change_condition_render(self):
        response = self._page()
        self.assertContains(response, 'Stories this analysis is based on')
        self.assertContains(response, 'Early Rains Arrive In Kebbi')
        self.assertContains(response, 'Three weeks of steady rain.')
        self.assertContains(response, 'This farming season')
