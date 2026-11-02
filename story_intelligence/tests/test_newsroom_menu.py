"""v2.9.2 — Newsroom menu consolidation.

All newsroom features live in ONE grouped "Newsroom" section of the
mobile hamburger menu, mirroring the existing "KPN Network" section,
and in a matching "Newsroom" dropdown in the desktop header (which
uses the KPN Network dropdown pattern). The scattered standalone
Promise Tracker / Archive / Future Signal / Human Impact links added
in Phases 2–4 are gone.
"""

from django.test import TestCase
from django.urls import reverse


def newsroom_hrefs():
    return {
        'News': reverse('campaigns:newsroom'),
        'Promise Tracker': reverse('promises:list'),
        'Story Archive': reverse('archive:home'),
        'Future Signal': reverse('signals:list'),
        'Human Impact Files': reverse('impact_files:list'),
    }


class NewsroomMenuTests(TestCase):
    def setUp(self):
        # Any public page renders base.html; the signals list body
        # itself links nowhere in the newsroom group, so every group
        # href found in the HTML comes from the menus.
        self.response = self.client.get(reverse('signals:list'))
        self.html = self.response.content.decode()

    def test_all_five_destinations_are_linked(self):
        self.assertEqual(self.response.status_code, 200)
        for label, href in newsroom_hrefs().items():
            self.assertIn(f'href="{href}"', self.html, label)

    def test_desktop_nav_groups_newsroom_in_a_dropdown(self):
        # Each destination is a dropdown item, like KPN Network's.
        for label, href in newsroom_hrefs().items():
            self.assertIn(f'href="{href}" class="kpn-dropdown-item"',
                          self.html, label)
        # The scattered standalone top-level links are gone.
        for label in ['Promise Tracker', 'Archive', 'Future Signal',
                      'Human Impact']:
            self.assertNotIn(f'kpn-nav-link">{label}', self.html)
        self.assertNotIn(
            f'<a href="{reverse("campaigns:newsroom")}" '
            'class="kpn-nav-link">Newsroom</a>', self.html)

    def test_mobile_menu_has_one_grouped_newsroom_section(self):
        mobile = self.html.split('id="kpn-mobile-menu"', 1)[1]
        # The grouped-section heading, same markup pattern as the
        # KPN Network section heading.
        self.assertIn('>Newsroom</p>', mobile)
        before, _, rest = mobile.partition('>Newsroom</p>')
        section, _, _ = rest.partition('>KPN Network</p>')
        # All five destinations sit inside the one group, with the
        # group's reader-facing labels.
        for label, href in newsroom_hrefs().items():
            self.assertIn(f'href="{href}"', section, label)
            self.assertIn(f'>{label}', section, label)
        # None of them appears as a scattered standalone link before
        # the group heading.
        for label, href in newsroom_hrefs().items():
            self.assertNotIn(f'href="{href}"', before, label)

    def test_kpn_network_group_is_unchanged(self):
        mobile = self.html.split('id="kpn-mobile-menu"', 1)[1]
        self.assertIn('>KPN Network</p>', mobile)
        network = mobile.split('>KPN Network</p>', 1)[1]
        self.assertIn(f'href="{reverse("core:patrons")}"', network)
        self.assertIn(f'href="{reverse("core:leadership")}"', network)
