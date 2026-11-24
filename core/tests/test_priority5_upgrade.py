"""Page-by-Page Upgrade · Priority 5 tests (brief §H, Impact & Metrics).

Covers: the D-02 removal of the hardcoded max(50, …) communities-
reached floor (the figure is the true recorded sum, on the impact
page and in the home view's figures); the metric registry — every
figure computed from the records it counts and rendered with its
definition, reporting period, last-updated date and source; the
honest "Not yet recorded" state for metrics with no underlying
records; the brief's unverified 327+ / 20-21 / 93-225 figures never
appearing; D-14 (no financial figures published); and the public
Kebbi coverage map — real COD-AB boundaries, choropleth strength from
the five public record types, uncovered LGAs shown as not covered,
per-LGA summary panel, and no staff-only data (member names) leaking.
"""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from core.models import CommunityInitiative, ImpactStory, Opportunity
from donations.models import Donation
from intelligence.models import ArticleLocation, Project
from leadership.models import LGA, Ward, Zone
from staff.models import User, YouthProgram
from story_intelligence.models import Institution, Promise, StoryProfile


def make_geo(name='Jega', ward_name='Jega Ward'):
    zone, _ = Zone.objects.get_or_create(name='Test Zone')
    lga, _ = LGA.objects.get_or_create(name=name, zone=zone)
    ward, _ = Ward.objects.get_or_create(name=ward_name, lga=lga)
    return zone, lga, ward


def make_member(username, lga=None, ward=None, status='VERIFIED'):
    return User.objects.create_user(
        username=username, phone=username, role='GENERAL',
        status=status, lga=lga, ward=ward,
        first_name='Synthetic', last_name='Memberperson')


def make_article(title, **kw):
    author, _ = User.objects.get_or_create(
        username='p5_author',
        defaults={'phone': 'p5_author', 'role': 'GENERAL',
                  'status': 'PENDING'})
    kw.setdefault('slug', title.lower().replace(' ', '-'))
    kw.setdefault('content', 'Body text.')
    kw.setdefault('status', 'PUBLISHED')
    kw.setdefault('published_at', timezone.now())
    kw.setdefault('author', author)
    return Campaign.objects.create(title=title, **kw)


def metrics_by_key(response):
    found = {}
    for group in response.context['metric_groups']:
        for metric in group['metrics']:
            found[metric['key']] = metric
    return found


class CommunitiesReachedFloorTests(TestCase):
    """D-02: no floor — the figure is the true recorded sum."""

    def test_small_sum_is_shown_as_recorded_not_floored(self):
        ImpactStory.objects.create(
            title='Small recorded reach', category='PROJECT',
            description='Synthetic.', communities_reached=3,
            people_impacted=10, is_published=True)
        response = self.client.get(reverse('core:impact'))
        self.assertEqual(response.context['communities_reached'], 3)
        metric = metrics_by_key(response)['communities_reached']
        self.assertEqual(metric['value'], 3)
        self.assertTrue(metric['recorded'])

    def test_no_stories_means_not_recorded_never_fifty(self):
        response = self.client.get(reverse('core:impact'))
        self.assertEqual(response.context['communities_reached'], 0)
        metric = metrics_by_key(response)['communities_reached']
        self.assertFalse(metric['recorded'])
        self.assertIsNone(metric['value'])
        self.assertContains(response, 'Not yet recorded')

    def test_unpublished_stories_do_not_count(self):
        ImpactStory.objects.create(
            title='Draft reach', category='PROJECT',
            description='Synthetic.', communities_reached=500,
            is_published=False)
        response = self.client.get(reverse('core:impact'))
        self.assertEqual(response.context['communities_reached'], 0)

    def test_home_figures_have_no_floor(self):
        ImpactStory.objects.create(
            title='Home reach', category='PROJECT',
            description='Synthetic.', communities_reached=7,
            is_published=True)
        response = self.client.get(reverse('core:home'))
        self.assertEqual(
            response.context['network_figures']['communities_reached'], 7)


