"""ICT Admin console (owner instruction, 2026-11-24).

Pins:
- the console renders for the assigned holder and for any superuser,
  and only for them (President and ordinary members are denied with
  the site's standard redirect; anonymous users go to login);
- the nav's ICT Admin link renders server-side only for them;
- the assignment is managed ONLY in the Django admin panel (owner
  clarification, 2026-11-24): the console has no reassignment form
  and its POST is refused; the admin change view is reachable by a
  superuser and not by any non-superuser, its picker never offers a
  superuser account, and a change there is audit-logged;
- after an admin change the new holder gains access and the old
  holder loses it (unless a superuser);
- every figure on the page equals the seeded records, and superuser
  accounts appear in no member figure or list on the page;
- the seed records the Director of Media as the initial holder and
  never overwrites an existing holder;
- SUPER ADMIN INVISIBILITY: the super admin account is never listed
  or manageable in the Contact & Mobilisation list or in the
  President's member-management surfaces (manage list, approvals,
  exports, swap picker and the per-member action routes — a superuser
  id 404s exactly like an unknown id).
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from core.ict_admin import seed_ict_admin_assignment
from core.models import (
    CommunityReport, IctAdminAssignment, IctAdminChange, Opportunity,
    OpportunityReport,
)
from editorial.models import Item as EditorialItem
from editorial.models import Source as EditorialSource
from intelligence.models import (
    Alert, AlertDelivery, CollectionRun, Project,
)
from leadership.models import LGA, RoleDefinition, Zone
from staff.forms import SwapPositionsForm
from staff.models import User
from story_intelligence.models import Institution, Promise
from telegram_integration.models import BotOutbox, TelegramMembership

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

ICT_URL = reverse('core:ict_admin')


def role_def(title, seat, tier='STATE'):
    return RoleDefinition.objects.create(
        title=title, tier=tier, seat_number=seat)


def make_user(username, rd=None, **kw):
    kw.setdefault('phone', username)
    kw.setdefault('status', 'VERIFIED')
    return User.objects.create_user(
        username=username, role_definition=rd, **kw)


class IctSeed(TestCase):
    """Shared seeded world for the console tests."""

    def setUp(self):
        self.central = Zone.objects.create(name='Kebbi Central')
        self.north = Zone.objects.create(name='Kebbi North')
        self.bk = LGA.objects.create(name='Birnin Kebbi', zone=self.central)
        self.jega = LGA.objects.create(name='Jega', zone=self.north)

        self.president_rd = role_def('President', 1)
        self.director_rd = role_def('Director of Media & Communications', 17)
        self.gs_rd = role_def('General Secretary', 3)

        self.director = make_user(
            'ict_director', self.director_rd, role='STATE',
            zone=self.central, lga=self.bk,
            first_name='Nasiru', last_name='Director')
        self.president = make_user(
            'ict_president', self.president_rd, role='STATE',
            first_name='Peter', last_name='President')
        self.superadmin = make_user(
            'ict_root', role='STATE', is_superuser=True, is_staff=True,
            first_name='Super', last_name='Adminsecret')
        self.member1 = make_user(
            'ict_member1', role='GENERAL', zone=self.central, lga=self.bk,
            first_name='Regular', last_name='Memberone')
        self.member2 = make_user(
            'ict_member2', role='GENERAL', zone=self.north, lga=self.jega,
            first_name='Second', last_name='Membertwo')
        self.pending1 = make_user(
            'ict_pending', role='GENERAL', status='PENDING',
            zone=self.central, lga=self.bk,
            first_name='Paul', last_name='Pending')
        self.target = make_user(
            'ict_target', role='GENERAL',
            first_name='New', last_name='Holder')

        IctAdminAssignment.objects.create(pk=1, user=self.director)


@override_settings(STORAGES=STORAGES)
class IctAccessTests(IctSeed):
    def test_holder_can_open_the_console(self):
        self.client.force_login(self.director)
        response = self.client.get(ICT_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ICT Admin Console')
        self.assertContains(response, 'Nasiru Director')

    def test_superuser_can_open_the_console(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(ICT_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ICT Admin Console')

    def test_president_is_denied(self):
        self.client.force_login(self.president)
        response = self.client.get(ICT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('staff:dashboard'))

    def test_ordinary_member_is_denied(self):
        self.client.force_login(self.member1)
        response = self.client.get(ICT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('staff:dashboard'))

    def test_anonymous_goes_to_login(self):
        response = self.client.get(ICT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/account/login/', response.url)

    def test_unassigned_console_is_superuser_only(self):
        assignment = IctAdminAssignment.objects.get(pk=1)
        assignment.user = None
        assignment.save()
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(ICT_URL).status_code, 302)
        self.client.force_login(self.superadmin)
        self.assertEqual(self.client.get(ICT_URL).status_code, 200)


@override_settings(STORAGES=STORAGES)
class IctNavTests(IctSeed):
    def _home(self, user):
        self.client.force_login(user)
        return self.client.get('/')

    def test_nav_link_visible_to_holder_and_superuser(self):
        self.assertContains(self._home(self.director), '/ict-admin/')
        self.assertContains(self._home(self.superadmin), '/ict-admin/')

    def test_nav_link_hidden_from_president_and_members(self):
        self.assertNotContains(self._home(self.president), '/ict-admin/')
        self.assertNotContains(self._home(self.member1), '/ict-admin/')
        self.client.logout()
        response = self.client.get('/')
        self.assertNotContains(response, '/ict-admin/')


@override_settings(STORAGES=STORAGES)
class IctFigureTests(IctSeed):
    def setUp(self):
        super().setUp()
        Campaign.objects.create(
            author=self.director, title='Published One', slug='pub-one',
            status='PUBLISHED')
        Campaign.objects.create(
            author=self.director, title='Published Two', slug='pub-two',
            status='PUBLISHED')
        Campaign.objects.create(
            author=self.director, title='Draft One', slug='draft-one',
            status='DRAFT')
        self.opp_open = Opportunity.objects.create(
            title='Open Opp', slug='open-opp', provider='Provider',
            description='Desc', status='OPEN')
        Opportunity.objects.create(
            title='Open Opp 2', slug='open-opp-2', provider='Provider',
            description='Desc', status='OPEN')
        Opportunity.objects.create(
            title='Closed Opp', slug='closed-opp', provider='Provider',
            description='Desc', status='CLOSED')
        CommunityReport.objects.create(
            reporter_name='Reporter A', location_details='Jega',
            category='HEALTH', what_happened='Something', status='PENDING')
        CommunityReport.objects.create(
            reporter_name='Reporter B', location_details='Zuru',
            category='HEALTH', what_happened='Something else',
            status='APPROVED')
        OpportunityReport.objects.create(
            opportunity=self.opp_open, reason='Looks fake', status='NEW')
        source = EditorialSource.objects.create(
            name='Test Source', url='https://example.com/feed',
            enabled=True, consecutive_failures=2)
        EditorialSource.objects.create(
            name='Quiet Source', url='https://example.com/page',
            enabled=False)
        for i, state in enumerate(
                ('WAITING', 'WAITING', 'REVIEW', 'DISMISSED')):
            EditorialItem.objects.create(
                key=f'ict-item-{i}', kind='NEWS', state=state,
                title=f'Item {i}', source=source)
        CollectionRun.objects.create(
            trigger='SCHEDULED', status='COMPLETED',
            started_at=timezone.now(), sources_due=2, sources_ok=2,
            items_new=4)
        CollectionRun.objects.create(
            trigger='MANUAL', status='FAILED',
            started_at=timezone.now(), sources_due=2, sources_failed=1)
        alert = Alert.objects.create(
            kind='SOURCE_HEALTH_FAILED', title='Source failed',
            message='It failed', dedupe_key='ict-alert-1')
        AlertDelivery.objects.create(
            alert=alert, channel='EMAIL', recipient='a@example.com',
            status='FAILED', error='boom')
        AlertDelivery.objects.create(
            alert=alert, channel='DASHBOARD', recipient='ict_director',
            status='SENT')
        TelegramMembership.objects.create(
            user=self.member1, telegram_user_id=111001,
            is_verified=True, telegram_status='member')
        TelegramMembership.objects.create(
            user=self.member2, telegram_user_id=111002,
            is_verified=False, telegram_status='not_member')
        BotOutbox.objects.create(kind='CUSTOM', text='queued one',
                                 state='QUEUED')
        BotOutbox.objects.create(kind='CUSTOM', text='sent one',
                                 state='SENT')
        BotOutbox.objects.create(kind='CUSTOM', text='sent two',
                                 state='SENT')
        BotOutbox.objects.create(kind='CUSTOM', text='failed one',
                                 state='FAILED')
        institution = Institution.objects.create(
            name='Kebbi State Government', kind='OTHER')
        Promise.objects.create(
            institution=institution, title='A tracked promise',
            description='Desc', announced_on=timezone.localdate(),
            status='ANNOUNCED')
        Project.objects.create(
            title='A tracked project', description='Desc',
            project_code='KPN-PRJ-2026-00999', sector='INFRASTRUCTURE',
            category='ROAD', lga=self.jega, status='ANNOUNCED',
            institution=institution, created_by=self.director)

    def _console(self):
        self.client.force_login(self.director)
        return self.client.get(ICT_URL)

    def test_stat_band_equals_seeded_records(self):
        stats = self._console().context['stats']
        # 7 accounts exist; the superuser is never counted as a member.
        self.assertEqual(stats['total_members'], 6)
        self.assertEqual(stats['verified_members'], 5)
        self.assertEqual(stats['pending_verification'], 1)
        self.assertEqual(stats['position_holders'], 2)
        self.assertEqual(stats['published_articles'], 2)
        self.assertEqual(stats['open_opportunities'], 2)
        self.assertEqual(stats['pending_community_reports'], 1)
        self.assertEqual(stats['new_listing_reports'], 1)

    def test_member_charts_equal_seeded_records(self):
        response = self._console()
        status = {r['label']: r['value']
                  for r in response.context['member_status_bars']}
        self.assertEqual(status['Verified'], 5)
        self.assertEqual(status['Pending'], 1)
        self.assertEqual(status['Suspended'], 0)
        zones = {r['label']: r['value']
                 for r in response.context['member_zone_bars']}
        self.assertEqual(zones, {'Kebbi Central': 2, 'Kebbi North': 1})

    def test_panels_equal_seeded_records(self):
        response = self._console()
        ctx = response.context
        items = dict(ctx['editorial_item_states'])
        self.assertEqual(items['Waiting for processing'], 2)
        self.assertEqual(items['Needs human review'], 1)
        self.assertEqual(items['Dismissed'], 1)
        self.assertEqual(items['Handed to existing workflow'], 0)
        self.assertEqual(ctx['sources_total'], 2)
        self.assertEqual(ctx['sources_enabled'], 1)
        self.assertEqual(ctx['sources_failing'], 1)
        self.assertEqual(len(ctx['collection_runs']), 2)
        self.assertEqual(ctx['alert_failures'], 1)
        self.assertEqual(ctx['alerts_total'], 2)
        campaigns = dict(ctx['campaign_status_counts'])
        self.assertEqual(campaigns['Published'], 2)
        self.assertEqual(campaigns['Draft'], 1)
        opportunities = dict(ctx['opportunity_status_counts'])
        self.assertEqual(opportunities['Open & Accepting Applications'], 2)
        self.assertEqual(opportunities['Closed'], 1)
        self.assertEqual(ctx['promises_total'], 1)
        self.assertEqual(ctx['projects_total'], 1)
        self.assertEqual(ctx['telegram_connected'], 2)
        self.assertEqual(ctx['telegram_verified'], 1)
        self.assertEqual(ctx['outbox_queued'], 1)
        self.assertEqual(ctx['outbox_sent'], 2)
        self.assertEqual(ctx['outbox_failed'], 1)

    def test_leadership_panel_lists_holders_and_vacancies(self):
        response = self._console()
        rows = {row['definition'].title: row['holders']
                for row in response.context['leadership_rows']}
        self.assertEqual(
            [h.username for h in rows['President']], ['ict_president'])
        self.assertEqual(
            [h.username for h in rows['Director of Media & Communications']],
            ['ict_director'])
        self.assertEqual(rows['General Secretary'], [])
        self.assertContains(response, 'Vacant')

    def test_superuser_appears_nowhere_on_the_page(self):
        response = self._console()
        self.assertNotContains(response, 'Adminsecret')
        recent = [m.username for m in response.context['recent_members']]
        self.assertNotIn('ict_root', recent)
        self.assertIn('ict_member1', recent)


@override_settings(STORAGES=STORAGES)
class IctAdminManagementTests(IctSeed):
    """The assignment is managed ONLY in the Django admin panel
    (owner clarification, 2026-11-24): the Super Admin operates only
    through /admin/. The console page carries no change controls."""

    ADMIN_CHANGE_URL = reverse(
        'admin:core_ictadminassignment_change', args=[1])

    def test_console_has_no_reassignment_controls(self):
        for user in (self.director, self.superadmin):
            self.client.force_login(user)
            response = self.client.get(ICT_URL)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'name="new_holder"')
            self.assertNotContains(response, 'Reassign ICT Admin')
            self.assertContains(response, 'Django admin panel')

    def test_post_to_the_console_changes_nothing(self):
        self.client.force_login(self.superadmin)
        response = self.client.post(ICT_URL, {'new_holder': self.target.pk})
        self.assertEqual(response.status_code, 405)
        assignment = IctAdminAssignment.objects.get(pk=1)
        self.assertEqual(assignment.user_id, self.director.pk)
        self.assertEqual(IctAdminChange.objects.count(), 0)

    def test_admin_change_view_reachable_by_superuser(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(self.ADMIN_CHANGE_URL)
        self.assertEqual(response.status_code, 200)

    def test_admin_change_view_denied_to_non_superusers(self):
        # The holder is not a staff user: the admin sends him to its
        # login page — he cannot reach the change form at all.
        self.client.force_login(self.director)
        response = self.client.get(self.ADMIN_CHANGE_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
        # A staff user without the model change permission gets 403 —
        # even though he can sign in to the admin.
        staffer = make_user(
            'ict_staffer', role='GENERAL', is_staff=True,
            first_name='Staff', last_name='Noaccess')
        self.client.force_login(staffer)
        response = self.client.get(self.ADMIN_CHANGE_URL)
        self.assertEqual(response.status_code, 403)

    def test_admin_picker_excludes_superusers(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(self.ADMIN_CHANGE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f'<option value="{self.target.pk}"')
        self.assertNotContains(
            response, f'<option value="{self.superadmin.pk}"')

    def test_admin_change_moves_the_assignment_and_access(self):
        self.client.force_login(self.superadmin)
        response = self.client.post(
            self.ADMIN_CHANGE_URL, {'user': self.target.pk})
        self.assertEqual(response.status_code, 302)
        assignment = IctAdminAssignment.objects.get(pk=1)
        self.assertEqual(assignment.user_id, self.target.pk)
        self.assertEqual(assignment.updated_by_id, self.superadmin.pk)
        change = IctAdminChange.objects.get()
        self.assertEqual(change.previous_holder_id, self.director.pk)
        self.assertEqual(change.new_holder_id, self.target.pk)
        self.assertEqual(change.changed_by_id, self.superadmin.pk)
        # Access follows the assignment: new holder in, old holder
        # out, the superuser keeps access regardless.
        self.client.force_login(self.target)
        self.assertEqual(self.client.get(ICT_URL).status_code, 200)
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(ICT_URL).status_code, 302)
        self.client.force_login(self.superadmin)
        self.assertEqual(self.client.get(ICT_URL).status_code, 200)


@override_settings(STORAGES=STORAGES)
class IctSeedTests(TestCase):
    def setUp(self):
        self.director_rd = role_def('Director of Media & Communications', 17)
        self.director = make_user(
            'seed_director', self.director_rd, role='STATE',
            first_name='Seed', last_name='Director')
        self.member = make_user(
            'seed_member', role='GENERAL',
            first_name='Seed', last_name='Member')

    def test_seed_assigns_the_director_of_media(self):
        seed_ict_admin_assignment()
        assignment = IctAdminAssignment.objects.get(pk=1)
        self.assertEqual(assignment.user_id, self.director.pk)

    def test_seed_never_overwrites_an_existing_holder(self):
        assignment = IctAdminAssignment.objects.create(
            pk=1, user=self.member)
        seed_ict_admin_assignment()
        assignment.refresh_from_db()
        self.assertEqual(assignment.user_id, self.member.pk)

    def test_seed_without_a_director_leaves_unassigned(self):
        self.director.role_definition = None
        self.director.save()
        seed_ict_admin_assignment()
        assignment = IctAdminAssignment.objects.get(pk=1)
        self.assertIsNone(assignment.user_id)


@override_settings(STORAGES=STORAGES)
class SuperAdminInvisibilityTests(IctSeed):
    """The super admin is never listed or manageable in the Contact &
    Mobilisation list or the President's member-management surfaces."""

    def setUp(self):
        super().setUp()
        self.pending_root = make_user(
            'ict_pendingroot', role='STATE', status='PENDING',
            is_superuser=True, is_staff=True,
            first_name='Pending', last_name='Rootsecret')

    def test_mobilisation_list_excludes_superusers(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse('staff:member_mobilization'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Adminsecret')
        self.assertNotContains(response, 'Rootsecret')
        self.assertContains(response, 'Memberone')
        # The count matches the visible list: every non-superuser.
        self.assertEqual(response.context['total_count'], 6)

    def test_manage_staff_excludes_superusers(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse('staff:manage_staff'))
        self.assertEqual(response.status_code, 200)
        listed = [u.username for u in response.context['staff']]
        self.assertNotIn('ict_root', listed)
        self.assertNotIn('ict_pendingroot', listed)
        self.assertIn('ict_member1', listed)
        self.assertNotContains(response, 'Adminsecret')

    def test_approve_members_excludes_superuser_applicants(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse('staff:approve_members'))
        self.assertEqual(response.status_code, 200)
        pending = [u.username for u in response.context['pending_users']]
        self.assertIn('ict_pending', pending)
        self.assertNotIn('ict_pendingroot', pending)
        # The review route 404s for the superuser, works for a member.
        response = self.client.get(
            reverse('staff:review_applicant', args=[self.pending_root.pk]))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            reverse('staff:review_applicant', args=[self.pending1.pk]))
        self.assertEqual(response.status_code, 200)

    def test_action_routes_404_for_superuser_like_unknown_id(self):
        self.client.force_login(self.president)
        for name in ('staff:edit_member_role', 'staff:promote_member',
                     'staff:demote_member', 'staff:dismiss_member',
                     'staff:suspend_member', 'staff:reinstate_member'):
            response = self.client.get(
                reverse(name, args=[self.superadmin.pk]))
            self.assertEqual(response.status_code, 404, name)
            response = self.client.get(reverse(name, args=[999999]))
            self.assertEqual(response.status_code, 404, name)
        # A normal member's page still opens.
        response = self.client.get(
            reverse('staff:dismiss_member', args=[self.member1.pk]))
        self.assertEqual(response.status_code, 200)

    def test_action_post_cannot_touch_the_superuser(self):
        self.client.force_login(self.president)
        response = self.client.post(
            reverse('staff:dismiss_member', args=[self.superadmin.pk]),
            {'reason': 'test'})
        self.assertEqual(response.status_code, 404)
        self.superadmin.refresh_from_db()
        self.assertTrue(self.superadmin.is_active)
        self.assertEqual(self.superadmin.status, 'VERIFIED')

    def test_member_exports_exclude_superusers(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse('staff:export_members_csv'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertNotIn('Adminsecret', body)
        self.assertIn('Memberone', body)

    def test_swap_picker_excludes_superusers(self):
        form = SwapPositionsForm()
        member1_qs = form.fields['member1'].queryset
        member2_qs = form.fields['member2'].queryset
        self.assertTrue(member1_qs.filter(pk=self.director.pk).exists())
        self.assertFalse(member1_qs.filter(pk=self.superadmin.pk).exists())
        self.assertFalse(member2_qs.filter(pk=self.superadmin.pk).exists())
