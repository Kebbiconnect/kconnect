"""ID tag monthly limit (API surface): GET account/id-tag/ returns
429 with the limit message once the account has generated a tag in
the current calendar month (Africa/Lagos)."""
from django.utils import timezone

from staff.id_tags import current_month_window, limit_message
from staff.models import IdTagGeneration

from .test_staff_api import StaffApiCase

API = '/api/v1/'
URL = API + 'account/id-tag/'


class IdTagLimitApiTests(StaffApiCase):
    def test_first_generation_succeeds_and_logs_one_row(self):
        response = self.client_for(self.director).get(URL)
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            IdTagGeneration.objects.filter(user=self.director).count(), 1)

    def test_second_generation_same_month_is_429_with_detail(self):
        client = self.client_for(self.director)
        first = client.get(URL)
        self.assertEqual(first.status_code, 200, first.content[:200])
        second = client.get(URL)
        self.assertEqual(second.status_code, 429, second.content[:500])
        self.assertEqual(second.data['detail'], limit_message())
        self.assertNotEqual(
            second.get('Content-Type', ''), 'application/pdf')
        self.assertEqual(
            IdTagGeneration.objects.filter(user=self.director).count(), 1)

    def test_last_month_row_does_not_block(self):
        row = IdTagGeneration.objects.create(user=self.director)
        start, _ = current_month_window()
        IdTagGeneration.objects.filter(pk=row.pk).update(
            generated_at=start - timezone.timedelta(days=1))
        response = self.client_for(self.director).get(URL)
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(
            IdTagGeneration.objects.filter(user=self.director).count(), 2)

    def test_general_member_still_blocked_403(self):
        response = self.client_for(self.member).get(URL)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            IdTagGeneration.objects.filter(user=self.member).exists())
