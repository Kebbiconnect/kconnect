from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.mail import get_connection
from django.conf import settings
from rest_framework.test import APIClient
from staff.models import User

class EmailSafetyTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.user=User.objects.create_user(username='qa_email',phone='qa_email',email='qa@example.invalid',status='VERIFIED')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',EMAIL_TIMEOUT=10)
    def test_smtp_connection_has_bounded_timeout(self):
        self.assertEqual(get_connection().timeout,10)

    @patch('rest_api.auth.send_mail',side_effect=TimeoutError('private provider value'))
    def test_reset_provider_timeout_returns_503_without_private_details(self,send):
        response=self.client.post('/api/v1/auth/password-reset/',{'email':self.user.email},format='json')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private provider value',str(response.data))

    @override_settings(CONTACT_RECIPIENT_EMAIL='staging@example.invalid')
    @patch('rest_api.workflow_views.send_mail',return_value=1)
    def test_contact_uses_configured_staging_recipient(self,send):
        response=self.client.post('/api/v1/content/contact/',{'name':'QA only','email':'qa@example.invalid','message':'Synthetic'},format='json')
        self.assertEqual(response.status_code,201)
        self.assertEqual(send.call_args.args[3],['staging@example.invalid'])

    @patch('rest_api.workflow_views.send_mail',side_effect=TimeoutError('private provider value'))
    def test_contact_provider_failure_returns_503_not_false_success(self,send):
        response=self.client.post('/api/v1/content/contact/',{'name':'QA only','email':'qa@example.invalid','message':'Synthetic'},format='json')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private provider value',str(response.data))
