"""Branded KPN transactional emails (v2.4.3).

Password-reset and membership-approval messages are sent as proper
HTML emails with a KPN header and a call-to-action button, plus a
plain-text fallback. Rendering uses Django templates under
staff/templates/staff/emails/; delivery goes through the configured
EMAIL_BACKEND (Lockally in production), which forwards the HTML part.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _site_url():
    return (getattr(settings, 'SITE_URL', '') or 'https://www.kpn.com.ng').rstrip('/')


def _send(to_email, subject, template_name, context, text_body):
    """Send one branded email; returns the number accepted (0 or 1).

    Raises on delivery failure so callers keep their existing error
    handling; a missing recipient address is a quiet no-op (returns 0).
    """
    if not to_email:
        return 0
    html_body = render_to_string(template_name, context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    message.attach_alternative(html_body, 'text/html')
    return message.send(fail_silently=False)


def send_password_reset_email(user, reset_link):
    full_name = user.get_full_name() or user.username
    site_url = _site_url()
    text_body = (
        f"Hello {full_name},\n\n"
        "You requested a password reset for your KPN account.\n\n"
        "Use the link below to set a new password. The link is valid for 24 hours:\n\n"
        f"{reset_link}\n\n"
        "If you did not request this reset, you can safely ignore this email.\n\n"
        "Best regards,\n"
        "Kebbi Progressive Youth Network (KPN)\n"
        f"{site_url}"
    )
    return _send(
        user.email,
        'Reset your KPN password',
        'staff/emails/password_reset.html',
        {'full_name': full_name, 'reset_link': reset_link, 'site_url': site_url},
        text_body,
    )


def send_account_approved_email(user):
    full_name = user.get_full_name() or user.username
    site_url = _site_url()
    role_title = ''
    if getattr(user, 'role_definition_id', None):
        role_title = user.role_definition.title
    dashboard_url = f'{site_url}/account/dashboard/'
    role_line = f"Your approved role: {role_title}.\n\n" if role_title else ''
    text_body = (
        f"Hello {full_name},\n\n"
        "Congratulations! Your application to join the Kebbi Progressive "
        "Youth Network (KPN) has been approved.\n\n"
        f"{role_line}"
        "You can now sign in and open your dashboard:\n\n"
        f"{dashboard_url}\n\n"
        "Welcome to the network. One Voice, One Change.\n\n"
        "Best regards,\n"
        "Kebbi Progressive Youth Network (KPN)\n"
        f"{site_url}"
    )
    return _send(
        user.email,
        'Your KPN membership has been approved',
        'staff/emails/account_approved.html',
        {'full_name': full_name, 'role_title': role_title,
         'dashboard_url': dashboard_url, 'site_url': site_url},
        text_body,
    )
