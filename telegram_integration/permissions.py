"""
KPN Dashboard Access Permission Check
======================================
SINGLE SOURCE OF TRUTH for dashboard access decisions.
Import and call check_dashboard_access(user) in views.
NEVER duplicate this logic in templates or other views.
"""

from django.conf import settings
from leadership.roles import TELEGRAM_REQUIRED_ROLE_TITLES as CANONICAL_TELEGRAM_REQUIRED_ROLES


# These role titles REQUIRE Telegram verification before dashboard access.
# Sourced from KPN spec §2 Category A.
TELEGRAM_REQUIRED_ROLE_TITLES = tuple(getattr(settings, 'TELEGRAM_REQUIRED_ROLE_TITLES', CANONICAL_TELEGRAM_REQUIRED_ROLES))


def get_telegram_status(user):
    """
    Return Telegram connection status for a user.
    Returns a dict with:
      connected: bool  — has a TelegramMembership record
      is_active: bool  — is_verified=True (active channel member)
      membership: TelegramMembership or None
    """
    try:
        tm = user.telegram_membership
        return {
            'connected': True,
            'is_active': tm.is_verified,
            'membership': tm,
        }
    except Exception:
        return {
            'connected': False,
            'is_active': False,
            'membership': None,
        }


def requires_telegram(user) -> bool:
    """Return True if this user's role requires Telegram verification for dashboard access."""
    if not user.role_definition:
        return False
    return user.role_definition.title in TELEGRAM_REQUIRED_ROLE_TITLES


def check_dashboard_access(user) -> dict:
    """
    Central dashboard access check.

    Returns:
    {
        'allowed': bool,
        'reason': str,
            Possible values:
            'not_verified'       — account not yet KPN-approved (status != VERIFIED)
            'telegram_required'  — leadership role needs Telegram, not yet verified
            'ok'                 — access granted
        'telegram_active': bool,
        'telegram_required': bool,
        'telegram_status': dict,  — from get_telegram_status()
    }

    IMPORTANT:
    - KPN approval (VERIFIED status) and Telegram verification are SEPARATE concerns.
    - Telegram verification never grants KPN approval.
    - Only VERIFIED members reach the Telegram check.
    """
    tg_status = get_telegram_status(user)
    tg_required = requires_telegram(user)

    if user.status != 'VERIFIED':
        return {
            'allowed': False,
            'reason': 'not_verified',
            'telegram_active': tg_status['is_active'],
            'telegram_required': tg_required,
            'telegram_status': tg_status,
        }

    if tg_required and not tg_status['is_active']:
        return {
            'allowed': False,
            'reason': 'telegram_required',
            'telegram_active': False,
            'telegram_required': True,
            'telegram_status': tg_status,
        }

    return {
        'allowed': True,
        'reason': 'ok',
        'telegram_active': tg_status['is_active'],
        'telegram_required': tg_required,
        'telegram_status': tg_status,
    }
