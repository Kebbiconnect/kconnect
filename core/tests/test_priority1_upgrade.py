"""Page-by-Page Upgrade · Priority 1 tests.

Covers: the VERIFICATION_PENDING opportunity status and its public
rules (D-06), the opportunity detail page, the expired-opportunities
archive, suspicious-listing reports and staff triage (D-07), the
newsroom date/provenance filters and the documented featured rule
(D-09), and the restructured navigation.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from core.models import Opportunity, OpportunityReport
from editorial.tests.helpers import media_director

BODY_JSON = {'blocks': [{'type': 'paragraph', 'data': {'text': 'Body text.'}}]}


def make_opp(slug, status='OPEN', **kw):
    kw.setdefault('title', slug.replace('-', ' ').title())
    kw.setdefault('provider', 'Synthetic Provider')
    kw.setdefault('description', 'Synthetic description.')
    kw.setdefault('application_link', 'https://example.org/apply')
    return Opportunity.objects.create(slug=slug, status=status, **kw)


class OpportunityTrustTests(TestCase):
    def test_pending_listing_on_hub_without_application_link(self):
        make_opp('pending-one', status='VERIFICATION_PENDING')
        response = self.client.get(reverse('core:opportunities'))
        self.assertContains(response, 'Verifying')
        self.assertContains(response, 'Details pending')

    def test_pending_detail_hides_application_link(self):
        opp = make_opp('pending-two', status='VERIFICATION_PENDING')
        response = self.client.get(
            reverse('core:opportunity_detail', kwargs={'slug': opp.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'https://example.org/apply')
        self.assertContains(response, 'Verification pending')

    def test_open_detail_shows_official_link_from_record(self):
        opp = make_opp('open-one', status='OPEN',
                       deadline=timezone.localdate() + timedelta(days=30))
        response = self.client.get(
            reverse('core:opportunity_detail', kwargs={'slug': opp.slug}))
        self.assertContains(response, 'https://example.org/apply')
        self.assertContains(response, 'Synthetic Provider')

    def test_detail_shows_new_fields_when_set(self):
        opp = make_opp('open-two', status='OPEN', opens_at=timezone.localdate(),
                       location_text='Birnin Kebbi', nigerians_eligible=True,
                       verification_source='Provider official site')
        response = self.client.get(
            reverse('core:opportunity_detail', kwargs={'slug': opp.slug}))
        self.assertContains(response, 'Birnin Kebbi')
        self.assertContains(response, 'Provider official site')

    def test_archive_lists_closed_only(self):
        make_opp('closed-one', status='CLOSED')
        make_opp('open-three', status='OPEN')
        response = self.client.get(reverse('core:opportunities_archive'))
        titles = [o.slug for o in response.context['closed_opps']]
        self.assertEqual(titles, ['closed-one'])
        self.assertContains(response, 'Closed One')

    def test_archive_has_photo_hero_without_credit(self):
        # Consistency Round A (owner, 2026-11-24): the expired archive
        # carries the same photographic hero treatment as the other
        # pages, and hero credit lines are removed site-wide.
        response = self.client.get(reverse('core:opportunities_archive'))
        self.assertContains(response, 'kpn-page-hero-photo')
        self.assertContains(response, 'opportunities-archive-hero')
        self.assertNotContains(response, 'kpn-hero-credit')

    def test_hub_excludes_closed(self):
        make_opp('closed-two', status='CLOSED')
        response = self.client.get(reverse('core:opportunities'))
        slugs = [o.slug for o in response.context['regular_opps']]
        self.assertNotIn('closed-two', slugs)

    def test_hub_status_filter(self):
        make_opp('pending-three', status='VERIFICATION_PENDING')
        make_opp('open-four', status='OPEN')
        response = self.client.get(reverse('core:opportunities'),
                                   {'status': 'VERIFICATION_PENDING'})
        slugs = [o.slug for o in response.context['regular_opps']]
        self.assertEqual(slugs, ['pending-three'])

    def test_hub_search_filter(self):
        make_opp('open-five', status='OPEN', title='Zebra Scholarship Fund')
        make_opp('open-six', status='OPEN', title='Alpha Job Scheme')
        response = self.client.get(reverse('core:opportunities'), {'q': 'Zebra'})
        slugs = [o.slug for o in response.context['regular_opps']]
        self.assertEqual(slugs, ['open-five'])

    def test_hub_has_no_category_pill_row(self):
        # Owner fix round 2: the category pill/chip row was removed from
        # the hub — the dropdown covers category filtering. The pill row
        # was the only source of ?category= links on the page.
        make_opp('open-seven', status='OPEN')
        response = self.client.get(reverse('core:opportunities'))
        self.assertNotContains(response, '?category=')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'All categories')

    def test_hub_category_dropdown_filter(self):
        make_opp('scholarship-one', status='OPEN', category='SCHOLARSHIP')
        make_opp('job-one', status='OPEN', category='JOB')
        response = self.client.get(reverse('core:opportunities'),
                                   {'category': 'JOB'})
        slugs = [o.slug for o in response.context['regular_opps']]
        self.assertEqual(slugs, ['job-one'])
        # The dropdown keeps the chosen category selected.
        self.assertContains(response, 'value="JOB" selected')

    def test_hub_paginates_at_twelve_per_page(self):
        # Scroll-length fix: the hub previously rendered every live
        # listing on one page, which grew without bound as listings
        # accumulated and buried the footer navigation.
        for i in range(1, 16):
            make_opp(f'paged-{i:02d}', status='OPEN')
        first = self.client.get(reverse('core:opportunities'))
        page = first.context['page_obj']
        self.assertEqual(len(page.object_list), 12)
        self.assertEqual(page.paginator.num_pages, 2)
        self.assertContains(first, 'page=2')
        self.assertContains(first, 'Page 1 of 2')
        second = self.client.get(reverse('core:opportunities'),
                                  {'page': '2'})
        second_slugs = [o.slug for o in second.context['regular_opps']]
        self.assertEqual(len(second_slugs), 3)
        first_slugs = {o.slug for o in first.context['regular_opps']}
        self.assertTrue(first_slugs.isdisjoint(second_slugs))

    def test_hub_pagination_preserves_filters(self):
        for i in range(1, 15):
            make_opp(f'paged-job-{i:02d}', status='OPEN', category='JOB')
        make_opp('paged-grant', status='OPEN', category='GRANT')
        response = self.client.get(reverse('core:opportunities'),
                                   {'category': 'JOB'})
        self.assertContains(response, 'category=JOB')
        self.assertContains(response, 'page=2')

    def test_expired_archive_paginates_at_twelve_per_page(self):
        for i in range(1, 14):
            make_opp(f'expired-{i:02d}', status='CLOSED')
        first = self.client.get(reverse('core:opportunities_archive'))
        page = first.context['page_obj']
        self.assertEqual(len(page.object_list), 12)
        self.assertEqual(page.paginator.num_pages, 2)
        second = self.client.get(reverse('core:opportunities_archive'),
                                  {'page': '2'})
        self.assertEqual(len(second.context['closed_opps'].object_list), 1)


class OpportunityReportTests(TestCase):
    def setUp(self):
        self.opp = make_opp('reported-one', status='OPEN')
        self.director = media_director('p1_director')

    def test_public_report_creates_queued_record(self):
        response = self.client.post(
            reverse('core:report_opportunity', kwargs={'slug': self.opp.slug}),
            {'reason': 'Asks applicants to pay a fee by transfer.',
             'reporter_name': 'Amina', 'reporter_contact': ''})
        self.assertEqual(response.status_code, 302)
        report = OpportunityReport.objects.get(opportunity=self.opp)
        self.assertEqual(report.status, 'NEW')
        # Nothing about the listing itself changed.
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.status, 'OPEN')

    def test_report_requires_reason(self):
        response = self.client.post(
            reverse('core:report_opportunity', kwargs={'slug': self.opp.slug}),
            {'reason': '', 'reporter_name': '', 'reporter_contact': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OpportunityReport.objects.count(), 0)

    def test_triage_queue_visible_to_director(self):
        OpportunityReport.objects.create(
            opportunity=self.opp, reason='Looks fake.')
        self.client.force_login(self.director)
        response = self.client.get(reverse('staff:manage_opportunities'))
        self.assertContains(response, 'triage queue')
        self.assertContains(response, 'Looks fake.')

    def test_uphold_moves_listing_to_verification_pending(self):
        report = OpportunityReport.objects.create(
            opportunity=self.opp, reason='Looks fake.')
        self.client.force_login(self.director)
        response = self.client.post(
            reverse('staff:opportunity_report_action',
                    kwargs={'report_id': report.pk}),
            {'action': 'uphold'})
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.opp.refresh_from_db()
        self.assertEqual(report.status, 'UPHELD')
        self.assertEqual(report.reviewed_by, self.director)
        self.assertEqual(self.opp.status, 'VERIFICATION_PENDING')

    def test_dismiss_keeps_listing_open(self):
        report = OpportunityReport.objects.create(
            opportunity=self.opp, reason='Mistaken report.')
        self.client.force_login(self.director)
        self.client.post(
            reverse('staff:opportunity_report_action',
                    kwargs={'report_id': report.pk}),
            {'action': 'dismiss'})
        report.refresh_from_db()
        self.opp.refresh_from_db()
        self.assertEqual(report.status, 'DISMISSED')
        self.assertEqual(self.opp.status, 'OPEN')

    def test_triage_forbidden_for_non_privileged_member(self):
        from editorial.tests.helpers import general_member
        report = OpportunityReport.objects.create(
            opportunity=self.opp, reason='Looks fake.')
        self.client.force_login(general_member('p1_member'))
        response = self.client.post(
            reverse('staff:opportunity_report_action',
                    kwargs={'report_id': report.pk}),
            {'action': 'uphold'})
        self.assertEqual(response.status_code, 403)
        report.refresh_from_db()
        self.opp.refresh_from_db()
        self.assertEqual(report.status, 'NEW')
        self.assertEqual(self.opp.status, 'OPEN')


def make_article(author, slug, verification='DEVELOPING', days_ago=0, **kw):
    kw.setdefault('title', slug.replace('-', ' ').title())
    kw.setdefault('content', 'Body text.')
    kw.setdefault('content_json', BODY_JSON)
    article = Campaign.objects.create(
        author=author, slug=slug, status='PUBLISHED',
        verification_status=verification, **kw)
    Campaign.objects.filter(pk=article.pk).update(
        published_at=timezone.now() - timedelta(days=days_ago))
    article.refresh_from_db()
    return article


class NewsroomUpgradeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('p1_editor')

    def test_featured_is_latest_verified(self):
        make_article(self.editor, 'newer-developing', verification='DEVELOPING', days_ago=0)
        verified = make_article(self.editor, 'older-verified', verification='VERIFIED', days_ago=2)
        response = self.client.get(reverse('campaigns:newsroom'))
        self.assertEqual(response.context['featured'].pk, verified.pk)
        self.assertNotIn(verified.pk, [a.pk for a in response.context['rest']])

    def test_featured_falls_back_to_latest(self):
        newest = make_article(self.editor, 'only-story', verification='DEVELOPING', days_ago=0)
        response = self.client.get(reverse('campaigns:newsroom'))
        self.assertEqual(response.context['featured'].pk, newest.pk)

    def test_date_filter(self):
        make_article(self.editor, 'recent-story', days_ago=1)
        make_article(self.editor, 'old-story', days_ago=40)
        today = timezone.localdate()
        response = self.client.get(reverse('campaigns:newsroom'), {
            'date_from': (today - timedelta(days=7)).isoformat(),
            'date_to': today.isoformat(),
        })
        slugs = [a.slug for a in response.context['rest']]
        if response.context['featured']:
            slugs.append(response.context['featured'].slug)
        self.assertIn('recent-story', slugs)
        self.assertNotIn('old-story', slugs)

    def test_breaking_lists_recent_developing(self):
        make_article(self.editor, 'fresh-developing', verification='DEVELOPING', days_ago=0)
        make_article(self.editor, 'stale-developing', verification='DEVELOPING', days_ago=10)
        response = self.client.get(reverse('campaigns:newsroom'))
        slugs = [a.slug for a in response.context['breaking']]
        self.assertIn('fresh-developing', slugs)
        self.assertNotIn('stale-developing', slugs)

    def test_community_provenance_filter(self):
        from core.models import CommunityReport
        from story_intelligence.models import StorySourceLink
        plain = make_article(self.editor, 'plain-story')
        linked = make_article(self.editor, 'community-story')
        report = CommunityReport.objects.create(
            category='COMMUNITY', location_details='Birnin Kebbi',
            what_happened='A community concern was raised.')
        StorySourceLink.objects.create(report=report, article=linked)
        response = self.client.get(reverse('campaigns:newsroom'), {'source': 'community'})
        slugs = [a.slug for a in response.context['rest']]
        if response.context['featured']:
            slugs.append(response.context['featured'].slug)
        self.assertIn('community-story', slugs)
        self.assertNotIn('plain-story', slugs)


class NavigationTests(TestCase):
    def test_home_shows_new_nav_structure(self):
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'Civic &amp; Advocacy')
        self.assertContains(response, 'Community Initiatives')
        self.assertContains(response, 'Volunteer Network')
        self.assertContains(response, 'Support KPN')
        # D-05 order inside the Newsroom group: LGA News before Promise Tracker.
        content = response.content.decode()
        self.assertLess(content.index('LGA News'), content.index('Promise Tracker'))
        self.assertLess(content.index('Promise Tracker'), content.index('Project Tracker'))
        self.assertLess(content.index('Project Tracker'), content.index('Human Impact Files'))

    def test_home_figures_band_removed(self):
        # Owner fix round (Priority 1 gate): the network-figures band no
        # longer renders on the homepage — the figures live on the Impact
        # & Metrics page. The view still computes them unchanged (no
        # metric formula was touched), so the context key stays present.
        response = self.client.get(reverse('core:home'))
        self.assertIn('network_figures', response.context)
        self.assertNotContains(response, 'KPN across Kebbi State')
        self.assertNotContains(response, 'Verified members')
        self.assertNotContains(response, 'Communities reached')

    def test_all_nav_targets_resolve(self):
        for name in ('core:home', 'campaigns:newsroom', 'lga_news:index',
                     'promises:list', 'projects:list', 'impact_files:list',
                     'signals:list', 'archive:home', 'core:opportunities',
                     'core:community', 'staff:register', 'core:report_a_story',
                     'core:civic', 'core:advocacy', 'core:leadership',
                     'core:patrons', 'core:impact', 'core:code_of_conduct',
                     'core:about', 'core:contact', 'core:support_us'):
            with self.subTest(name=name):
                self.assertTrue(reverse(name))
