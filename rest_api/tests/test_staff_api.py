"""Staff API (Android 2.0.0): screens 38, 131–132, 136–139, 160–202.

Every endpoint group is exercised against the same services the web
desks use; capability denials pin the web gates (security desk D6,
ICT holder-only), and payload state names are asserted against the
model choice vocabularies verbatim.
"""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from core.models import (
    AdvocacyActivity, AdvocacyCampaign, IctAdminAssignment, Opportunity,
    OpportunityReport,
)
from editorial.models import Audit as EditorialAudit
from editorial.models import Item as EditorialItem
from editorial.models import Source as EditorialSource
from editorial.tests.helpers import (
    assistant_media, general_member, make_user, media_director, president,
)
from events.models import Event, MeetingMinutes
from intelligence import projects as project_service
from intelligence.connectors import _fingerprint
from intelligence.models import (
    DESK_STATES, Alert, AlertDelivery, EventCluster, FieldReport,
    GeoAlias, IntelligenceCategory, Project, PromiseCandidate,
    PublicationCategory, RawPublication, SecurityIncident,
)
from intelligence.tests.helpers import seed_directory
from leadership.models import LGA
from staff.models import User
from story_intelligence.models import (
    Claim, EvidenceRecord, Institution, Promise,
)
from story_intelligence.services import REDACTION_MARKER

API = '/api/v1/'


def make_source(name='Staff API Source'):
    return EditorialSource.objects.create(
        name=name, kind='NEWS', url='https://feeds.example.com/feed.xml',
        feed=True, enabled=True, connector_kind='RSS', max_items=5)


def make_item(source, title, text='Body text from Jega.'):
    count = RawPublication.objects.count() + 1
    url = f'https://example.com/staff-{count}'
    return RawPublication.objects.create(
        source=source, canonical_url=url, original_url=url, title=title,
        text=text, discovered_at=timezone.now(), fetch_status='CONTENT',
        content_fingerprint=_fingerprint(title, text))


def categorise(item, slug='education', primary=True):
    category = IntelligenceCategory.objects.get(slug=slug)
    PublicationCategory.objects.create(
        publication=item, category=category, is_primary=primary,
        reason='Test fixture.')
    return category


