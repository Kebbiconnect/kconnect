"""Page-by-Page Upgrade · Priority 2 tests.

Covers: the Community Hub lifecycle extension (brief §D — PAUSED /
CANCELLED added, PLANNING shown as "Planned", structured LGA/ward,
objective/dates/team/results), the public moderated community-report
route (D-08 — one queue, nothing auto-published), Community Voice
publication as an explicit reviewer decision with reporter PII never
public, the Civic Engagement & Advocacy section (D-11 — /civic/ and
/advocacy/ both survive; five subsections), advocacy campaigns shown
with their full brief structure (objective, background, evidence,
affected communities, proposed action, team, activity log, government
response, outcome), and Election Observation per D-12 (guidance plus
findings linked from real published records only).
"""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from core.models import (AdvocacyActivity, AdvocacyCampaign,
                         CommunityInitiative, CommunityReport, Opportunity)
from editorial.tests.helpers import general_member, geo, media_director

BODY_JSON = {'blocks': [{'type': 'paragraph', 'data': {'text': 'Body text.'}}]}


def make_initiative(title, status='ACTIVE', **kw):
    kw.setdefault('category', 'PROJECT')
    kw.setdefault('description', 'Synthetic description.')
    kw.setdefault('location_text', 'Synthetic location')
    return CommunityInitiative.objects.create(title=title, status=status, **kw)


def make_campaign(title, status='ACTIVE', **kw):
    kw.setdefault('issue', 'Synthetic issue.')
    kw.setdefault('background', 'Synthetic background.')
    return AdvocacyCampaign.objects.create(title=title, status=status, **kw)


def make_report(**kw):
    zone, lga, ward = geo()
    kw.setdefault('reporter_name', 'Synthetic Reporter')
    kw.setdefault('reporter_phone', '08030000000')
    kw.setdefault('category', 'INFRASTRUCTURE')
    kw.setdefault('lga', lga)
    kw.setdefault('ward', ward)
    kw.setdefault('location_details', 'Synthetic street')
    kw.setdefault('incident_date', timezone.localdate())
    kw.setdefault('what_happened', 'The synthetic bridge is damaged.')
    return CommunityReport.objects.create(**kw)


