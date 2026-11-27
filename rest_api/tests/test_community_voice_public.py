"""Public Community Voice endpoint (GET /api/v1/civic/community-voice/).

Root fix for item 5: the app called GET community-reports/ — the
staff review queue gated on REVIEW_COMMUNITY_REPORTS — so ordinary
users always failed. The web page /civic/community-voice/
(core.views.community_voice) is public and shows only concerns a
reviewer explicitly published to Community Voice
(``published_to_voice=True``, D-08), with reporter name/phone never
rendered. This endpoint mirrors that page exactly.

These tests pin: anonymous access, web-visible-only filtering,
the privacy boundary (no reporter/internal keys in the payload),
and the category/location fields the app renders.
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import CommunityReport
from editorial.tests.helpers import geo

API = '/api/v1/'
URL = API + 'civic/community-voice/'

PRIVATE_KEYS = ('reporter_name', 'reporter_phone', 'submitted_by',
                'internal_notes')


class CommunityVoicePublicTests(TestCase):
    def setUp(self):
        self.zone, self.lga, self.ward = geo()
        self.client = APIClient()

    def make_report(self, **overrides):
        data = {
            'reporter_name': 'Private Person',
            'reporter_phone': '08000000000',
            'lga': self.lga, 'ward': self.ward, 'zone': self.zone,
            'location_details': 'Near the market',
            'category': 'HEALTH',
            'what_happened': 'The clinic roof leaks.',
            'who_was_involved': 'Clinic staff and patients',
            'why_is_it_important': 'Patients get wet when it rains.',
            'internal_notes': 'Internal only — never public.',
        }
        data.update(overrides)
        return CommunityReport.objects.create(**data)

    def publish(self, report):
        """The reviewer decision the web page keys on (D-08)."""
        report.published_to_voice = True
        report.voice_published_at = timezone.now()
        report.save(update_fields=['published_to_voice',
                                   'voice_published_at'])
        return report

    def test_anonymous_get_returns_200(self):
        self.publish(self.make_report(status='APPROVED',
                                      info_status='CONFIRMED'))
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)

    def test_only_web_visible_approved_reports_appear(self):
        approved = self.publish(self.make_report(
            status='APPROVED', info_status='CONFIRMED'))
        self.make_report(status='PENDING')
        self.make_report(status='REJECTED')
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [approved.pk])

    def test_approved_but_not_published_to_voice_is_hidden(self):
        # Mirrors the web view exactly: newsroom approval alone does
        # not put a concern on Community Voice; the reviewer must
        # explicitly publish it there (published_to_voice).
        self.make_report(status='APPROVED', info_status='CONFIRMED')
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['results'], [])

    def test_payload_has_no_reporter_or_internal_keys(self):
        self.publish(self.make_report(status='APPROVED',
                                      info_status='VERIFIED'))
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        row = response.data['results'][0]
        for key in PRIVATE_KEYS:
            self.assertNotIn(key, row)
        # The private values must not leak under any other key either.
        rendered = str(row)
        self.assertNotIn('Private Person', rendered)
        self.assertNotIn('08000000000', rendered)
        self.assertNotIn('Internal only', rendered)

    def test_category_and_location_fields_present(self):
        report = self.publish(self.make_report(
            status='APPROVED', info_status='CONFIRMED'))
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        row = response.data['results'][0]
        self.assertEqual(row['id'], report.pk)
        self.assertEqual(row['category'], 'HEALTH')
        self.assertEqual(row['category_label'], 'Health')
        self.assertEqual(row['lga'], self.lga.pk)
        self.assertEqual(row['lga_name'], self.lga.name)
        self.assertEqual(row['ward'], self.ward.pk)
        self.assertEqual(row['ward_name'], self.ward.name)
        self.assertEqual(row['location_details'], 'Near the market')
        self.assertEqual(row['what_happened'], 'The clinic roof leaks.')
        self.assertEqual(row['who_was_involved'],
                         'Clinic staff and patients')
        self.assertEqual(row['why_is_it_important'],
                         'Patients get wet when it rains.')
        self.assertEqual(row['status'], 'APPROVED')
        self.assertEqual(row['info_status'], 'CONFIRMED')
        self.assertIn('evidence_image', row)
        self.assertIn('evidence_video', row)
        self.assertIn('created_at', row)

    def test_empty_when_nothing_published(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])