class StaffApiCase(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('staff_director')
        self.president = president('staff_president')
        self.assistant = assistant_media('staff_assistant')
        self.member = general_member('staff_member')
        self.audit_lead = make_user(
            'staff_audit', title='Director of Audit & Accountability')
        self.reporter = make_user(
            'staff_reporter', title=None, role='GENERAL',
            is_trusted_reporter=True)
        self.jega = LGA.objects.get(name='Jega')
        self.source = make_source()

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class OpportunityReportApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        self.opp = Opportunity.objects.create(
            title='Test Grant', slug='test-grant', category='GRANT',
            provider='Test Provider', description='A grant.',
            status='OPEN')

    def test_public_report_creates_record_201(self):
        response = APIClient().post(
            API + 'opportunities/test-grant/report/',
            {'reason': 'Link looks wrong', 'details': 'It redirects.',
             'contact': 'reader@example.com'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        report = OpportunityReport.objects.get(opportunity=self.opp)
        self.assertEqual(report.status, 'NEW')
        self.assertIn('Link looks wrong', report.reason)
        self.assertIn('It redirects.', report.reason)
        self.assertEqual(report.reporter_contact, 'reader@example.com')
        self.assertEqual(response.data['status'], 'NEW')

    def test_report_requires_reason_envelope(self):
        response = APIClient().post(
            API + 'opportunities/test-grant/report/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error']['code'], 'validation_error')
        self.assertFalse(OpportunityReport.objects.exists())


class FieldReportApiTests(StaffApiCase):
    def payload(self):
        category = IntelligenceCategory.objects.get(slug='education')
        return {'headline': 'School roof damaged in Jega',
                'report_text': 'The roof of the primary school was damaged.',
                'lga': self.jega.pk, 'category': category.pk,
                'occurred_at': '2026-11-20T10:30'}

    def test_trusted_reporter_posts_and_lists_own(self):
        client = self.client_for(self.reporter)
        response = client.post(API + 'field-reports/', self.payload(),
                               format='json')
        self.assertEqual(response.status_code, 201, response.content)
        report = FieldReport.objects.get(reporter=self.reporter)
        self.assertIsNotNone(report.publication_id)
        listing = client.get(API + 'field-reports/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['scope'], 'mine')
        self.assertEqual(listing.data['results'][0]['id'], report.pk)
        self.assertIn(listing.data['results'][0]['desk_state'],
                      dict(DESK_STATES))

    def test_plain_member_cannot_submit_or_list(self):
        client = self.client_for(self.member)
        self.assertEqual(client.post(
            API + 'field-reports/', self.payload(), format='json').status_code, 403)
        self.assertEqual(client.get(API + 'field-reports/').status_code, 403)

    def test_reviewer_sees_queue_scope(self):
        self.client_for(self.reporter).post(
            API + 'field-reports/', self.payload(), format='json')
        listing = self.client_for(self.director).get(API + 'field-reports/')
        self.assertEqual(listing.data['scope'], 'queue')
        self.assertEqual(listing.data['count'], 1)


class RankingsCalendarMinutesTests(StaffApiCase):
    def test_rankings_public_with_internal_for_leaders(self):
        response = APIClient().get(API + 'impact/rankings/')
        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.data['top_lgas']]
        self.assertIn('Editorial Test LGA', names)
        self.assertIsNone(response.data['internal_data'])
        leader = self.client_for(self.director).get(API + 'impact/rankings/')
        self.assertIsNotNone(leader.data['internal_data'])
        self.assertIn('pending_reports', leader.data['internal_data'])

    def test_calendar_and_all_minutes(self):
        event = Event.objects.create(
            title='State Meeting', description='Monthly meeting.',
            location='Birnin Kebbi', start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(hours=2),
            created_by=self.director)
        MeetingMinutes.objects.create(
            event=event, content='Full minutes text.',
            summary='Key points.', recorded_by=self.director)
        client = self.client_for(self.member)
        calendar = client.get(API + 'events/calendar/')
        self.assertEqual(calendar.status_code, 200)
        row = calendar.data['results'][0]
        self.assertEqual(row['title'], 'State Meeting')
        self.assertIsNone(row['lga'])
        minutes = client.get(API + 'events/minutes/')
        self.assertEqual(minutes.status_code, 200)
        self.assertEqual(minutes.data['results'][0]['event_title'],
                         'State Meeting')


class AdvocacyDecisionTests(StaffApiCase):
    def test_decision_transitions_and_audit_activity(self):
        campaign = AdvocacyCampaign.objects.create(
            title='Clean Water Campaign', issue='Water access.',
            background='Background.', status='PAUSED', is_active=True)
        client = self.client_for(self.director)
        response = client.post(
            API + f'advocacy/{campaign.pk}/decision/',
            {'action': 'APPROVE'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'ACTIVE')
        response = client.post(
            API + f'advocacy/{campaign.pk}/decision/',
            {'action': 'REJECT', 'note': 'Evidence insufficient.'},
            format='json')
        self.assertEqual(response.status_code, 200)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'CLOSED')
        self.assertFalse(campaign.is_active)
        self.assertEqual(AdvocacyActivity.objects.filter(
            campaign=campaign).count(), 2)

    def test_decision_denied_for_member_and_bad_action(self):
        campaign = AdvocacyCampaign.objects.create(
            title='Roads Campaign', issue='Roads.', background='Bg.')
        self.assertEqual(self.client_for(self.member).post(
            API + f'advocacy/{campaign.pk}/decision/',
            {'action': 'APPROVE'}, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.director).post(
            API + f'advocacy/{campaign.pk}/decision/',
            {'action': 'FLY'}, format='json').status_code, 400)


class IntelligenceDeskApiTests(StaffApiCase):
    def test_overview_counts_and_member_denial(self):
        # A completed collection run must not break the overview: the
        # cycle-health payload carries plain data, not the model instance.
        from intelligence.models import CollectionRun
        CollectionRun.objects.create(status='COMPLETED')
        response = self.client_for(self.director).get(
            API + 'intelligence/overview/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.data['cycle_health']['last_run']['status'], 'COMPLETED')
        self.assertEqual(set(response.data['desk_counts']),
                         {value for value, _ in DESK_STATES})
        self.assertEqual(self.client_for(self.member).get(
            API + 'intelligence/overview/').status_code, 403)

    def test_items_filters_and_state_names(self):
        item = make_item(self.source, 'Jega school reopening')
        categorise(item)
        item.relevance = 'CONFIRMED'
        item.save(update_fields=['relevance'])
        client = self.client_for(self.director)
        response = client.get(API + 'intelligence/items/')
        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        self.assertEqual(row['relevance'], 'CONFIRMED')
        self.assertEqual(row['relevance_label'], 'Confirmed Kebbi relevance')
        self.assertEqual(row['desk_state'], 'DISCOVERED')
        filtered = client.get(API + 'intelligence/items/?relevance=CONFIRMED')
        self.assertEqual(filtered.data['count'], 1)
        filtered = client.get(API + 'intelligence/items/?relevance=UNCERTAIN')
        self.assertEqual(filtered.data['count'], 0)

    def walk_to_approved(self, client, ref):
        for action in ('TRIAGE', 'BEGIN_VERIFICATION', 'VERIFY', 'APPROVE'):
            response = client.post(
                API + f'intelligence/desk/{ref}/transition/',
                {'action': action}, format='json')
            self.assertEqual(response.status_code, 200, response.content)

    def test_desk_transition_and_convert_creates_draft_without_story_id(self):
        item = make_item(self.source, 'Market fire in Jega',
                         text='A fire damaged stalls at Jega market.')
        categorise(item)
        client = self.client_for(self.director)
        queue = client.get(API + 'intelligence/desk/')
        self.assertEqual(queue.data['count'], 1)
        ref = queue.data['results'][0]['ref']
        self.assertEqual(ref, f'item-{item.pk}')
        detail = client.get(API + f'intelligence/desk/{ref}/')
        self.assertEqual(detail.data['desk_state'], 'DISCOVERED')
        self.walk_to_approved(client, ref)
        detail = client.get(API + f'intelligence/desk/{ref}/')
        self.assertEqual(detail.data['desk_state'], 'APPROVED')
        blocked = client.post(API + f'intelligence/desk/{ref}/convert/',
                              {}, format='json')
        self.assertEqual(blocked.status_code, 400)
        converted = client.post(API + f'intelligence/desk/{ref}/convert/',
                                {'confirm': True}, format='json')
        self.assertEqual(converted.status_code, 201, converted.content)
        self.assertEqual(converted.data['article']['status'], 'DRAFT')
        self.assertFalse(converted.data['article']['story_id'])
        article = Campaign.objects.get(pk=converted.data['article']['id'])
        self.assertEqual(article.status, 'DRAFT')
        self.assertFalse(article.story_id)

    def test_cluster_split_and_merge(self):
        first = make_item(self.source, 'Flood report one')
        second = make_item(self.source, 'Flood report two')
        third = make_item(self.source, 'Flood report three')
        category = categorise(first)
        cluster = EventCluster.objects.create(
            title='Flood reports', category=category, primary_lga=self.jega)
        for item in (first, second, third):
            item.cluster = cluster
            item.save(update_fields=['cluster'])
        client = self.client_for(self.director)
        listing = client.get(API + 'intelligence/clusters/')
        self.assertEqual(listing.data['count'], 1)
        detail = client.get(API + f'intelligence/clusters/{cluster.pk}/')
        self.assertEqual(detail.data['member_count'], 3)
        split = client.post(
            API + f'intelligence/clusters/{cluster.pk}/split/',
            {'items': [third.pk]}, format='json')
        self.assertEqual(split.status_code, 200, split.content)
        third.refresh_from_db()
        self.assertIsNone(third.cluster_id)
        other = EventCluster.objects.create(
            title='Other cluster', category=category, primary_lga=self.jega)
        merged = client.post(
            API + f'intelligence/clusters/{cluster.pk}/merge/',
            {'other_cluster': other.pk}, format='json')
        self.assertEqual(merged.status_code, 200, merged.content)
        other.refresh_from_db()
        self.assertEqual(other.state, 'MERGED')


class IntelligenceAdminApiTests(StaffApiCase):
    def test_sources_create_runs_alias_review_and_lgas(self):
        client = self.client_for(self.director)
        created = client.post(API + 'intelligence/sources/', {
            'name': 'API Created Source', 'kind': 'NEWS',
            'url': 'https://news.example.com/feed.xml', 'feed': True,
            'enabled': False, 'max_items': 3, 'connector_kind': 'RSS',
            'poll_interval_minutes': 30,
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(self.client_for(self.member).post(
            API + 'intelligence/sources/', {}, format='json').status_code, 403)
        runs = client.get(API + 'intelligence/runs/')
        self.assertEqual(runs.status_code, 200)
        alias = GeoAlias.objects.create(
            alias='Jega Town', target_kind='LGA', lga=self.jega,
            created_by=self.director)
        reviewed = client.post(
            API + f'intelligence/aliases/{alias.pk}/review/',
            {'decision': 'APPROVED'}, format='json')
        self.assertEqual(reviewed.status_code, 200)
        alias.refresh_from_db()
        self.assertEqual(alias.status, 'APPROVED')
        lgas = client.get(API + 'intelligence/lgas/')
        self.assertEqual(lgas.status_code, 200)
        slugs = {row['name']: row['slug'] for row in lgas.data['results']}
        self.assertEqual(slugs['Jega'], 'jega')
        detail = client.get(API + 'intelligence/lgas/jega/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['name'], 'Jega')
        self.assertIn('districts', detail.data)

    def test_article_location_tagging(self):
        article = Campaign.objects.create(
            author=self.director, title='Jega Story', slug='jega-story',
            status='PUBLISHED', content='Body.',
            published_at=timezone.now())
        client = self.client_for(self.director)
        tagged = client.post(API + 'intelligence/article-locations/', {
            'article_id': article.pk, 'lga': self.jega.pk,
        }, format='json')
        self.assertEqual(tagged.status_code, 201, tagged.content)
        self.assertEqual(tagged.data['kind'], 'MANUAL')
        listing = client.get(API + 'intelligence/article-locations/')
        self.assertEqual(listing.data['total_links'], 1)

    def test_briefings_generate_detail_and_telegram(self):
        client = self.client_for(self.director)
        generated = client.post(API + 'intelligence/briefings/generate/',
                                {'period': 'DAILY'}, format='json')
        self.assertEqual(generated.status_code, 201, generated.content)
        briefing_id = generated.data['id']
        listing = client.get(API + 'intelligence/briefings/')
        self.assertEqual(listing.data['count'], 1)
        detail = client.get(API + f'intelligence/briefings/{briefing_id}/')
        self.assertEqual(detail.status_code, 200)
        sent = client.post(
            API + f'intelligence/briefings/{briefing_id}/telegram/',
            {}, format='json')
        self.assertEqual(sent.status_code, 200, sent.content)

    def test_alert_rules_and_my_alerts(self):
        client = self.client_for(self.director)
        rules = client.get(API + 'intelligence/alert-rules/')
        self.assertEqual(rules.status_code, 200)
        keys = [row['key'] for row in rules.data['results']]
        self.assertIn('BRIEFING', keys)
        rule_id = rules.data['results'][0]['id']
        updated = client.put(API + f'intelligence/alert-rules/{rule_id}/', {
            'enabled': True, 'channels': ['DASHBOARD'],
            'recipient_capability': 'VIEW_INTELLIGENCE',
            'recipient_emails': '', 'telegram_chat_ids': '',
        }, format='json')
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data['channels'], ['DASHBOARD'])
        alert = Alert.objects.create(
            rule_id=rule_id, kind='SECURITY_VERIFIED', title='Heads up',
            message='Something happened.', dedupe_key='staff-api-alert-1')
        delivery = AlertDelivery.objects.create(
            alert=alert, channel='DASHBOARD',
            recipient=self.director.get_username(), status='SENT')
        mine = client.get(API + 'intelligence/alerts/')
        self.assertEqual(mine.data['unread'], 1)
        read = client.post(API + f'intelligence/alerts/{delivery.pk}/read/',
                           {}, format='json')
        self.assertEqual(read.status_code, 200)
        delivery.refresh_from_db()
        self.assertTrue(delivery.is_read)


class PromiseCandidateApiTests(StaffApiCase):
    def make_candidate(self, quote):
        item = make_item(self.source, 'Promise statement', text=quote)
        return PromiseCandidate.objects.create(
            publication=item, quote=quote, matched_pattern='will build',
            institution_name='Kebbi State Government', lga=self.jega,
            dedupe_key=f'candidate-{PromiseCandidate.objects.count() + 1}')

    def test_confirm_creates_promise(self):
        candidate = self.make_candidate(
            'The government will build a new clinic in Jega.')
        client = self.client_for(self.director)
        listing = client.get(API + 'intelligence/promise-candidates/')
        self.assertEqual(listing.data['count'], 1)
        confirmed = client.post(
            API + f'intelligence/promise-candidates/{candidate.pk}/confirm/',
            {}, format='json')
        self.assertEqual(confirmed.status_code, 201, confirmed.content)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, 'CONFIRMED')
        self.assertIsNotNone(candidate.promise_id)
        promise = Promise.objects.get(pk=candidate.promise_id)
        self.assertEqual(promise.status, 'ANNOUNCED')
        self.assertEqual(confirmed.data['promise']['id'], promise.pk)

    def test_dismiss_requires_reason(self):
        candidate = self.make_candidate('We shall tar the road soon.')
        client = self.client_for(self.director)
        blocked = client.post(
            API + f'intelligence/promise-candidates/{candidate.pk}/dismiss/',
            {}, format='json')
        self.assertEqual(blocked.status_code, 400)
        dismissed = client.post(
            API + f'intelligence/promise-candidates/{candidate.pk}/dismiss/',
            {'reason': 'Not a commitment.'}, format='json')
        self.assertEqual(dismissed.status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, 'DISMISSED')


class SecurityDeskApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        self.item = make_item(self.source, 'Security incident report')
        categorise(self.item, slug='security-public-safety')

    def test_non_holders_get_403(self):
        for user in (self.assistant, self.member, self.audit_lead):
            response = self.client_for(user).get(API + 'intelligence/security/')
            self.assertEqual(response.status_code, 403,
                             f'{user} should not see the security desk')

    def test_holder_flow_restrict_incident_claim_status_redact(self):
        client = self.client_for(self.president)
        desk = client.get(API + 'intelligence/security/')
        self.assertEqual(desk.status_code, 200, desk.content)
        self.assertEqual(desk.data['total_units'], 1)
        ref = f'item-{self.item.pk}'
        detail = client.get(API + f'intelligence/security/{ref}/')
        self.assertEqual(detail.status_code, 200)
        transitioned = client.post(
            API + f'intelligence/security/{ref}/transition/',
            {'action': 'RESTRICT'}, format='json')
        self.assertEqual(transitioned.status_code, 200, transitioned.content)
        self.assertEqual(transitioned.data['desk_state'], 'RESTRICTED')
        created = client.post(API + 'intelligence/security/incidents/', {
            'title': 'Incident in Jega', 'lga': self.jega.pk,
            'location_text': 'Jega town',
            'working_notes': 'Notes with a sensitive passage inside.',
            'occurred_at': '2026-11-20T09:00',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        incident_id = created.data['id']
        claim = client.post(
            API + f'intelligence/security/incidents/{incident_id}/claim/',
            {'label': 'People displaced', 'count': 12,
             'source_name': 'Community leader', 'source_url': ''},
            format='json')
        self.assertEqual(claim.status_code, 201, claim.content)
        self.assertIn('Community leader', claim.data['attribution'])
        self.assertIn('12', claim.data['attribution'])
        detail = client.get(
            API + f'intelligence/security/incidents/{incident_id}/')
        self.assertEqual(detail.data['claims'][0]['count'], 12)
        self.assertTrue(detail.data['claims_lines'])
        statused = client.post(
            API + f'intelligence/security/incidents/{incident_id}/status/',
            {'status': 'CLOSED'}, format='json')
        self.assertEqual(statused.data['status'], 'CLOSED')
        redacted = client.post(
            API + f'intelligence/security/incidents/{incident_id}/redact/',
            {'passage': 'a sensitive passage'}, format='json')
        self.assertEqual(redacted.status_code, 200, redacted.content)
        incident = SecurityIncident.objects.get(pk=incident_id)
        self.assertNotIn('a sensitive passage', incident.working_notes)
        self.assertIn('[REDACTED]', incident.working_notes)


class ProjectApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        self.project = project_service.create_project(
            self.director, title='Jega Clinic', description='A clinic.',
            category='NEW_BUILD', lga=self.jega)

    def test_manage_detail_milestone_evidence_and_verified_guard(self):
        client = self.client_for(self.director)
        detail = client.get(
            API + f'intelligence/projects/{self.project.pk}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.data['project_code'], self.project.project_code)
        milestone = client.post(
            API + f'intelligence/projects/{self.project.pk}/milestone/',
            {'date': '2026-11-20', 'title': 'Foundation laid',
             'body': 'Work started.'}, format='json')
        self.assertEqual(milestone.status_code, 201, milestone.content)
        evidence = client.post(
            API + f'intelligence/projects/{self.project.pk}/evidence/',
            {'kind': 'FIELD_INSPECTION', 'title': 'Site visit',
             'url': '', 'verification_state': 'DOCUMENTED',
             'is_public': False}, format='json')
        self.assertEqual(evidence.status_code, 201, evidence.content)
        # The person who filed the evidence cannot verify completion.
        blocked = client.post(
            API + f'intelligence/projects/{self.project.pk}/status/',
            {'status': 'COMPLETED_VERIFIED'}, format='json')
        self.assertEqual(blocked.status_code, 400, blocked.content)
        # A different verifier (Audit director) can.
        verified = self.client_for(self.audit_lead).post(
            API + f'intelligence/projects/{self.project.pk}/status/',
            {'status': 'COMPLETED_VERIFIED'}, format='json')
        self.assertEqual(verified.status_code, 200, verified.content)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'COMPLETED_VERIFIED')
        listing = client.get(
            API + f'intelligence/projects/{self.project.pk}/evidence/')
        self.assertEqual(len(listing.data['results']), 1)

    def test_map_rows(self):
        response = self.client_for(self.director).get(
            API + 'intelligence/map/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data['results']), 21)
        jega = [r for r in response.data['results'] if r['name'] == 'Jega'][0]
        self.assertEqual(jega['pj_tracked'], 1)


class StoryDeskApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        self.institution = Institution.objects.create(
            name='Kebbi State Government', kind='GOVERNMENT')

    def test_promise_desk_create_patch_update_status(self):
        client = self.client_for(self.director)
        created = client.post(API + 'story-intelligence/promises/', {
            'institution': self.institution.pk,
            'title': 'Build Jega clinic',
            'description': 'A new clinic for Jega.',
            'announced_on': '2026-11-01', 'sector': 'HEALTH',
            'lga': self.jega.pk, 'stories': [],
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        promise_id = created.data['id']
        self.assertEqual(created.data['status'], 'ANNOUNCED')
        patched = client.patch(
            API + f'story-intelligence/promises/{promise_id}/desk/',
            {'title': 'Build Jega clinic (phase 1)'}, format='json')
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.data['title'], 'Build Jega clinic (phase 1)')
        updated = client.post(
            API + f'story-intelligence/promises/{promise_id}/updates/',
            {'update_date': '2026-11-20', 'title': 'Work started',
             'body': 'Foundation laid.', 'evidence_title': '',
             'evidence_url': '', 'new_status': 'IN_PROGRESS'},
            format='json')
        self.assertEqual(updated.status_code, 201, updated.content)
        self.assertEqual(updated.data['promise_status'], 'IN_PROGRESS')
        desk = client.get(API + 'story-intelligence/promises/desk/')
        self.assertEqual(desk.data['count'], 1)
        detail = client.get(
            API + f'story-intelligence/promises/{promise_id}/desk/')
        self.assertEqual(detail.data['status'], 'IN_PROGRESS')

    def test_story_desk_claim_status_and_radar(self):
        article = Campaign.objects.create(
            author=self.director, title='Clinic Story', slug='clinic-story',
            status='PUBLISHED', content='Body.',
            published_at=timezone.now())
        claim = Claim.objects.create(
            article=article, text='The clinic is complete.',
            status='DEVELOPING', noted_by=self.director)
        client = self.client_for(self.director)
        desk = client.get(
            API + f'story-intelligence/stories/{article.pk}/desk/')
        self.assertEqual(desk.status_code, 200, desk.content)
        self.assertEqual(desk.data['claims'][0]['status'], 'DEVELOPING')
        changed = client.post(
            API + f'story-intelligence/stories/{article.pk}/desk/',
            {'action': 'claim_status', 'claim_id': claim.pk,
             'status': 'CONFIRMED', 'reason': 'Site visit.'}, format='json')
        self.assertEqual(changed.status_code, 200, changed.content)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'CONFIRMED')
        radar = client.get(API + 'story-intelligence/radar/')
        self.assertEqual(radar.status_code, 200)
        self.assertIn('reports', radar.data)

    def test_redaction_endpoint_uses_service_and_mocks_cloudinary(self):
        article = Campaign.objects.create(
            author=self.director, title='Sensitive Story',
            slug='sensitive-story', status='PUBLISHED',
            content='Body naming a private person.',
            published_at=timezone.now())
        evidence = EvidenceRecord.objects.create(
            article=article, title='Leaked document', kind='DOCUMENT',
            file=SimpleUploadedFile('leak.txt', b'secret-bytes'),
            added_by=self.director)
        client = self.client_for(self.director)
        with mock.patch('cloudinary.uploader.destroy',
                        return_value={'result': 'ok'}) as destroy:
            response = client.post(API + 'story-intelligence/redact/', {
                'target_type': 'evidence', 'target_id': evidence.pk,
                'reason_category': 'PERSONAL_DATA',
            }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(destroy.call_count, 1)
        self.assertEqual(response.data['file_removal'], 'ok')
        evidence.refresh_from_db()
        self.assertFalse(evidence.file)
        # Article-level shorthand: {article_id, reason}.
        claim = Claim.objects.create(
            article=article, text='A private name appears here.',
            status='DEVELOPING', noted_by=self.director)
        response = client.post(API + 'story-intelligence/redact/', {
            'target_type': 'claim', 'target_id': claim.pk,
            'reason': 'SAFETY',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        claim.refresh_from_db()
        self.assertEqual(claim.text, REDACTION_MARKER)
        denied = self.client_for(self.member).post(
            API + 'story-intelligence/redact/', {
                'target_type': 'claim', 'target_id': claim.pk,
                'reason_category': 'SAFETY',
            }, format='json')
        self.assertEqual(denied.status_code, 403)


class EditorialApiTests(StaffApiCase):
    def test_overview_item_and_source_approve(self):
        source = EditorialSource.objects.create(
            name='Editorial API Source', kind='NEWS',
            url='https://news.example.com/rss.xml', feed=True,
            enabled=False, max_items=3)
        item = EditorialItem.objects.create(
            key='staff-api-item-1', kind='NEWS', state='REVIEW',
            title='Draft story', source=source,
            original={'title': 'Draft story'},
            draft={'title': 'Draft story', 'body': 'Body.'})
        client = self.client_for(self.director)
        overview = client.get(API + 'editorial/')
        self.assertEqual(overview.status_code, 200, overview.content)
        self.assertEqual(overview.data['items_by_state']['REVIEW'], 1)
        detail = client.get(API + f'editorial/{item.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['state'], 'REVIEW')
        sources = client.get(API + 'editorial/sources/')
        self.assertEqual(sources.status_code, 200)
        approved = client.post(
            API + f'editorial/sources/{source.pk}/approve/', {},
            format='json')
        self.assertEqual(approved.status_code, 200, approved.content)
        source.refresh_from_db()
        self.assertTrue(source.enabled)
        self.assertTrue(EditorialAudit.objects.filter(
            action='SOURCE_SAVED',
            detail__source_id=source.pk).exists())
        self.assertEqual(self.client_for(self.member).get(
            API + 'editorial/sources/').status_code, 403)


class IctApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        IctAdminAssignment.objects.create(pk=1, user=self.director)
        self.superuser = User.objects.create_user(
            username='staff_root', phone='staff_root', is_superuser=True,
            is_staff=True)

    def test_holder_and_superuser_access_all_sections(self):
        for user in (self.director, self.superuser):
            client = self.client_for(user)
            for section in ('overview', 'members', 'leadership',
                            'intelligence', 'telegram'):
                response = client.get(API + f'ict/{section}/')
                self.assertEqual(response.status_code, 200,
                                 f'{user} ict/{section}: {response.content}')
        overview = self.client_for(self.director).get(API + 'ict/overview/')
        self.assertEqual(overview.data['assignment']['holder']['username'],
                         'staff_director')
        self.assertGreaterEqual(overview.data['stats']['total_members'], 1)

    def test_non_holders_denied_and_post_is_405(self):
        for user in (self.president, self.member, self.assistant):
            response = self.client_for(user).get(API + 'ict/overview/')
            self.assertEqual(response.status_code, 403,
                             f'{user} must not open the ICT console')
        response = self.client_for(self.director).post(
            API + 'ict/overview/', {}, format='json')
        self.assertEqual(response.status_code, 405)