class CommunityHubTests(TestCase):
    def test_hub_renders_with_real_hero_no_credit(self):
        response = self.client.get(reverse('core:community'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Community Hub')
        self.assertContains(response, 'community-hero')
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotContains(response, 'ActionAid Nigeria')
        self.assertNotContains(response, 'kpn-hero-credit')

    def test_lifecycle_labels_use_public_wording(self):
        make_initiative('Planned Water Project', status='PLANNING')
        make_initiative('Paused Market Work', status='PAUSED')
        make_initiative('Cancelled Borehole', status='CANCELLED')
        response = self.client.get(reverse('core:community'))
        self.assertContains(response, 'Planned')
        self.assertContains(response, 'Paused')
        self.assertContains(response, 'Cancelled')

    def test_planned_is_not_presented_as_active(self):
        make_initiative('Future Outreach Only', status='PLANNING')
        response = self.client.get(reverse('core:community'))
        self.assertContains(response, 'No initiative is marked active right now')

    def test_status_filter(self):
        make_initiative('Active Market Cleanup', status='ACTIVE')
        make_initiative('Paused Market Cleanup', status='PAUSED')
        response = self.client.get(reverse('core:community'), {'status': 'PAUSED'})
        self.assertContains(response, 'Paused Market Cleanup')
        self.assertNotContains(response, 'Active Market Cleanup')

    def test_category_and_lga_filters(self):
        zone, lga, ward = geo()
        make_initiative('Welfare Visit', category='WELFARE', lga=lga, ward=ward)
        make_initiative('Road Project', category='PROJECT')
        response = self.client.get(reverse('core:community'), {'category': 'WELFARE'})
        self.assertContains(response, 'Welfare Visit')
        self.assertNotContains(response, 'Road Project')
        response = self.client.get(reverse('core:community'), {'lga': str(lga.pk)})
        self.assertContains(response, 'Welfare Visit')
        self.assertNotContains(response, 'Road Project')

    def test_upcoming_outreach_needs_a_future_start_date(self):
        today = timezone.localdate()
        make_initiative('Future Health Outreach', status='PLANNING',
                        start_date=today + timedelta(days=10))
        response = self.client.get(reverse('core:community'))
        self.assertContains(response, 'Upcoming outreach')
        self.assertContains(response, 'Future Health Outreach')

    def test_no_upcoming_section_without_records(self):
        make_initiative('Undated Plan', status='PLANNING')
        response = self.client.get(reverse('core:community'))
        self.assertNotContains(response, 'Upcoming outreach')

    def test_volunteer_opportunities_linked_from_hub(self):
        Opportunity.objects.create(
            title='Synthetic Volunteer Call', slug='synthetic-volunteer',
            category='VOLUNTEER', provider='KPN', description='Help out.',
            application_link='https://example.org/volunteer', status='OPEN')
        response = self.client.get(reverse('core:community'))
        self.assertContains(response, 'Synthetic Volunteer Call')

    def test_initiative_detail_shows_full_record(self):
        zone, lga, ward = geo()
        initiative = make_initiative(
            'Detailed Initiative', status='COMPLETED', lga=lga, ward=ward,
            objective='Bring clean water to the ward.',
            responsible_team='KPN Community Team',
            results='Two boreholes repaired.',
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() - timedelta(days=2),
            people_reached=450)
        response = self.client.get(reverse(
            'core:community_initiative_detail', kwargs={'pk': initiative.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bring clean water to the ward.')
        self.assertContains(response, 'KPN Community Team')
        self.assertContains(response, 'Documented results')
        self.assertContains(response, 'Two boreholes repaired.')
        self.assertContains(response, 'Editorial Test LGA')

    def test_initiative_detail_404(self):
        response = self.client.get(reverse(
            'core:community_initiative_detail', kwargs={'pk': 99999}))
        self.assertEqual(response.status_code, 404)


class PublicCommunityReportTests(TestCase):
    def setUp(self):
        cache.clear()

    def _payload(self):
        zone, lga, ward = geo()
        return {
            'reporter_name': 'Public Reporter',
            'reporter_phone': '08031112222',
            'category': 'INFRASTRUCTURE',
            'lga': str(lga.pk), 'ward': str(ward.pk),
            'location_details': 'By the old market',
            'incident_date': str(timezone.localdate()),
            'what_happened': 'The public tap has been dry for weeks.',
            'who_was_involved': '', 'why_is_it_important': '',
        }

    def test_form_states_moderation(self):
        response = self.client.get(reverse('core:community_report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'does not publish it')

    def test_submission_lands_pending_and_unpublished(self):
        response = self.client.post(
            reverse('core:community_report'), self._payload())
        self.assertRedirects(response, reverse('core:community_report_submitted'))
        report = CommunityReport.objects.get()
        self.assertEqual(report.status, 'PENDING')
        self.assertFalse(report.published_to_voice)
        self.assertIsNone(report.submitted_by)

    def test_submission_is_not_on_community_voice(self):
        self.client.post(reverse('core:community_report'), self._payload())
        response = self.client.get(reverse('core:community_voice'))
        self.assertNotContains(response, 'public tap has been dry')

    def test_invalid_submission_creates_nothing(self):
        payload = self._payload()
        payload['what_happened'] = ''
        response = self.client.post(reverse('core:community_report'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CommunityReport.objects.count(), 0)

    def test_confirmation_page(self):
        response = self.client.get(reverse('core:community_report_submitted'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'has been received')


class CommunityVoiceTests(TestCase):
    def test_only_voice_published_concerns_show(self):
        make_report()
        response = self.client.get(reverse('core:community_voice'))
        self.assertNotContains(response, 'synthetic bridge is damaged')
        self.assertContains(response, 'No documented concerns have been published yet')

    def test_voice_shows_concern_without_reporter_pii(self):
        report = make_report(published_to_voice=True, info_status='CONFIRMED',
                             voice_published_at=timezone.now())
        response = self.client.get(reverse('core:community_voice'))
        self.assertContains(response, 'The synthetic bridge is damaged.')
        self.assertContains(response, 'Community-raised, not KPN findings')
        self.assertContains(response, report.get_info_status_display())
        self.assertNotContains(response, 'Synthetic Reporter')
        self.assertNotContains(response, '08030000000')

    def test_escalated_concern_links_to_campaign(self):
        campaign = make_campaign('Fix the Bridge Campaign')
        make_report(published_to_voice=True, status='ESCALATED',
                    escalated_campaign=campaign,
                    voice_published_at=timezone.now())
        response = self.client.get(reverse('core:community_voice'))
        self.assertContains(response, 'Fix the Bridge Campaign')
        self.assertContains(response, reverse(
            'core:advocacy_detail', kwargs={'pk': campaign.pk}))


class StaffVoiceAndEscalationTests(TestCase):
    def setUp(self):
        self.director = media_director('p2_director')
        self.report = make_report()

    def test_director_publishes_to_voice(self):
        self.client.force_login(self.director)
        response = self.client.post(
            reverse('staff:community_report_review',
                    kwargs={'report_id': self.report.pk}),
            {'action': 'approve', 'info_status': 'VERIFIED',
             'voice_panel': '1', 'publish_to_voice': 'on'})
        self.assertEqual(response.status_code, 302)
        self.report.refresh_from_db()
        self.assertTrue(self.report.published_to_voice)
        self.assertIsNotNone(self.report.voice_published_at)
        self.assertEqual(self.report.status, 'APPROVED')

    def test_approval_alone_does_not_publish_to_voice(self):
        self.client.force_login(self.director)
        self.client.post(
            reverse('staff:community_report_review',
                    kwargs={'report_id': self.report.pk}),
            {'action': 'approve', 'info_status': 'VERIFIED'})
        self.report.refresh_from_db()
        self.assertFalse(self.report.published_to_voice)

    def test_director_escalates_with_link(self):
        campaign = make_campaign('Escalation Target')
        self.client.force_login(self.director)
        self.client.post(
            reverse('staff:community_report_review',
                    kwargs={'report_id': self.report.pk}),
            {'action': 'escalate', 'escalated_campaign': str(campaign.pk),
             'voice_panel': '1'})
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'ESCALATED')
        self.assertEqual(self.report.escalated_campaign, campaign)

    def test_member_cannot_publish_to_voice(self):
        # specific_role_required turns non-privileged users away with a
        # redirect to their dashboard (existing site behaviour); the
        # protection property is that the report is untouched.
        self.client.force_login(general_member('p2_member'))
        response = self.client.post(
            reverse('staff:community_report_review',
                    kwargs={'report_id': self.report.pk}),
            {'action': 'approve', 'info_status': 'VERIFIED',
             'voice_panel': '1', 'publish_to_voice': 'on'})
        self.assertEqual(response.status_code, 302)
        self.report.refresh_from_db()
        self.assertFalse(self.report.published_to_voice)
        self.assertEqual(self.report.status, 'PENDING')


class AdvocacyCampaignTests(TestCase):
    def test_list_groups_current_and_concluded(self):
        make_campaign('Ongoing Road Campaign', status='ACTIVE')
        make_campaign('Finished Water Campaign', status='COMPLETED')
        response = self.client.get(reverse('core:advocacy'))
        self.assertContains(response, 'Current campaigns')
        self.assertContains(response, 'Ongoing Road Campaign')
        self.assertContains(response, 'Concluded campaigns')
        self.assertContains(response, 'Finished Water Campaign')

    def test_inactive_campaign_hidden_and_detail_404(self):
        campaign = make_campaign('Hidden Campaign', is_active=False)
        response = self.client.get(reverse('core:advocacy'))
        self.assertNotContains(response, 'Hidden Campaign')
        response = self.client.get(reverse(
            'core:advocacy_detail', kwargs={'pk': campaign.pk}))
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_full_brief_structure(self):
        author = media_director('p2_author')
        article = Campaign.objects.create(
            author=author, slug='bridge-evidence', title='Bridge Evidence Story',
            content='Body.', content_json=BODY_JSON, status='PUBLISHED',
            story_id='KPN-SI-2026-00999')
        campaign = make_campaign(
            'Full Structure Campaign', status='COMPLETED',
            objective='Get the bridge repaired.',
            affected_communities='Three villages across the river.',
            proposed_action='Formal request to the ministry.',
            kpn_position='KPN Position Statement Text',
            actions_taken='Petition delivered.',
            government_response='The ministry promised inspection.',
            outcome='Bridge repaired and reopened.',
            responsible_team='Civic Engagement Team')
        campaign.evidence_articles.add(article)
        AdvocacyActivity.objects.create(
            campaign=campaign, date=timezone.localdate(),
            entry='Delegation met the commissioner.')
        response = self.client.get(reverse(
            'core:advocacy_detail', kwargs={'pk': campaign.pk}))
        self.assertEqual(response.status_code, 200)
        for text in ('Get the bridge repaired.', 'Synthetic background.',
                     'Three villages across the river.',
                     'Formal request to the ministry.',
                     "KPN's position", 'KPN Position Statement Text',
                     'Petition delivered.',
                     'The ministry promised inspection.',
                     'Bridge repaired and reopened.',
                     'Civic Engagement Team',
                     'Delegation met the commissioner.',
                     'Bridge Evidence Story', 'KPN-SI-2026-00999',
                     'Government response'):
            self.assertContains(response, text)

    def test_draft_evidence_article_not_shown(self):
        author = media_director('p2_author2')
        draft = Campaign.objects.create(
            author=author, slug='draft-evidence', title='Unpublished Evidence',
            content='Body.', content_json=BODY_JSON, status='DRAFT')
        campaign = make_campaign('Evidence Gate Campaign')
        campaign.evidence_articles.add(draft)
        response = self.client.get(reverse(
            'core:advocacy_detail', kwargs={'pk': campaign.pk}))
        self.assertNotContains(response, 'Unpublished Evidence')

    def test_staff_activity_log_round_trip(self):
        director = media_director('p2_director2')
        campaign = make_campaign('Logged Campaign')
        self.client.force_login(director)
        response = self.client.post(
            reverse('staff:manage_advocacy_activities',
                    kwargs={'pk': campaign.pk}),
            {'date': str(timezone.localdate()),
             'entry': 'Community meeting held in the ward.'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(campaign.activities.count(), 1)
        response = self.client.get(reverse(
            'core:advocacy_detail', kwargs={'pk': campaign.pk}))
        self.assertContains(response, 'Community meeting held in the ward.')
        self.assertContains(response, 'Progress and activities')


class CivicSectionTests(TestCase):
    def test_landing_has_five_subsections_and_nonpartisan_note(self):
        response = self.client.get(reverse('core:civic'))
        self.assertEqual(response.status_code, 200)
        for text in ('Civic Education', 'Governance &amp; Accountability',
                     'Community Voice', 'Advocacy Campaigns',
                     'Election Observation', 'KPN is non-partisan',
                     'civic-hero'):
            self.assertContains(response, text)
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotContains(response, 'Channels Television')
        self.assertNotContains(response, 'kpn-hero-credit')

    def test_education_page(self):
        response = self.client.get(reverse('core:civic_education'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Voter Education')

    def test_governance_links_into_existing_trackers(self):
        response = self.client.get(reverse('core:civic_governance'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('promises:list'))
        self.assertContains(response, reverse('projects:list'))
        self.assertContains(response, reverse('archive:home'))

    def test_election_observation_empty_state(self):
        response = self.client.get(reverse('core:election_observation'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No observation findings have been published yet')

    def test_election_observation_links_real_findings(self):
        author = media_director('p2_author3')
        article = Campaign.objects.create(
            author=author, slug='election-findings',
            title='KPN Observers Report Calm Election Day',
            content='Body.', content_json=BODY_JSON, status='PUBLISHED')
        Campaign.objects.filter(pk=article.pk).update(
            published_at=timezone.now())
        response = self.client.get(reverse('core:election_observation'))
        self.assertContains(response, 'KPN Observers Report Calm Election Day')

    def test_old_routes_survive(self):
        for name in ('core:civic', 'core:advocacy', 'core:community',
                     'core:report_a_story'):
            url = reverse(name)
            self.assertTrue(url)
        self.assertEqual(self.client.get(reverse('core:civic')).status_code, 200)
        self.assertEqual(self.client.get(reverse('core:advocacy')).status_code, 200)

    def test_nav_links_new_subsections(self):
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, reverse('core:civic_education'))
        self.assertContains(response, reverse('core:community_voice'))
        self.assertContains(response, reverse('core:election_observation'))
        self.assertContains(response, reverse('core:community_report'))
