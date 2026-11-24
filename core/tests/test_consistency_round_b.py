"""Consistency Round B smoke tests (owner instruction 2026-11-24).

Round B restyles every remaining public page into the Priorities 1–6
design language (kpn-design.css tokens/components, .kpn-page-hero
treatment, breadcrumbs, premium cards) without changing any page's
text, data, forms or behaviour. These tests pin, for each upgraded
page: the route resolves anonymously, the page's own existing content
is still present, the hero treatment is applied, and no hero carries a
credit line (owner removed them site-wide).
"""

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.models import Patron
from leadership.models import LGA, RoleDefinition, Ward, Zone
from media.models import MediaItem
from staff.models import User


def make_member(username, **kw):
    kw.setdefault('phone', username)
    kw.setdefault('role', 'GENERAL')
    kw.setdefault('status', 'VERIFIED')
    return User.objects.create_user(username=username, **kw)


class AboutRoundBTests(TestCase):
    def test_about_hero_and_content(self):
        response = self.client.get(reverse('core:about'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero-photo', html)
        self.assertIn('about-hero', html)
        self.assertIn('About Kebbi Progressive Youth Network', html)
        self.assertIn('One Voice, One Change', html)
        self.assertIn('Our Network Structure', html)
        self.assertNotIn('kpn-hero-credit', html)


class PatronsRoundBTests(TestCase):
    def setUp(self):
        Patron.objects.create(
            patron_type='GRAND', full_name='Grand Patron Example',
            title='Grand Patron of KPN',
            bio=('Word ' * 30).strip())
        Patron.objects.create(
            patron_type='PATRON', full_name='Patron Example',
            title='Patron of KPN', bio='Short bio.')

    def test_patrons_hero_cards_and_bio_hooks(self):
        response = self.client.get(reverse('core:patrons'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero-photo', html)
        self.assertIn('archive-hero', html)
        self.assertIn('kpn-patron-feature', html)
        self.assertIn('kpn-patron-card', html)
        self.assertIn('Grand Patron Example', html)
        self.assertIn('Patron Example', html)
        # The read-more behaviour hooks must survive the restyle.
        self.assertIn('patron-bio-wrapper', html)
        self.assertIn('bio-toggle-btn', html)
        self.assertIn('data-patron-id', html)
        self.assertNotIn('kpn-hero-credit', html)

    def test_patrons_empty_state(self):
        Patron.objects.all().delete()
        response = self.client.get(reverse('core:patrons'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Patrons Coming Soon')


class LeadershipRoundBTests(TestCase):
    def setUp(self):
        RoleDefinition.objects.create(
            title='President', tier='STATE', seat_number=1)

    def test_leadership_hero_and_vacant_card(self):
        response = self.client.get(reverse('core:leadership'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero-photo', html)
        self.assertIn('leadership-hero', html)
        self.assertIn('kpn-person-card', html)
        self.assertIn('President', html)
        self.assertIn('Vacant', html)
        self.assertNotIn('kpn-hero-credit', html)

    def test_leadership_holder_card_and_profile_link(self):
        role = RoleDefinition.objects.get(title='President')
        holder = make_member(
            'rb_president', role='STATE', role_definition=role,
            first_name='Holder', last_name='Example')
        response = self.client.get(reverse('core:leadership'))
        self.assertContains(response, 'Holder Example')
        self.assertContains(
            response, reverse('core:view_profile', args=[holder.id]))


class ViewProfileRoundBTests(TestCase):
    def setUp(self):
        role = RoleDefinition.objects.create(
            title='Director of Media', tier='STATE', seat_number=2)
        self.profile_user = make_member(
            'rb_profile', role='STATE', role_definition=role,
            first_name='Profile', last_name='Example',
            bio='A short member biography.')

    def test_profile_band_and_content(self):
        response = self.client.get(
            reverse('core:view_profile', args=[self.profile_user.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-profile-band', html)
        self.assertNotIn('to-kpn-blue', html)
        self.assertIn('Profile Example', html)
        self.assertIn('Director of Media', html)
        self.assertIn('A short member biography.', html)
        self.assertIn('Back to Leadership', html)


class GalleryRoundBTests(TestCase):
    def setUp(self):
        uploader = make_member('rb_uploader', first_name='Media',
                               last_name='Uploader')
        MediaItem.objects.create(
            title='Community Event Photo', description='A KPN event.',
            media_type='PHOTO', file='gallery/rb-photo.jpg',
            status='APPROVED', uploaded_by=uploader)

    def test_gallery_hero_and_media_card(self):
        response = self.client.get(reverse('core:gallery'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero-photo', html)
        self.assertIn('metrics-hero', html)
        self.assertIn('kpn-media-card', html)
        self.assertIn('Community Event Photo', html)
        self.assertIn('openLightbox', html)
        self.assertNotIn('kpn-hero-credit', html)

    def test_gallery_filter_still_works(self):
        response = self.client.get(reverse('core:gallery'),
                                   {'type': 'VIDEO'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Community Event Photo')


class ContactRoundBTests(TestCase):
    def test_contact_hero_info_and_form_fields(self):
        response = self.client.get(reverse('core:contact'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero', html)
        self.assertIn('Get In Touch', html)
        self.assertIn('Sani Abacha Bypass Road, Birnin Kebbi', html)
        self.assertIn('+234 806 777 0283', html)
        self.assertIn('info@kpn.com.ng', html)
        # The form contract is unchanged.
        self.assertIn('name="name"', html)
        self.assertIn('name="email"', html)
        self.assertIn('name="message"', html)
        self.assertIn('method="POST"', html)


class SupportUsRoundBTests(TestCase):
    def test_support_hero_and_bank_card(self):
        response = self.client.get(reverse('core:support_us'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero-photo', html)
        self.assertIn('impact-hero', html)
        self.assertIn('Support Our Mission', html)
        self.assertIn('kpn-bank-card', html)
        self.assertIn('Kebbi Progressive Youth Network', html)
        self.assertIn('Access Bank Nigeria', html)
        self.assertIn('Bank details are being verified', html)
        self.assertIn('copyAccountNumber()', html)
        self.assertNotIn('kpn-hero-credit', html)


class FaqRoundBTests(TestCase):
    def test_faq_hero_accordion_and_search(self):
        response = self.client.get(reverse('core:faq'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero', html)
        self.assertIn('Frequently Asked Questions', html)
        self.assertEqual(html.count('kpn-faq-card faq-item'), 9)
        self.assertIn('What is the Kebbi Progressive Youth Network (KPN)?', html)
        self.assertIn('id="faqSearch"', html)
        self.assertIn('category-btn', html)
        self.assertIn('Still Have Questions?', html)


class NetworkRankingsRoundBTests(TestCase):
    def setUp(self):
        zone = Zone.objects.create(name='Rankings Zone')
        self.lga = LGA.objects.create(name='Rankings LGA', zone=zone)
        Ward.objects.create(name='Rankings Ward', lga=self.lga)
        make_member('rb_ranked', lga=self.lga)

    def test_rankings_hero_and_public_cards(self):
        response = self.client.get(reverse('core:network_rankings'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-page-hero', html)
        self.assertNotIn('bg-kpn-blue', html)
        self.assertIn('kpn-rank-card', html)
        self.assertIn('Top Active LGAs', html)
        self.assertIn('Rankings LGA', html)
        self.assertIn('Verified Trusted Reporters', html)
        # The internal dashboard never renders for anonymous visitors.
        self.assertNotIn('Internal Executive Dashboard', html)


class ErrorPagesRoundBTests(TestCase):
    def test_404_page_uses_design_language(self):
        response = self.client.get('/definitely-not-a-real-page/')
        self.assertEqual(response.status_code, 404)
        html = response.content.decode('utf-8')
        self.assertIn('kpn-error-card', html)
        self.assertIn('Page Not Found', html)

    def test_403_template_uses_design_language(self):
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().get('/too-many/')
        request.user = AnonymousUser()
        html = render_to_string('403.html', request=request)
        self.assertIn('kpn-error-card', html)
        self.assertIn('Too Many Requests', html)
        self.assertIn('Back to Login', html)

    def test_500_template_is_standalone_and_branded(self):
        html = render_to_string('500.html')
        self.assertIn('Something Went Wrong', html)
        self.assertIn('Kebbi Progressive Youth Network', html)
        self.assertIn('#176b36', html)
