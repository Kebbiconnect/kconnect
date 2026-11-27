"""Part B: data behind app screens 53, 81, 118, 123 and 177.

- FAQ categories extracted verbatim from core/templates/core/faq.html.
- Announcement read receipts (staff.AnnouncementRead).
- Legal opinion drafts (staff.LegalOpinionDraft).
- Event audience (events.Event.audience).
- Alert rule creation (intelligence.AlertRule, one row per kind).
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import FAQ
from editorial.tests.helpers import general_member, make_user, media_director
from events.models import Event
from intelligence.models import ALERT_RULES, AlertRule, IntelligenceAudit
from staff.models import Announcement, AnnouncementRead, DisciplinaryAction, LegalOpinionDraft

API = '/api/v1/'


class FaqCategoryTests(TestCase):
    # (question, expected data-category slug) — verbatim from the
    # hard-coded cards in core/templates/core/faq.html.
    TEMPLATE_ITEMS = [
        ('What is the Kebbi Progressive Youth Network (KPN)?', 'about'),
        ('Is KPN a political organization?', 'about'),
        ('How does KPN fund its activities?', 'about'),
        ('Who can join KPN?', 'membership'),
        ('What are the responsibilities of a member?', 'membership'),
        ('Can I lose my membership?', 'membership'),
        ('How is KPN structured?', 'leadership'),
        ('How does KPN gather community reports?', 'reporting'),
        ('How is information classified before publication?', 'reporting'),
    ]

    def setUp(self):
        self.client = APIClient()
        for i, (question, _cat) in enumerate(self.TEMPLATE_ITEMS):
            FAQ.objects.create(question=question, answer=f'Answer {i}.', order=i)

    def test_payload_carries_exact_template_categories(self):
        response = self.client.get(API + 'content/faq/')
        self.assertEqual(response.status_code, 200, response.content)
        by_question = {row['question']: row['category']
                       for row in response.data['results']}
        for question, category in self.TEMPLATE_ITEMS:
            self.assertEqual(by_question[question], category, question)

    def test_uncategorised_question_uses_template_all_default(self):
        FAQ.objects.create(question='A brand new staff question?', answer='New.')
        response = self.client.get(API + 'content/faq/')
        by_question = {row['question']: row['category']
                       for row in response.data['results']}
        self.assertEqual(by_question['A brand new staff question?'], 'all')

    def test_category_labels_match_template_pills_verbatim(self):
        from core.faq_categories import FAQ_CATEGORY_LABELS
        self.assertEqual(FAQ_CATEGORY_LABELS, {
            'all': 'All', 'about': 'About KPN', 'membership': 'Membership',
            'leadership': 'Leadership', 'reporting': 'Reporting',
            'opportunities': 'Opportunities', 'trackers': 'Trackers',
            'support': 'Support & Contact'})


class AnnouncementReadTests(TestCase):
    def setUp(self):
        self.creator = make_user('pb_ann_creator', title='President')
        self.member = general_member('pb_ann_member')
        self.other = general_member('pb_ann_other')
        self.announcement = Announcement.objects.create(
            title='State-wide notice', content='Body.', scope='GENERAL',
            priority='NORMAL', created_by=self.creator)
        self.client = APIClient()

    def received_row(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(API + 'announcements/received/')
        self.assertEqual(response.status_code, 200, response.content)
        rows = [r for r in response.data['results'] if r['id'] == self.announcement.pk]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_unread_then_read_then_other_user_unaffected(self):
        self.assertFalse(self.received_row(self.member)['is_read'])
        self.client.force_authenticate(self.member)
        first = self.client.post(
            API + f'announcements/{self.announcement.pk}/read/', {}, format='json')
        self.assertEqual(first.status_code, 201, first.content)
        self.assertTrue(first.data['is_read'])
        self.assertTrue(AnnouncementRead.objects.filter(
            announcement=self.announcement, user=self.member).exists())
        # Idempotent: a second POST succeeds and keeps one receipt.
        second = self.client.post(
            API + f'announcements/{self.announcement.pk}/read/', {}, format='json')
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(AnnouncementRead.objects.filter(
            announcement=self.announcement, user=self.member).count(), 1)
        self.assertTrue(self.received_row(self.member)['is_read'])
        # Another recipient is unaffected.
        self.assertFalse(self.received_row(self.other)['is_read'])

    def test_marking_an_invisible_announcement_is_404(self):
        hidden = Announcement.objects.create(
            title='Ward only', content='Body.', scope='WARD',
            priority='NORMAL', created_by=self.creator,
            target_ward=self.other.ward)
        self.client.force_authenticate(self.member)
        # member and other share the helper geography, so use a scope
        # the member cannot receive and did not create: STATE scope is
        # only for verified STATE-tier seat holders.
        state_only = Announcement.objects.create(
            title='State only', content='Body.', scope='STATE',
            priority='NORMAL', created_by=self.creator)
        response = self.client.post(
            API + f'announcements/{state_only.pk}/read/', {}, format='json')
        self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(AnnouncementRead.objects.filter(
            announcement=state_only, user=self.member).exists())
        del hidden


class LegalOpinionDraftTests(TestCase):
    def setUp(self):
        self.legal = make_user(
            'pb_legal', title='Director of Legal Affairs & Ethics')
        self.president = make_user('pb_president', title='President')
        self.target = general_member('pb_target')
        self.action = DisciplinaryAction.objects.create(
            user=self.target, action_type='DISMISSAL',
            reason='Test case.', issued_by=self.president)
        self.client = APIClient()
        self.client.force_authenticate(self.legal)
        self.draft_url = API + f'discipline/{self.action.pk}/legal-opinion/draft/'
        self.final_url = API + f'discipline/{self.action.pk}/legal-opinion/'

    def test_save_fetch_replace_and_final_submit_clears_draft(self):
        missing = self.client.get(self.draft_url)
        self.assertEqual(missing.status_code, 404, missing.content)
        saved = self.client.put(self.draft_url, {
            'legal_opinion': 'Draft finding: supports action.',
            'legal_approved': True}, format='json')
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.data['legal_opinion'],
                         'Draft finding: supports action.')
        self.assertTrue(saved.data['legal_approved'])
        fetched = self.client.get(self.draft_url)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data['legal_opinion'],
                         'Draft finding: supports action.')
        # Saving again replaces the one draft for (author, case).
        self.client.put(self.draft_url, {
            'legal_opinion': 'Revised draft.', 'legal_approved': False},
            format='json')
        self.assertEqual(LegalOpinionDraft.objects.filter(
            action=self.action, author=self.legal).count(), 1)
        fetched = self.client.get(self.draft_url)
        self.assertEqual(fetched.data['legal_opinion'], 'Revised draft.')
        self.assertFalse(fetched.data['legal_approved'])
        # Final submission (unchanged endpoint) clears the draft.
        final = self.client.post(self.final_url, {
            'legal_opinion': 'Final opinion.', 'legal_approved': True},
            format='json')
        self.assertEqual(final.status_code, 200, final.content)
        self.assertEqual(final.data['legal_opinion'], 'Final opinion.')
        self.assertFalse(LegalOpinionDraft.objects.filter(
            action=self.action, author=self.legal).exists())
        self.assertEqual(self.client.get(self.draft_url).status_code, 404)

    def test_draft_gate_denies_non_legal_user(self):
        self.client.force_authenticate(self.target)
        self.assertEqual(self.client.get(self.draft_url).status_code, 403)
        denied = self.client.put(self.draft_url, {
            'legal_opinion': 'Nope.', 'legal_approved': False}, format='json')
        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertFalse(LegalOpinionDraft.objects.exists())


class EventAudienceTests(TestCase):
    def setUp(self):
        self.manager = make_user(
            'pb_events', title='Director of Programmes & Events')
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        self.payload = {
            'title': 'Youth Day gathering', 'description': 'Fixture.',
            'location': 'Birnin Kebbi',
            'start_date': now.isoformat(),
            'end_date': (now + timedelta(hours=2)).isoformat()}

    def test_create_with_audience_round_trips(self):
        created = self.client.post(
            API + 'events/', {**self.payload, 'audience': 'All members'},
            format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data['audience'], 'All members')
        self.assertEqual(Event.objects.get(pk=created.data['id']).audience,
                         'All members')
        detail = self.client.get(API + f"events/{created.data['id']}/")
        self.assertEqual(detail.data['audience'], 'All members')
        updated = self.client.patch(
            API + f"events/{created.data['id']}/",
            {'audience': 'Ward leaders only'}, format='json')
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data['audience'], 'Ward leaders only')

    def test_create_without_audience_still_works(self):
        created = self.client.post(API + 'events/', self.payload, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data['audience'], '')


class AlertRuleCreateTests(TestCase):
    def setUp(self):
        self.director = media_director('pb_director')
        self.member = general_member('pb_member')
        self.client = APIClient()
        self.url = API + 'intelligence/alert-rules/'
        self.payload = {
            'enabled': True, 'channels': ['DASHBOARD', 'TELEGRAM'],
            'recipient_capability': 'MANAGE_SOURCES',
            'recipient_emails': 'alerts@example.invalid',
            'telegram_chat_ids': '12345'}

    def test_create_for_unconfigured_kind(self):
        self.assertFalse(AlertRule.objects.exists())
        self.client.force_authenticate(self.director)
        created = self.client.post(
            self.url, {**self.payload, 'key': 'CYCLE_MISSED'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data['key'], 'CYCLE_MISSED')
        self.assertEqual(created.data['channels'], ['DASHBOARD', 'TELEGRAM'])
        self.assertEqual(created.data['telegram_chat_ids'], '12345')
        self.assertEqual(created.data['email_list'], ['alerts@example.invalid'])
        rule = AlertRule.objects.get(key='CYCLE_MISSED')
        self.assertEqual(rule.updated_by, self.director)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='ALERT_RULE_CREATED', target_type='AlertRule',
            target_id=rule.pk).exists())

    def test_duplicate_kind_is_a_clear_400(self):
        AlertRule.objects.create(
            key='BRIEFING', recipient_capability='VIEW_INTELLIGENCE_REPORTS')
        self.client.force_authenticate(self.director)
        response = self.client.post(
            self.url, {**self.payload, 'key': 'BRIEFING'}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('already', str(response.data).lower())
        self.assertEqual(AlertRule.objects.filter(key='BRIEFING').count(), 1)

    def test_arbitrary_kind_is_rejected(self):
        self.client.force_authenticate(self.director)
        response = self.client.post(
            self.url, {**self.payload, 'key': 'NOT_A_KIND'}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(AlertRule.objects.exists())
        # Every fixed-vocabulary kind remains creatable in principle.
        self.assertEqual({k for k, _l in ALERT_RULES}, {
            'SECURITY_VERIFIED', 'SENSITIVE_CONFIRMED', 'SOURCE_HEALTH_FAILED',
            'CYCLE_MISSED', 'PROJECT_VERIFIED_ABANDONED', 'BRIEFING'})

    def test_gate_denial_for_member_without_manage_sources(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.url, {**self.payload, 'key': 'CYCLE_MISSED'}, format='json')
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(AlertRule.objects.exists())
