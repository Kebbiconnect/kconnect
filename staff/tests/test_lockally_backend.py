"""Lockally email backend contract tests.

The payload must match Lockally's documented POST /v1/send format:
`from` a plain string, `to`/`cc`/`bcc` arrays of strings, a required
Idempotency-Key header, and reply_to when the sender has no mailbox.
The pre-2026-10-30 backend sent objects and no Idempotency-Key, which
the API rejects — password-reset mail failed with correct credentials.
"""
from unittest import mock

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from staff.lockally_backend import LockallyEmailBackend


def fake_response(status_code=202, body=None):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = body or {'status': 'queued', 'id': 'x'}
    return response


@override_settings(
    LOCKALLY_API_KEY='lk_live_example',
    LOCKALLY_API_URL='https://api.lockally.com/v1/send',
    LOCKALLY_FROM_EMAIL='noreply@kpn.com.ng',
    LOCKALLY_FROM_NAME='KPN - Kebbi Progressive Youth Network',
    CONTACT_RECIPIENT_EMAIL='info@kpn.com.ng',
    DEFAULT_FROM_EMAIL='noreply@kpn.com.ng',
)
class LockallyBackendContractTests(SimpleTestCase):
    def _send(self, response):
        backend = LockallyEmailBackend()
        message = EmailMessage(
            subject='KPN Password Reset Request',
            body='Reset link here',
            to=['member@example.com'],
        )
        with mock.patch('staff.lockally_backend.requests.post',
                        return_value=response) as post:
            result = backend.send_messages([message])
        return result, post

    def test_payload_uses_documented_string_format(self):
        result, post = self._send(fake_response())
        self.assertEqual(result, 1)
        kwargs = post.call_args.kwargs
        payload = kwargs['json']
        self.assertEqual(payload['from'], 'noreply@kpn.com.ng')
        self.assertIsInstance(payload['from'], str)
        self.assertEqual(payload['to'], ['member@example.com'])
        self.assertEqual(payload['subject'], 'KPN Password Reset Request')
        self.assertEqual(payload['text'], 'Reset link here')
        # noreply@ has no mailbox, so reply_to must route to contact.
        self.assertEqual(payload['reply_to'], 'info@kpn.com.ng')
        headers = kwargs['headers']
        self.assertTrue(headers['Idempotency-Key'].startswith('kpn-'))
        self.assertEqual(headers['Authorization'], 'Bearer lk_live_example')

    def test_http_error_raises_with_status(self):
        with self.assertRaises(RuntimeError):
            self._send(fake_response(403, {'detail': 'Missing scope send:write'}))

    def test_suppressed_recipients_are_not_reported_as_sent(self):
        with self.assertRaises(RuntimeError):
            self._send(fake_response(200, {'status': 'suppressed'}))

    def test_test_key_send_still_counts_but_is_flagged(self):
        # 200 + delivered + @test.lockally.com message id = simulated.
        result, _post = self._send(fake_response(
            200, {'status': 'delivered',
                  'message_id': '<abc@test.lockally.com>'}))
        self.assertEqual(result, 1)

    @override_settings(LOCKALLY_API_KEY='', LOCKALLY_API_URL='')
    def test_missing_configuration_raises(self):
        backend = LockallyEmailBackend()
        message = EmailMessage(subject='x', body='y', to=['a@example.com'])
        with self.assertRaises(RuntimeError):
            backend.send_messages([message])
