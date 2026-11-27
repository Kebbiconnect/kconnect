"""App 2.0.5 website API contracts.

Covers: member search by phone/email, pending-member tier filter,
announcement tier audiences (WARD_TIER / LGA_TIER), full-list location
pagination, and register gender normalisation.
"""
import io

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from editorial.tests.helpers import geo, make_user, media_director, president
from leadership.models import LGA, RoleDefinition, Ward, Zone
from staff.models import Announcement, User

API = '/api/v1/'


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class MemberSearchTests(TestCase):
    def setUp(self):
        self.viewer = media_director('s205_director')
        zone, lga, ward = geo()
        self.target = User.objects.create_user(
            username='s205_target', role='GENERAL', status='VERIFIED',
            first_name='Searchable', last_name='Person',
            phone='08035550199', email='findme205@example.invalid',
            zone=zone, lga=lga, ward=ward)

    def test_found_by_phone_fragment(self):
        response = client_for(self.viewer).get(API + 'members/?search=5550199')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(self.target.pk, [row['id'] for row in response.data['results']])

    def test_found_by_email_fragment(self):
        response = client_for(self.viewer).get(API + 'members/?search=findme205')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(self.target.pk, [row['id'] for row in response.data['results']])


class PendingTierFilterTests(TestCase):
    def setUp(self):
        self.viewer = president('p205_president')
        self.ward_applicant = make_user(
            'p205_ward', title='Ward Community Lead', tier='WARD',
            role='WARD', status='PENDING')
        self.lga_applicant = make_user(
            'p205_lga', title='LGA Network Lead', tier='LGA',
            role='LGA', status='PENDING')

    def ids(self, query=''):
        response = client_for(self.viewer).get(API + 'members/pending/' + query)
        self.assertEqual(response.status_code, 200, response.content)
        return [row['id'] for row in response.data['results']]

    def test_ward_tier_filter(self):
        ids = self.ids('?tier=WARD')
        self.assertIn(self.ward_applicant.pk, ids)
        self.assertNotIn(self.lga_applicant.pk, ids)

    def test_lga_tier_filter(self):
        ids = self.ids('?tier=LGA')
        self.assertIn(self.lga_applicant.pk, ids)
        self.assertNotIn(self.ward_applicant.pk, ids)

    def test_unknown_tier_is_ignored(self):
        ids = self.ids('?tier=BOGUS')
        self.assertIn(self.ward_applicant.pk, ids)
        self.assertIn(self.lga_applicant.pk, ids)


class AnnouncementTierAudienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zone = Zone.objects.create(name='Tier audience zone')
        cls.lga = LGA.objects.create(name='Tier audience LGA', zone=cls.zone)
        cls.ward = Ward.objects.create(name='Tier audience ward', lga=cls.lga)
        cls.users = {}
        for tier, title in [('STATE', 'President'), ('LGA', 'LGA Network Lead'),
                            ('WARD', 'Ward Community Lead')]:
            rd = RoleDefinition.objects.create(title=title, tier=tier, seat_number=1)
            cls.users[tier] = User.objects.create_user(
                username='tier205_' + tier, phone=tier, status='VERIFIED',
                role=tier, role_definition=rd, zone=cls.zone, lga=cls.lga,
                ward=cls.ward)
        cls.general = User.objects.create_user(
            username='tier205_general', phone='general', role='GENERAL',
            status='VERIFIED', zone=cls.zone, lga=cls.lga, ward=cls.ward)

    def publish(self, scope, **kw):
        return Announcement.objects.create(
            title='Tier audience test', content='Body', scope=scope,
            created_by=self.users['STATE'], **kw)

    def visible(self, announcement, user):
        return Announcement.for_user(user).filter(pk=announcement.pk).exists()

    def test_ward_tier_reaches_ward_holders_only(self):
        announcement = self.publish('WARD_TIER')
        self.assertTrue(self.visible(announcement, self.users['WARD']))
        self.assertFalse(self.visible(announcement, self.users['LGA']))
        self.assertFalse(self.visible(announcement, self.users['STATE']))
        self.assertFalse(self.visible(announcement, self.general))
        self.assertEqual(announcement.get_target_display(), 'All Ward Roles')

    def test_lga_tier_reaches_lga_holders_only(self):
        announcement = self.publish('LGA_TIER')
        self.assertTrue(self.visible(announcement, self.users['LGA']))
        self.assertFalse(self.visible(announcement, self.users['WARD']))
        self.assertFalse(self.visible(announcement, self.users['STATE']))
        self.assertFalse(self.visible(announcement, self.general))
        self.assertEqual(announcement.get_target_display(), 'All LGA Roles')

    def test_general_and_zonal_behaviour_unchanged(self):
        general = self.publish('GENERAL')
        for user in [*self.users.values(), self.general]:
            self.assertTrue(self.visible(general, user))
        zonal = self.publish('ZONAL', target_zone=self.zone)
        for user in [*self.users.values(), self.general]:
            self.assertTrue(self.visible(zonal, user))

    def test_tier_scopes_reject_targets_in_clean(self):
        from django.core.exceptions import ValidationError
        for scope in ('WARD_TIER', 'LGA_TIER'):
            with self.assertRaises(ValidationError):
                Announcement(title='X', content='Y', scope=scope,
                             target_zone=self.zone).full_clean()

    def test_api_create_tier_scope_without_target_and_reject_with_target(self):
        client = client_for(self.users['STATE'])
        created = client.post(API + 'announcements/', {
            'title': 'Ward tier API', 'content': 'For all ward holders.',
            'scope': 'WARD_TIER', 'priority': 'NORMAL',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data['scope'], 'WARD_TIER')
        rejected = client.post(API + 'announcements/', {
            'title': 'Ward tier API bad', 'content': 'Must not carry a target.',
            'scope': 'WARD_TIER', 'priority': 'NORMAL',
            'target_zone': self.zone.pk,
        }, format='json')
        self.assertEqual(rejected.status_code, 400, rejected.content)
        received = client_for(self.users['WARD']).get(API + 'announcements/received/')
        self.assertIn(created.data['id'], [row['id'] for row in received.data['results']])
        received_lga = client_for(self.users['LGA']).get(API + 'announcements/received/')
        self.assertNotIn(created.data['id'], [row['id'] for row in received_lga.data['results']])


class LocationFullListTests(TestCase):
    def test_pagination_class_page_size(self):
        from rest_api.pagination import LargeListPagination
        from rest_api.views import LGAListView, WardListView, ZoneListView
        for view in (ZoneListView, LGAListView, WardListView):
            self.assertIs(view.pagination_class, LargeListPagination)
        self.assertEqual(LargeListPagination.page_size, 500)

    def test_full_directory_in_one_page(self):
        zones = [Zone.objects.create(name=f'Full Zone {i}') for i in range(3)]
        lgas = []
        for i in range(21):
            lgas.append(LGA(name=f'Full LGA {i}', zone=zones[i % 3]))
        LGA.objects.bulk_create(lgas)
        lgas = list(LGA.objects.all())
        wards = []
        for i in range(225):
            wards.append(Ward(name=f'Full Ward {i}', lga=lgas[i % 21]))
        Ward.objects.bulk_create(wards)
        client = APIClient()
        for path, expected in (('locations/zones/', 3), ('locations/lgas/', 21),
                               ('locations/wards/', 225)):
            response = client.get(API + path)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.data['count'], expected)
            self.assertEqual(len(response.data['results']), expected)
            self.assertIsNone(response.data['next'])


class RegisterGenderTests(TestCase):
    def setUp(self):
        self.zone, self.lga, self.ward = geo()
        self.rd, _ = RoleDefinition.objects.get_or_create(
            tier='LGA', title='LGA Administrative Officer',
            defaults={'seat_number': 2})

    def image(self):
        out = io.BytesIO()
        Image.new('RGB', (16, 16), 'green').save(out, 'PNG')
        return SimpleUploadedFile('reg205.png', out.getvalue(), content_type='image/png')

    def register(self, username, gender):
        return APIClient().post(API + 'auth/register/', {
            'username': username, 'password': 'LocalOnly-Reg-205!',
            'password_confirm': 'LocalOnly-Reg-205!',
            'email': f'{username}@example.invalid', 'first_name': 'Reg',
            'last_name': 'Gender', 'phone': f'phone-{username}',
            'gender': gender, 'photo': self.image(), 'zone': self.zone.pk,
            'lga': self.lga.pk, 'role_definition': self.rd.pk,
        }, format='multipart')

    def test_full_word_female_normalised(self):
        response = self.register('reg205_female', 'FEMALE')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.get(username='reg205_female').gender, 'F')

    def test_mixed_case_male_normalised(self):
        response = self.register('reg205_male', 'Male')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.get(username='reg205_male').gender, 'M')

    def test_code_still_accepted_and_invalid_rejected(self):
        response = self.register('reg205_code', 'F')
        self.assertEqual(response.status_code, 201, response.content)
        response = self.register('reg205_bad', 'X')
        self.assertEqual(response.status_code, 400, response.content)
