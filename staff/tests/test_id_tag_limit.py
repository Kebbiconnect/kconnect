"""ID tag monthly limit (web surface) and full-quality PDF check.

One generation per account per calendar month (Africa/Lagos),
enforced in staff.views.generate_id_tag; successful generations are
logged as staff.IdTagGeneration rows. The PDF is embedded at full
quality (PNG) — the round-4 400 KB cap was lifted by the owner on
2026-11-25 because the app cache lives on the phone, not in a
database.
"""
import os
from io import BytesIO

from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from staff.id_tags import (
    current_month_window, limit_message, next_available_date,
)
from staff.models import IdTagGeneration, User

URL = reverse('staff:generate_id_tag')
DASHBOARD = reverse('staff:dashboard')


def make_member(username, role='STATE'):
    return User.objects.create_user(
        username=username, password='unused-test-password',
        phone=username, status='VERIFIED', role=role,
        first_name='Test', last_name='Member')


def noisy_photo_bytes():
    """A large, noisy JPEG (random pixels — incompressible), like a
    real camera photo, generated in-test with PIL."""
    from PIL import Image
    image = Image.frombytes('RGB', (900, 1100), os.urandom(900 * 1100 * 3))
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=95)
    return buffer.getvalue()


class IdTagLimitWebTests(TestCase):
    def setUp(self):
        self.user = make_member('idtag_leader')

    def messages_of(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_first_generation_succeeds_and_logs_one_row(self):
        self.client.force_login(self.user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        body = b''.join(response.streaming_content) \
            if response.streaming else response.content
        self.assertTrue(body.startswith(b'%PDF'))
        self.assertEqual(
            IdTagGeneration.objects.filter(user=self.user).count(), 1)

    def test_second_generation_same_month_refused_on_web(self):
        self.client.force_login(self.user)
        first = self.client.get(URL)
        self.assertEqual(first.status_code, 200)
        second = self.client.get(URL)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(second.url, DASHBOARD)
        self.assertIn(limit_message(), self.messages_of(second))
        self.assertNotEqual(
            second.get('Content-Type', ''), 'application/pdf')
        # No second log row (and therefore no second PDF was produced
        # and recorded).
        self.assertEqual(
            IdTagGeneration.objects.filter(user=self.user).count(), 1)

    def test_last_month_row_does_not_block_this_month(self):
        row = IdTagGeneration.objects.create(user=self.user)
        start, _ = current_month_window()
        IdTagGeneration.objects.filter(pk=row.pk).update(
            generated_at=start - timezone.timedelta(days=1))
        self.client.force_login(self.user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            IdTagGeneration.objects.filter(user=self.user).count(), 2)

    def test_general_member_block_still_works(self):
        general = make_member('idtag_general', role='GENERAL')
        self.client.force_login(general)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, DASHBOARD)
        self.assertIn(
            'General members are not authorized to generate ID cards.',
            self.messages_of(response))
        self.assertFalse(
            IdTagGeneration.objects.filter(user=general).exists())

    def test_limit_message_names_first_of_next_month_without_leading_zero(self):
        nxt = next_available_date()
        self.assertEqual(nxt.day, 1)
        self.assertEqual(
            limit_message(),
            'You have already generated your ID tag this month. '
            f'You can generate a new one from {nxt.day} '
            f'{nxt.strftime("%B")} {nxt.year}.')


class IdTagPdfSizeTests(TestCase):
    def test_pdf_with_noisy_photo_is_full_quality(self):
        """The cards are embedded as full-quality PNG again (owner
        lifted the 400 KB cap on 2026-11-25). The compressed round-4
        build produced 319,762 bytes for this same fixture; the
        restored build must be clearly larger than that (the original
        full-quality build measured 461,605 bytes) while staying in a
        sane band for a two-page tag (well under 2 MB)."""
        user = make_member('idtag_photo')
        user.photo.save(
            'idtag-noisy-photo.jpg',
            ContentFile(noisy_photo_bytes()), save=True)
        self.addCleanup(self._remove_photo, user)

        self.client.force_login(user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content) \
            if response.streaming else response.content
        self.assertTrue(body.startswith(b'%PDF'))
        self.assertGreater(len(body), 319762)
        self.assertLess(len(body), 2 * 1024 * 1024)

    @staticmethod
    def _remove_photo(user):
        try:
            if user.photo:
                user.photo.delete(save=False)
        except Exception:
            pass
