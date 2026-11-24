"""Role-name alignment (owner instruction, 2026-11-24).

The constitutional catalogue in leadership/roles.py carries the new
role names; ROLE_ALIASES maps the old ones. Pins:

- sampled role dashboards display the CANONICAL title and never the
  old title anywhere in the response;
- the typing (welcome_messages) phrases of every dashboard contain no
  old role name;
- a member whose STORED RoleDefinition title is a legacy alias still
  displays the canonical title on their dashboard and public profile,
  and the /account/dashboard/ dispatcher routes them to their role
  dashboard (it previously fell through to the generic dashboard).
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from leadership.models import LGA, RoleDefinition, Ward, Zone
from leadership.roles import ROLE_ALIASES
from staff.models import User
from telegram_integration.models import TelegramMembership

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

_uid = [9700]


def make_user(username, rd=None, **kw):
    kw.setdefault('phone', username)
    kw.setdefault('status', 'VERIFIED')
    user = User.objects.create_user(username=username, role_definition=rd,
                                    **kw)
    _uid[0] += 1
    TelegramMembership.objects.create(
        user=user, telegram_user_id=999700000 + _uid[0], is_verified=True,
        telegram_status='member')
    return user


# (url, stored/canonical title, tier, role code, old title that must vanish)
SAMPLES = [
    ('/account/dashboards/lga-coordinator/', 'LGA Network Lead', 'LGA',
     'LGA', 'LGA Coordinator'),
    ('/account/dashboards/ward-coordinator/', 'Ward Community Lead', 'WARD',
     'WARD', 'Ward Coordinator'),
    ('/account/dashboards/zonal-coordinator/', 'Senatorial Director',
     'ZONAL', 'ZONAL', 'Zonal Coordinator'),
    ('/account/dashboards/treasurer/', 'Director of Finance', 'STATE',
     'STATE', 'Treasurer'),
    ('/account/dashboards/lga-secretary/', 'LGA Administrative Officer',
     'LGA', 'LGA', 'LGA Secretary'),
    ('/account/dashboards/organizing-secretary/',
     'Director of Programmes & Events', 'STATE', 'STATE',
     'Organizing Secretary'),
]


@override_settings(STORAGES=STORAGES)
class CanonicalDashboardTitleTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name='Kebbi Central')
        self.lga = LGA.objects.create(name='Birnin Kebbi', zone=self.zone)
        self.ward = Ward.objects.create(name='Nassarawa Ward', lga=self.lga)

    def test_sampled_dashboards_show_canonical_titles_only(self):
        for i, (url, title, tier, role_code, old) in enumerate(SAMPLES):
            rd = RoleDefinition.objects.create(
                title=title, tier=tier, seat_number=50 + i)
            kw = dict(role=role_code, zone=self.zone)
            if tier in ('LGA', 'WARD'):
                kw['lga'] = self.lga
            if tier == 'WARD':
                kw['ward'] = self.ward
            user = make_user(f'align_{i}', rd, **kw)
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, f'{title} Dashboard')
            self.assertNotContains(response, old)
            self.client.logout()


@override_settings(STORAGES=STORAGES)
class LegacyStoredTitleTests(TestCase):
    """A stored legacy alias must display (and route) canonically."""

    def setUp(self):
        self.zone = Zone.objects.create(name='Kebbi Central')
        self.lga = LGA.objects.create(name='Birnin Kebbi', zone=self.zone)
        legacy = RoleDefinition.objects.create(
            title='LGA Coordinator', tier='LGA', seat_number=1)
        self.user = make_user('align_legacy', legacy, role='LGA',
                              zone=self.zone, lga=self.lga)
        self.client.force_login(self.user)

    def test_dashboard_header_shows_canonical_title(self):
        response = self.client.get('/account/dashboards/lga-coordinator/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LGA Network Lead Dashboard')
        self.assertContains(response, 'LGA Network Lead')
        self.assertNotContains(response, 'LGA Coordinator')

    def test_dispatcher_routes_legacy_holder_to_role_dashboard(self):
        response = self.client.get('/account/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LGA Network Lead Dashboard')
        self.assertNotContains(response, 'LGA Coordinator')

    def test_public_profile_shows_canonical_title(self):
        response = self.client.get(
            reverse('core:view_profile', args=[self.user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LGA Network Lead')
        self.assertNotContains(response, 'LGA Coordinator')


class TypingPhraseAlignmentTests(TestCase):
    """No welcome/typing phrase in any dashboard may name an old role."""

    def _phrases(self):
        base = Path(settings.BASE_DIR)
        files = list((base / 'staff/templates/staff/dashboards').glob('*.html'))
        files.append(base / 'staff/templates/staff/dashboard.html')
        phrases = []
        for f in files:
            text = f.read_text(encoding='utf-8')
            for attr in re.findall(
                    r'(?:welcome_messages|data-messages)="([^"]*)"', text):
                phrases.extend(p for p in attr.split('|') if p.strip())
        return phrases

    def test_no_old_role_name_in_typing_phrases(self):
        phrases = self._phrases()
        self.assertTrue(phrases)
        for phrase in phrases:
            for old in ROLE_ALIASES:
                self.assertNotIn(old, phrase)
                self.assertNotIn(old.lower(), phrase.lower())

    def test_ward_finance_phrase_names_canonical_role(self):
        self.assertIn('Supporting the Ward Finance Officer.',
                      self._phrases())
