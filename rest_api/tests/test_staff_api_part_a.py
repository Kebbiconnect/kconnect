"""Staff API Part A: the endpoints added for the next Android screens.

Each group mirrors a web view — security working copy, printable ID
tag, project-from-desk-unit, editorial source create/edit, cross-event
attendance logs, district/community create and institution create —
and pins the web gate, the web form/service behaviour and the audit
rows the web writes.
"""
from django.utils import timezone
from rest_framework.test import APIClient

from editorial.models import Audit as EditorialAudit
from editorial.models import Source as EditorialSource
from editorial.tests.helpers import make_user
from events.models import Event, EventAttendance
from intelligence.models import (
    Community, District, EventCluster, IntelligenceAudit, Project,
)
from leadership.models import Ward
from story_intelligence.models import Institution, StoryAudit

from .test_staff_api import StaffApiCase, categorise, make_item

API = '/api/v1/'


class SecurityWorkingCopyApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        self.item = make_item(self.source, 'Security incident report')
        categorise(self.item, slug='security-public-safety')
        self.url = API + f'intelligence/security/item/{self.item.pk}/working-copy/'

    def test_get_empty_working_copy_and_view_audit(self):
        response = self.client_for(self.president).get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data['has_working_copy'])
        self.assertEqual(response.data['working_text'], '')
        self.assertEqual(response.data['passages'], [])
        self.assertTrue(IntelligenceAudit.objects.filter(
            actor=self.president, action='SECURITY_VIEW',
            target_type='RawPublication', target_id=self.item.pk).exists())

    def test_non_holders_denied_get_and_post(self):
        for user in (self.assistant, self.member, self.audit_lead):
            client = self.client_for(user)
            self.assertEqual(client.get(self.url).status_code, 403)
            self.assertEqual(client.post(
                self.url, {'action': 'prepare'}, format='json').status_code, 403)

    def test_prepare_then_redact_blanks_only_working_copy(self):
        client = self.client_for(self.director)
        prepared = client.post(self.url, {'action': 'prepare'}, format='json')
        self.assertEqual(prepared.status_code, 200, prepared.content)
        self.assertTrue(prepared.data['has_working_copy'])
        self.assertIn('Body text from Jega.', prepared.data['working_text'])
        self.assertEqual(prepared.data['passages'],
                         prepared.data['working_text'].split('\n\n'))
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='SECURITY_WORKING_COPY',
            target_id=self.item.pk).exists())
        redacted = client.post(self.url, {
            'action': 'redact', 'passage': 'Body text from Jega.',
        }, format='json')
        self.assertEqual(redacted.status_code, 200, redacted.content)
        self.assertEqual(redacted.data['redacted_occurrences'], 1)
        self.assertNotIn('Body text from Jega.', redacted.data['working_text'])
        self.assertIn('[REDACTED]', redacted.data['working_text'])
        # The original evidence record is never altered.
        self.item.refresh_from_db()
        self.assertEqual(self.item.text, 'Body text from Jega.')
        # The redaction audit records counts/lengths only, never text.
        audit = IntelligenceAudit.objects.get(
            action='SECURITY_REDACTION', target_id=self.item.pk)
        self.assertEqual(audit.detail['occurrences'], 1)
        self.assertEqual(audit.detail['passage_length'],
                         len('Body text from Jega.'))
        self.assertNotIn('Body text', str(audit.detail))

    def test_redact_unknown_passage_and_unknown_action_are_400(self):
        client = self.client_for(self.director)
        client.post(self.url, {'action': 'prepare'}, format='json')
        self.assertEqual(client.post(self.url, {
            'action': 'redact', 'passage': 'Not in the copy.',
        }, format='json').status_code, 400)
        self.assertEqual(client.post(self.url, {
            'action': 'shred',
        }, format='json').status_code, 400)

    def test_non_restricted_unit_is_404(self):
        plain = make_item(self.source, 'School reopening')
        categorise(plain, slug='education')
        url = API + f'intelligence/security/item/{plain.pk}/working-copy/'
        client = self.client_for(self.director)
        self.assertEqual(client.get(url).status_code, 404)
        self.assertEqual(client.post(
            url, {'action': 'prepare'}, format='json').status_code, 404)


