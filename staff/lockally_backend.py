"""
KPN Lockally Email Backend
==========================
A Django email backend that delivers email through the Lockally Sending API.

Environment variables required:
    LOCKALLY_API_KEY      — API key with send:write permission
    LOCKALLY_API_URL      — Full API endpoint URL (e.g. https://api.lockally.com/v1/send)
    LOCKALLY_FROM_EMAIL   — Sender email address
    LOCKALLY_FROM_NAME    — Sender display name (e.g. "KPN - Kebbi Progressive Network")

Security notes:
    - The API key is NEVER written to logs.
    - A failed delivery logs only the sanitized error message and HTTP status code.
    - Provider details are never exposed to end users.
"""

import logging
import requests
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings

logger = logging.getLogger(__name__)


class LockallyEmailBackend(BaseEmailBackend):
    """
    Sends email via the Lockally Sending API (POST JSON).
    Falls back gracefully on failure without exposing credentials.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_url = getattr(settings, 'LOCKALLY_API_URL', '')
        self.api_key = getattr(settings, 'LOCKALLY_API_KEY', '')
        self.from_email = getattr(settings, 'LOCKALLY_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)
        self.from_name = getattr(settings, 'LOCKALLY_FROM_NAME', 'KPN')

    def _send_single(self, email_message):
        """
        Sends one EmailMessage via Lockally API.
        Returns True on success, False on failure.
        Never logs the API key.
        """
        if not self.api_url or not self.api_key:
            logger.error(
                'Lockally email backend: LOCKALLY_API_URL or LOCKALLY_API_KEY is not configured. '
                'Set both environment variables to enable email delivery.'
            )
            if not self.fail_silently:
                raise RuntimeError(
                    'Lockally email backend is not configured. '
                    'Set LOCKALLY_API_URL and LOCKALLY_API_KEY environment variables.'
                )
            return False

        # Build the payload — uses Lockally's transactional send format
        # The body may be HTML or plain text; prefer HTML if provided
        html_body = None
        text_body = None

        if hasattr(email_message, 'alternatives'):
            for content, mimetype in email_message.alternatives:
                if mimetype == 'text/html':
                    html_body = content
                    break

        if html_body is None:
            text_body = email_message.body
        else:
            text_body = email_message.body  # Also send plain text as fallback

        payload = {
            'from': {
                'email': self.from_email,
                'name': self.from_name,
            },
            'to': [{'email': addr} for addr in email_message.to],
            'subject': email_message.subject,
            'text': text_body,
        }

        if html_body:
            payload['html'] = html_body

        # Include CC and BCC if present
        if email_message.cc:
            payload['cc'] = [{'email': addr} for addr in email_message.cc]
        if email_message.bcc:
            payload['bcc'] = [{'email': addr} for addr in email_message.bcc]

        # Send the request — auth via Bearer token in header
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                timeout=15,
            )

            if response.status_code in (200, 201, 202):
                logger.info(
                    'Lockally: Email sent successfully to %d recipient(s). Subject: "%s"',
                    len(email_message.to),
                    email_message.subject,
                )
                return True
            else:
                # Log status code only, never the API key
                logger.error(
                    'Lockally: Email delivery failed. HTTP %d. Subject: "%s". '
                    'Recipients: %d. Check Lockally dashboard for details.',
                    response.status_code,
                    email_message.subject,
                    len(email_message.to),
                )
                if not self.fail_silently:
                    raise RuntimeError(
                        f'Lockally email delivery failed with HTTP {response.status_code}.'
                    )
                return False

        except requests.Timeout:
            logger.error(
                'Lockally: Request timed out after 15s. Subject: "%s".',
                email_message.subject,
            )
            if not self.fail_silently:
                raise
            return False

        except requests.ConnectionError:
            logger.error(
                'Lockally: Could not connect to sending API. Subject: "%s". '
                'Check LOCKALLY_API_URL configuration.',
                email_message.subject,
            )
            if not self.fail_silently:
                raise
            return False

        except Exception as exc:
            # Log the exception type and message, but never API key or credentials
            logger.error(
                'Lockally: Unexpected error sending email. Subject: "%s". Error type: %s.',
                email_message.subject,
                type(exc).__name__,
            )
            if not self.fail_silently:
                raise
            return False

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects.
        Returns the number of emails successfully sent.
        """
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            try:
                if self._send_single(message):
                    sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent_count