class MetricRegistryTests(TestCase):
    def setUp(self):
        _, self.lga, self.ward = make_geo()
        make_member('p5_member_a', lga=self.lga, ward=self.ward)
        make_member('p5_member_b', lga=self.lga, ward=self.ward)
        make_member('p5_pending', lga=self.lga, ward=self.ward,
                    status='PENDING')
        self.article = make_article(
            'Verified Civic Story', category='CIVIC',
            verification_status='VERIFIED')
        StoryProfile.objects.create(article=self.article, kind='IMPACT')
        CommunityInitiative.objects.create(
            title='Synthetic Initiative', category='PROJECT',
            status='ACTIVE', description='Synthetic.',
            location_text='Synthetic place', lga=self.lga,
            people_reached=40)
        YouthProgram.objects.create(
            title='Synthetic Training', description='Synthetic.',
            program_type='TRAINING', status='COMPLETED')
        Opportunity.objects.create(
            title='Synthetic Opportunity', slug='synthetic-opportunity',
            provider='Synthetic Provider',
            category='TRAINING', description='Synthetic.',
            application_link='https://example.org/apply',
            deadline='2027-06-01', status='OPEN')

    def test_six_groups_in_brief_order(self):
        response = self.client.get(reverse('core:impact'))
        names = [g['name'] for g in response.context['metric_groups']]
        self.assertEqual(names, [
            'Network Reach', 'Community Development',
            'Media & Information', 'Youth Empowerment',
            'Civic Engagement', 'Organizational Performance'])

    def test_figures_trace_to_records(self):
        response = self.client.get(reverse('core:impact'))
        metrics = metrics_by_key(response)
        self.assertEqual(metrics['verified_members']['value'], 2)
        self.assertEqual(metrics['active_lgas']['value'], 1)
        self.assertEqual(metrics['active_lgas']['suffix'], ' of 21')
        self.assertEqual(metrics['active_wards']['value'], 1)
        self.assertEqual(metrics['active_wards']['suffix'], ' of 225')
        self.assertEqual(metrics['initiatives']['value'], 1)
        self.assertEqual(metrics['beneficiaries']['value'], 40)
        self.assertEqual(metrics['reports_published']['value'], 1)
        self.assertEqual(metrics['community_stories']['value'], 1)
        self.assertEqual(metrics['verified_reports']['value'], 1)
        self.assertEqual(metrics['civic_education']['value'], 1)
        self.assertEqual(metrics['training']['value'], 1)
        self.assertEqual(metrics['opportunity_programmes']['value'], 1)
        self.assertEqual(metrics['programmes_completed']['value'], 1)

    def test_every_recorded_metric_carries_provenance(self):
        response = self.client.get(reverse('core:impact'))
        for group in response.context['metric_groups']:
            for metric in group['metrics']:
                self.assertTrue(metric['definition'], metric['key'])
                self.assertTrue(metric['source'], metric['key'])
                if metric['recorded']:
                    self.assertTrue(metric['period'], metric['key'])
                    self.assertIsNotNone(
                        metric['last_updated'], metric['key'])

    def test_provenance_is_rendered_beside_figures(self):
        response = self.client.get(reverse('core:impact'))
        self.assertContains(response, 'Reporting period')
        self.assertContains(response, 'Last updated')
        self.assertContains(response, 'Source')
        self.assertContains(
            response, 'Members whose KPN registration has been verified.')
        self.assertContains(response, 'KPN member register')

    def test_unrecorded_metrics_show_honest_state(self):
        response = self.client.get(reverse('core:impact'))
        metrics = metrics_by_key(response)
        # No mentorship programmes, no observer records, no promises.
        self.assertFalse(metrics['mentorship']['recorded'])
        self.assertFalse(metrics['observer_participation']['recorded'])
        self.assertFalse(metrics['commitments_tracked']['recorded'])
        self.assertIsNone(metrics['mentorship']['value'])

    def test_brief_headline_figures_never_appear(self):
        response = self.client.get(reverse('core:impact'))
        self.assertNotContains(response, '327+')
        self.assertNotContains(response, '93 / 225')
        self.assertNotContains(response, '20 / 21')

    def test_financial_figures_are_not_published(self):
        Donation.objects.create(
            donor_name='Synthetic Donor', amount='987654.00',
            reference='P5-TEST-REF', status='VERIFIED')
        response = self.client.get(reverse('core:impact'))
        self.assertNotContains(response, '987654')
        self.assertNotContains(response, 'Synthetic Donor')
        metric = metrics_by_key(response)['financial_transparency']
        self.assertFalse(metric['recorded'])
        self.assertContains(
            response, 'published where approved for publication')


