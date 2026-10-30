"""
KPN Lockally Email Backend
==========================
A Django email backend that delivers email through the Lockally Sending API.

Environment variables required:
    LOCKALLY_API_KEY      — LIVE API key (lk_live_...) with send:write permission
    LOCKALLY_API_URL      — Full API endpoint URL (https://api.lockally.com/v1/send)
    LOCKALLY_FROM_EMAIL   — Sender email address on a domain VERIFIED in Lockally
    LOCKALLY_FROM_NAME    — Sender display name (e.g. "KPN - Kebbi Progressive Network")

The payload follows Lockally's documented POST /v1/send contract
(developers.lockally.com, checked 2026-10-30): `from` is a plain address
STRING, `to`/`cc`/`bcc` are arrays of address strings, an
`Idempotency-Key` header is REQUIRED on every call, and `reply_to` is
required when the sender address has no mailbox behind it (KPN sends
from noreply@, so replies are routed to CONTACT_RECIPIENT_EMAIL).
An earlier version of this backend sent `from`/`to` as objects and no
Idempotency-Key, which the API rejects — that broke password-reset mail
even with correct credentials (owner report 2026-10-30).

Security notes:
    - The API key is NEVER written to logs.
    - A failed delivery logs only the HTTP status code and the provider's
      problem detail (never credentials).
    - Provider details are never exposed to end users.
"""

import logging
import uuid
from email.utils import parseaddr

import requests
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings

logger = logging.getLogger(__name__)


def _bare_address(value):
    """Extract the bare addr-spec from 'Name <addr>' or return the input."""
    _name, addr = parseaddr(value or '')
    return addr or (value or '')


class LockallyEmailBackend(BaseEmailBackend):
    """
    Sends email via the Lockally Sending API (POST JSON).
    Raises delivery errors by default; never silently falls back to console or SMTP.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_url = getattr(settings, 'LOCKALLY_API_URL', '')
        self.api_key = getattr(settings, 'LOCKALLY_API_KEY', '')
        self.from_email = getattr(settings, 'LOCKALLY_FROM_EMAIL', '') or settings.DEFAULT_FROM_EMAIL
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

        # Build the payload in Lockally's documented format: plain
        # address strings everywhere (no {email, name} objects).
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
            'from': _bare_address(self.from_email),
            'to': [_bare_address(addr) for addr in email_message.to],
            'subject': email_message.subject,
            'text': text_body,
        }

        if html_body:
            payload['html'] = html_body

        # Include CC and BCC if present
        if email_message.cc:
            payload['cc'] = [_bare_address(addr) for addr in email_message.cc]
        if email_message.bcc:
            payload['bcc'] = [_bare_address(addr) for addr in email_message.bcc]

        # Lockally requires reply_to when the sender has no mailbox
        # behind it (e.g. noreply@). Honour the message's own reply-to
        # first, then fall back to the monitored contact address.
        reply_to = ''
        if getattr(email_message, 'reply_to', None):
            reply_to = _bare_address(email_message.reply_to[0])
        if not reply_to:
            reply_to = _bare_address(
                getattr(settings, 'CONTACT_RECIPIENT_EMAIL', '') or '')
        if reply_to:
            payload['reply_to'] = reply_to
            if self.from_name:
                payload['reply_to_name'] = self.from_name

        # Send the request — auth via Bearer token in header, plus the
        # Idempotency-Key header Lockally REQUIRES on every send.
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Idempotency-Key': f'kpn-{uuid.uuid4().hex}',
                },
                timeout=15,
            )

            if response.status_code in (200, 201, 202):
                # A 200 is NOT a queued delivery: per Lockally's docs it
                # means every recipient was suppressed, or a TEST key
                # simulated the send. Only 202 queues real mail.
                provider_status = ''
                message_id = ''
                try:
                    body = response.json()
                    provider_status = str(body.get('status', '') or '')
                    message_id = str(body.get('message_id', '') or '')
                except Exception:
                    pass
                if provider_status == 'suppressed':
                    logger.error(
                        'Lockally: All recipients suppressed; nothing was delivered. '
                        'Subject: "%s". Remove the address from the Lockally suppression list.',
                        email_message.subject,
                    )
                    if not self.fail_silently:
                        raise RuntimeError(
                            'Lockally suppressed all recipients; email was not delivered.')
                    return False
                if message_id.endswith('@test.lockally.com'):
                    logger.warning(
                        'Lockally: A TEST API key (lk_test_) is configured — the send was '
                        'SIMULATED and no email was delivered. Use a live lk_live_ key in production.'
                    )
                logger.info(
                    'Lockally: Email accepted by provider for %d recipient(s). '
                    'HTTP %d, provider status "%s". Subject: "%s"',
                    len(email_message.to),
                    response.status_code,
                    provider_status or 'accepted',
                    email_message.subject,
                )
                return True
            else:
                # Log status code + the provider's problem detail (RFC
                # 9457 — it names the exact cause: bad scope, unverified
                # domain, invalid field), never the API key.
                detail = ''
                try:
                    body = response.json()
                    detail = str(body.get('detail') or body.get('title') or '')[:300]
                except Exception:
                    pass
                logger.error(
                    'Lockally: Email delivery failed. HTTP %d. Subject: "%s". '
                    'Recipients: %d. Provider detail: %s',
                    response.status_code,
                    email_message.subject,
                    len(email_message.to),
                    detail or '(none returned)',
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
