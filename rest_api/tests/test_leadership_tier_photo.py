"""2.0.6 regression locks: leadership tier filtering + profile photos.

No production API code changed in the Android 2.0.6 round: the public
leadership endpoint already filters seats server-side by the role
definition's tier and already projects each holder's profile photo, and
the auth/me payload already carries the signed-in member's photo. These
tests pin that behaviour so a future change cannot silently drop it —
the app depends on it for the Leadership Ward/LGA tier filter and for
the Me / Leadership / Leader Profile avatars (initials are only the
in-app fallback when a member has no photo).
"""
from django.test import TestCase
from rest_framework.test import APIClient

from leadership.models import LGA, RoleDefinition, Ward
from staff.models import User


class LeadershipTierAndPhotoTests(TestCase):
    def setUp(self):
        from intelligence.tests.helpers import seed_directory
        seed_directory()
        self.client = APIClient()
        self.jega = LGA.objects.get(name='Jega')
        self.ward, _ = Ward.objects.get_or_create(
            name='Tier Test Ward', lga=self.jega)
        state_role, _ = RoleDefinition.objects.get_or_create(
            tier='STATE', title='President', defaults={'seat_number': 1})
        lga_role, _ = RoleDefinition.objects.get_or_create(
            tier='LGA', title='LGA Network Lead', defaults={'seat_number': 1})
        ward_role, _ = RoleDefinition.objects.get_or_create(
            tier='WARD', title='Ward Community Lead', defaults={'seat_number': 1})
        self.state_holder = User.objects.create_user(
            username='tier_state_holder', password='x', role='STATE',
            status='VERIFIED', role_definition=state_role,
            first_name='State', last_name='Holder', phone='tier-state')
        self.state_holder.photo = 'profile_photos/state-holder.jpg'
        self.state_holder.save(update_fields=['photo'])
        self.lga_holder = User.objects.create_user(
            username='tier_lga_holder', password='x', role='LGA',
            status='VERIFIED', role_definition=lga_role, lga=self.jega,
            first_name='Lga', last_name='Holder', phone='tier-lga')
        self.lga_holder.photo = 'profile_photos/lga-holder.jpg'
        self.lga_holder.save(update_fields=['photo'])
        self.ward_holder = User.objects.create_user(
            username='tier_ward_holder', password='x', role='WARD',
            status='VERIFIED', role_definition=ward_role, lga=self.jega,
            ward=self.ward, first_name='Ward', last_name='Holder',
            phone='tier-ward')
        self.ward_holder.photo = 'profile_photos/ward-holder.jpg'
        self.ward_holder.save(update_fields=['photo'])

    def seats(self, **params):
        response = self.client.get('/api/v1/leadership/', params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data['results']

    def test_state_tier_returns_only_state_seats_with_holder_photo(self):
        rows = self.seats(tier='STATE', status='FILLED')
        self.assertTrue(rows)
        self.assertTrue(all(row['tier'] == 'STATE' for row in rows))
        mine = [r for r in rows if r['holder'] and r['holder']['id'] == self.state_holder.id]
        self.assertEqual(len(mine), 1)
        self.assertIn('profile_photos/state-holder.jpg', mine[0]['holder']['photo'])

    def test_lga_tier_returns_only_lga_seats_with_holder_photo(self):
        rows = self.seats(tier='LGA', status='FILLED')
        self.assertTrue(rows)
        self.assertTrue(all(row['tier'] == 'LGA' for row in rows))
        mine = [r for r in rows if r['holder'] and r['holder']['id'] == self.lga_holder.id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['location']['lga'], self.jega.id)
        self.assertIn('profile_photos/lga-holder.jpg', mine[0]['holder']['photo'])

    def test_ward_tier_returns_only_ward_seats_with_holder_photo(self):
        rows = self.seats(tier='WARD', status='FILLED')
        self.assertTrue(rows)
        self.assertTrue(all(row['tier'] == 'WARD' for row in rows))
        mine = [r for r in rows if r['holder'] and r['holder']['id'] == self.ward_holder.id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['location']['ward'], self.ward.id)
        self.assertIn('profile_photos/ward-holder.jpg', mine[0]['holder']['photo'])

    def test_holder_without_photo_serializes_null_photo(self):
        self.lga_holder.photo = None
        self.lga_holder.save(update_fields=['photo'])
        rows = self.seats(tier='LGA', status='FILLED')
        mine = [r for r in rows if r['holder'] and r['holder']['id'] == self.lga_holder.id]
        self.assertEqual(len(mine), 1)
        self.assertIsNone(mine[0]['holder']['photo'])

    def test_me_payload_carries_member_photo(self):
        self.client.force_authenticate(self.state_holder)
        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('profile_photos/state-holder.jpg', response.data['photo'] or '')

    def test_leader_detail_payload_carries_photo(self):
        response = self.client.get(f'/api/v1/leadership/people/{self.lga_holder.id}/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('profile_photos/lga-holder.jpg', response.data['photo'] or '')