class CoverageMapTests(TestCase):
    def setUp(self):
        _, self.jega, self.jega_ward = make_geo('Jega', 'Jega Ward')
        _, self.zuru, _ = make_geo('Zuru', 'Zuru Ward')
        make_member('p5_cov_a', lga=self.jega, ward=self.jega_ward)
        self.article = make_article('Jega Market Story')
        ArticleLocation.objects.create(
            article=self.article, lga=self.jega, kind='MANUAL')
        CommunityInitiative.objects.create(
            title='Jega Initiative', category='PROJECT', status='ACTIVE',
            description='Synthetic.', location_text='Jega',
            lga=self.jega, people_reached=5)
        institution = Institution.objects.create(
            name='Synthetic Institution', kind='AGENCY')
        Promise.objects.create(
            institution=institution, title='Jega Promise',
            description='Synthetic.', announced_on=timezone.localdate(),
            lga=self.jega, status='ANNOUNCED')
        Project.objects.create(
            title='Jega Project', description='Synthetic.',
            category='ROAD', lga=self.jega, status='IN_PROGRESS')

    def rows_by_name(self, response):
        return {row['lga'].name: row
                for row in response.context['coverage_rows']}

    def test_coverage_counts_from_records(self):
        response = self.client.get(reverse('core:impact'))
        rows = self.rows_by_name(response)
        jega = rows['Jega']
        self.assertEqual(jega['members'], 1)
        self.assertEqual(jega['wards_active'], 1)
        self.assertEqual(jega['wards_total'], 1)
        self.assertEqual(jega['stories'], 1)
        self.assertEqual(jega['initiatives'], 1)
        self.assertEqual(jega['promises'], 1)
        self.assertEqual(jega['projects'], 1)
        self.assertEqual(jega['strength'], 5)
        self.assertTrue(jega['covered'])
        self.assertEqual(jega['fill'], '#176b36')

    def test_uncovered_lga_is_shown_as_not_covered(self):
        response = self.client.get(reverse('core:impact'))
        rows = self.rows_by_name(response)
        zuru = rows['Zuru']
        self.assertEqual(zuru['strength'], 0)
        self.assertFalse(zuru['covered'])
        self.assertEqual(zuru['fill'], '#e9f0ea')
        self.assertContains(response, 'Not yet covered')
        totals = response.context['coverage_totals']
        self.assertEqual(totals['lgas_covered'], 1)
        self.assertEqual(totals['lgas_total'], 2)

    def test_map_renders_real_boundaries_and_attribution(self):
        response = self.client.get(reverse('core:impact'))
        # The Jega path from the validated COD-AB geometry.
        self.assertContains(response, 'M392.8,398.8L372.8,402.6')
        self.assertContains(response, 'COD-AB')
        self.assertContains(response, 'Humanitarian Data Exchange')

    def test_map_renders_at_all_widths(self):
        # Owner correction 2026-11-24: the coverage map shows on
        # mobile too — no desktop-only wrapper in the markup, the
        # SVG is rendered, the LGA list stays below it, and the old
        # under-900px hiding rule is gone from the design CSS.
        from pathlib import Path

        from django.conf import settings

        response = self.client.get(reverse('core:impact'))
        self.assertContains(response, 'kpn-cov-svg')
        self.assertContains(response, 'kpn-cov-mapwrap')
        self.assertNotContains(response, 'kpn-cov-desktop')
        self.assertContains(response, 'kpn-cov-list')
        css = (Path(settings.BASE_DIR)
               / 'static/staff/css/kpn-design.css').read_text()
        self.assertNotIn('kpn-cov-desktop', css)
        self.assertNotIn('.kpn-cov-desktop { display:none', css)

    def test_draft_stories_do_not_count_as_coverage(self):
        draft = make_article('Unpublished Jega Draft', status='DRAFT',
                             published_at=None)
        ArticleLocation.objects.create(
            article=draft, lga=self.zuru, kind='MANUAL')
        response = self.client.get(reverse('core:impact'))
        rows = self.rows_by_name(response)
        self.assertEqual(rows['Zuru']['stories'], 0)
        self.assertFalse(rows['Zuru']['covered'])

    def test_selected_lga_panel(self):
        response = self.client.get(
            reverse('core:impact'), {'lga': self.jega.pk})
        self.assertEqual(
            response.context['coverage_selected']['lga'], self.jega)
        self.assertContains(response, '5 of 5 record types present')
        self.assertContains(response, 'Read Jega news')

    def test_invalid_lga_param_falls_back_to_statewide(self):
        response = self.client.get(
            reverse('core:impact'), {'lga': 'not-a-number'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['coverage_selected'])

    def test_no_member_names_leak(self):
        response = self.client.get(reverse('core:impact'))
        self.assertNotContains(response, 'Memberperson')
        self.assertNotContains(response, 'p5_cov_a')

    def test_hero_is_real_kebbi_photo_no_credit(self):
        response = self.client.get(reverse('core:impact'))
        self.assertContains(response, 'metrics-hero')
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotContains(
            response,
            'Yauri Rigata, Kebbi State — Photo: Rex Clarke Adventures')
        self.assertNotContains(response, 'kpn-hero-credit')
        self.assertContains(
            response,
            'To show what KPN has actually achieved, where it '
            'operates and how its work is progressing.')