class IdTagApiTests(StaffApiCase):
    def test_own_tag_returns_web_pdf(self):
        response = self.client_for(self.director).get(API + 'account/id-tag/')
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('staff_director_id_card.pdf',
                      response['Content-Disposition'])
        body = b''.join(response.streaming_content) \
            if response.streaming else response.content
        self.assertTrue(body.startswith(b'%PDF'))
        # Two card pages (front + back), excluding the /Pages root.
        import re
        self.assertEqual(len(re.findall(rb'/Type\s*/Page(?!s)', body)), 2)

    def test_general_member_blocked_like_web(self):
        response = self.client_for(self.member).get(API + 'account/id-tag/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_blocked(self):
        self.assertEqual(
            APIClient().get(API + 'account/id-tag/').status_code, 401)


class ProjectFromUnitApiTests(StaffApiCase):
    def verified_item(self):
        item = make_item(self.source, 'Jega road repairs flagged off')
        categorise(item, slug='infrastructure-roads')
        item.desk_state = 'VERIFIED'
        item.save(update_fields=['desk_state'])
        return item

    def test_create_from_item_stores_provenance(self):
        item = self.verified_item()
        response = self.client_for(self.director).post(
            API + f'intelligence/projects/from-item/{item.pk}/',
            {'category': 'ROAD'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(source_publication=item)
        self.assertEqual(response.data['id'], project.pk)
        self.assertEqual(response.data['project_code'], project.project_code)
        # Prefill came from the unit's own records, as the web form shows.
        self.assertEqual(project.title, item.title)

    def test_create_from_cluster_stores_provenance(self):
        item = self.verified_item()
        category = item.category_links.get(is_primary=True).category
        cluster = EventCluster.objects.create(
            title=item.title, category=category, primary_lga=self.jega,
            desk_state='APPROVED')
        item.cluster = cluster
        item.save(update_fields=['cluster'])
        response = self.client_for(self.director).post(
            API + f'intelligence/projects/from-cluster/{cluster.pk}/',
            {'category': 'ROAD', 'title': 'Jega Road Repairs'},
            format='json')
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(source_cluster=cluster)
        self.assertEqual(project.title, 'Jega Road Repairs')

    def test_unverified_unit_refused(self):
        item = make_item(self.source, 'Unverified report')
        categorise(item, slug='infrastructure-roads')
        response = self.client_for(self.director).post(
            API + f'intelligence/projects/from-item/{item.pk}/',
            {'category': 'ROAD'}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Project.objects.exists())

    def test_member_denied(self):
        item = self.verified_item()
        response = self.client_for(self.member).post(
            API + f'intelligence/projects/from-item/{item.pk}/',
            {'category': 'ROAD'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.exists())


class EditorialSourceCreateEditApiTests(StaffApiCase):
    payload = {
        'name': 'Part A Feed', 'kind': 'NEWS',
        'url': 'https://example.com/feed.xml', 'feed': True,
        'allowed_hosts': '', 'keywords': 'Kebbi', 'max_items': 3,
        'enabled': True,
    }

    def test_manager_creates_source_with_audit(self):
        response = self.client_for(self.director).post(
            API + 'editorial/sources/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        source = EditorialSource.objects.get(name='Part A Feed')
        self.assertTrue(source.enabled)
        self.assertTrue(EditorialAudit.objects.filter(
            action='SOURCE_SAVED', detail__source_id=source.pk).exists())

    def test_non_managers_denied_create(self):
        # The web gate is the editorial manager check: the Director of
        # Media only — not even the President.
        for user in (self.president, self.member, self.assistant):
            response = self.client_for(user).post(
                API + 'editorial/sources/', self.payload, format='json')
            self.assertEqual(response.status_code, 403,
                             f'{user} must not create editorial sources')
        self.assertFalse(EditorialSource.objects.filter(
            name='Part A Feed').exists())

    def test_http_url_rejected_like_web_form(self):
        response = self.client_for(self.director).post(
            API + 'editorial/sources/',
            {**self.payload, 'url': 'http://example.com/feed.xml'},
            format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(EditorialSource.objects.filter(
            name='Part A Feed').exists())

    def test_manager_edits_source_with_put(self):
        source = EditorialSource.objects.create(
            name='Old Name', kind='NEWS',
            url='https://news.example.com/rss.xml', feed=True,
            enabled=False, max_items=3)
        response = self.client_for(self.director).put(
            API + f'editorial/sources/{source.pk}/',
            {**self.payload, 'name': 'New Name'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        source.refresh_from_db()
        self.assertEqual(source.name, 'New Name')
        self.assertTrue(source.enabled)
        self.assertTrue(EditorialAudit.objects.filter(
            action='SOURCE_SAVED', detail__source_id=source.pk).exists())
        denied = self.client_for(self.president).put(
            API + f'editorial/sources/{source.pk}/', self.payload,
            format='json')
        self.assertEqual(denied.status_code, 403)


class AttendanceLogsApiTests(StaffApiCase):
    def setUp(self):
        super().setUp()
        self.event = Event.objects.create(
            title='State Meeting', description='Monthly meeting.',
            location='Birnin Kebbi', start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(hours=2),
            created_by=self.director)
        self.other_event = Event.objects.create(
            title='Zonal Meeting', description='Zonal meeting.',
            location='Argungu', start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(hours=1),
            created_by=self.director)

    def test_logs_span_events_present_only_most_recent_first(self):
        EventAttendance.objects.create(
            event=self.event, attendee=self.director, present=True,
            recorded_by=self.president)
        latest = EventAttendance.objects.create(
            event=self.other_event, attendee=self.president, present=True,
            recorded_by=self.director)
        EventAttendance.objects.create(
            event=self.event, attendee=self.member, present=False,
            recorded_by=self.director)
        response = self.client_for(self.member).get(
            API + 'events/attendance/logs/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['count'], 2)
        first = response.data['results'][0]
        self.assertEqual(first['id'], latest.pk)
        self.assertEqual(first['event']['title'], 'Zonal Meeting')
        self.assertEqual(first['attendee']['username'], 'staff_president')
        self.assertTrue(first['present'])

    def test_unverified_member_denied(self):
        pending = make_user('parta_pending', title=None, role='GENERAL',
                            status='PENDING')
        response = self.client_for(pending).get(
            API + 'events/attendance/logs/')
        self.assertEqual(response.status_code, 403)


class DistrictCommunityApiTests(StaffApiCase):
    def test_district_create_with_audit(self):
        response = self.client_for(self.director).post(
            API + 'intelligence/lgas/jega/districts/',
            {'name': 'Jega Central'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        district = District.objects.get(name='Jega Central')
        self.assertEqual(district.lga, self.jega)
        self.assertEqual(response.data['lga'], self.jega.pk)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='DISTRICT_CREATED', target_id=district.pk).exists())

    def test_district_create_denied_and_unknown_lga(self):
        self.assertEqual(self.client_for(self.member).post(
            API + 'intelligence/lgas/jega/districts/',
            {'name': 'Nope'}, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.director).post(
            API + 'intelligence/lgas/no-such-lga/districts/',
            {'name': 'Nope'}, format='json').status_code, 404)
        self.assertFalse(District.objects.filter(name='Nope').exists())

    def test_community_create_scoped_to_lga(self):
        ward = Ward.objects.create(name='Jega Ward One', lga=self.jega)
        district = District.objects.create(name='Jega District', lga=self.jega)
        response = self.client_for(self.director).post(
            API + 'intelligence/lgas/jega/communities/',
            {'name': 'Tunga', 'ward': ward.pk, 'district': district.pk},
            format='json')
        self.assertEqual(response.status_code, 201, response.content)
        community = Community.objects.get(name='Tunga')
        self.assertEqual(community.lga, self.jega)
        self.assertEqual(community.ward, ward)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='COMMUNITY_CREATED', target_id=community.pk).exists())

    def test_community_rejects_ward_from_another_lga(self):
        from leadership.models import LGA
        argungu = LGA.objects.get(name='Argungu')
        foreign_ward = Ward.objects.create(name='Argungu Ward', lga=argungu)
        response = self.client_for(self.director).post(
            API + 'intelligence/lgas/jega/communities/',
            {'name': 'Bad Link', 'ward': foreign_ward.pk}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Community.objects.filter(name='Bad Link').exists())

    def test_community_create_denied_for_member(self):
        self.assertEqual(self.client_for(self.member).post(
            API + 'intelligence/lgas/jega/communities/',
            {'name': 'Nope'}, format='json').status_code, 403)


class InstitutionCreateApiTests(StaffApiCase):
    def test_create_with_story_audit(self):
        response = self.client_for(self.director).post(
            API + 'story-intelligence/promises/institutions/',
            {'name': 'Kebbi State Ministry of Health', 'kind': 'MINISTRY',
             'contact_note': '', 'notes': ''}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        institution = Institution.objects.get(
            name='Kebbi State Ministry of Health')
        self.assertEqual(response.data['kind'], 'MINISTRY')
        self.assertTrue(StoryAudit.objects.filter(
            action='INSTITUTION_ADDED', target_type='institution',
            target_id=institution.pk).exists())

    def test_denied_without_manage_promises(self):
        for user in (self.member, self.audit_lead):
            response = self.client_for(user).post(
                API + 'story-intelligence/promises/institutions/',
                {'name': 'Nope Authority', 'kind': 'AGENCY'},
                format='json')
            self.assertEqual(response.status_code, 403,
                             f'{user} must not add institutions')
        self.assertFalse(Institution.objects.filter(
            name='Nope Authority').exists())

    def test_duplicate_name_rejected_by_form(self):
        Institution.objects.create(name='Existing Authority', kind='AGENCY')
        response = self.client_for(self.director).post(
            API + 'story-intelligence/promises/institutions/',
            {'name': 'Existing Authority', 'kind': 'AGENCY'},
            format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            Institution.objects.filter(name='Existing Authority').count(), 1)
