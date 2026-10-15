from django.test import TestCase
from rest_framework.test import APIClient

class ReleaseAuthInputTests(TestCase):
    def test_reset_request_rejects_non_email_values(self):
        client=APIClient()
        for value in (None,[],{},'not-an-email'):
            with self.subTest(value=value):
                response=client.post('/api/v1/auth/password-reset/',{'email':value},format='json')
                self.assertEqual(response.status_code,400)
    def test_reset_confirmation_rejects_structured_passwords(self):
        client=APIClient()
        for value in (None,[],{},''):
            with self.subTest(value=value):
                response=client.post('/api/v1/auth/password-reset/confirm/',{'uid':'bad','token':'bad','new_password':value},format='json')
                self.assertEqual(response.status_code,400)
