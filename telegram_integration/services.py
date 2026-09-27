"""
KPN Telegram Membership Verification Service
============================================
Single reusable service for all Telegram membership verification.
All parts of the website MUST use this service.
Do NOT duplicate this logic elsewhere.
"""

import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('telegram_integration')


def get_bot_token():
    """Return the configured Telegram bot token."""
    return getattr(settings, 'TELEGRAM_BOT_TOKEN', '')


def get_channel_id():
    """Return the configured KPN Telegram channel ID."""
    return getattr(settings, 'TELEGRAM_CHANNEL_ID', '@officialkpn')


def call_telegram_api(method: str, params: dict = None, timeout: int = 10) -> dict:
    """
    Make a call to the Telegram Bot API.
    Returns the response dict or raises on error.
    """
    token = get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        response = requests.post(url, json=params or {}, timeout=timeout)
        data = response.json()
        return data
    except requests.RequestException as e:
        logger.error(f"Telegram API request failed ({method}): {e}")
        raise


def verify_telegram_membership(telegram_user_id: int) -> dict:
    """
    Core verification service. Call this everywhere membership verification is needed.

    Calls Telegram getChatMember for the configured KPN channel.
    Updates TelegramMembership record.
    Returns result dict:
    {
        'success': bool,
        'is_member': bool,
        'status': str (telegram status string),
        'error': str (if success=False),
        'membership': TelegramMembership instance or None
    }

    IMPORTANT: This only verifies Telegram channel membership.
    It does NOT affect KPN approval status.
    """
    from .models import TelegramMembership

    result = {
        'success': False,
        'is_member': False,
        'status': 'not_member',
        'error': None,
        'membership': None,
    }

    token = get_bot_token()
    channel_id = get_channel_id()

    if not token:
        result['error'] = 'Telegram bot token not configured. Contact administrator.'
        logger.error("verify_telegram_membership called but TELEGRAM_BOT_TOKEN not set.")
        return result

    if not channel_id:
        result['error'] = 'KPN Telegram channel not configured. Contact administrator.'
        logger.error("verify_telegram_membership called but TELEGRAM_CHANNEL_ID not set.")
        return result

    now = timezone.now()

    try:
        data = call_telegram_api('getChatMember', {
            'chat_id': channel_id,
            'user_id': telegram_user_id,
        })
    except RuntimeError as e:
        result['error'] = str(e)
        return result
    except Exception as e:
        result['error'] = f"Telegram API unavailable. Please try again later."
        logger.error(f"getChatMember failed for {telegram_user_id}: {e}")
        return result

    if not data.get('ok'):
        error_code = data.get('error_code', 0)
        description = data.get('description', 'Unknown Telegram API error')

        # 400 usually means user not found in channel context
        if error_code == 400:
            result['status'] = 'not_member'
            result['error'] = 'User is not found in the KPN Telegram channel.'
        elif error_code == 403:
            result['error'] = 'Bot is not an administrator of the channel. Contact KPN admin.'
            logger.error(f"Bot not admin of channel {channel_id}: {description}")
        else:
            result['error'] = f"Telegram error: {description}"
            logger.warning(f"getChatMember non-ok for {telegram_user_id}: {data}")

        # Update last_checked_at if we have a record
        try:
            tm = TelegramMembership.objects.get(telegram_user_id=telegram_user_id)
            tm.last_checked_at = now
            tm.save(update_fields=['last_checked_at', 'updated_at'])
            result['membership'] = tm
        except TelegramMembership.DoesNotExist:
            pass

        return result

    # Parse successful response
    member_info = data.get('result', {})
    tg_status = member_info.get('status', 'not_member')
    result['success'] = True
    result['status'] = tg_status

    # Determine if this is an active member
    # For 'restricted' users, Telegram includes 'is_member' field
    is_active = False
    if tg_status in ('creator', 'administrator', 'member'):
        is_active = True
    elif tg_status == 'restricted':
        # restricted users may still be members if is_member=True
        is_active = member_info.get('is_member', False)
    elif tg_status in ('left', 'kicked'):
        is_active = False

    result['is_member'] = is_active

    # Update or note the TelegramMembership record
    try:
        tm = TelegramMembership.objects.get(telegram_user_id=telegram_user_id)
        old_verified = tm.is_verified
        tm.telegram_status = tg_status
        tm.is_verified = is_active
        tm.last_checked_at = now

        if is_active:
            tm.last_verified_at = now
            if not tm.first_verified_at:
                tm.first_verified_at = now
            tm.left_at = None  # clear left_at if re-verified
        else:
            if old_verified and not tm.left_at:
                # Was verified, now not — record when we detected the leave
                tm.left_at = now

        tm.save(update_fields=[
            'telegram_status', 'is_verified', 'last_checked_at',
            'last_verified_at', 'first_verified_at', 'left_at', 'updated_at'
        ])
        result['membership'] = tm
        logger.info(
            f"Telegram verification for user_id={telegram_user_id}: "
            f"status={tg_status}, is_member={is_active}"
        )
    except TelegramMembership.DoesNotExist:
        # No linked KPN account — just return the result without updating
        logger.info(
            f"getChatMember check for unlinked Telegram user {telegram_user_id}: "
            f"status={tg_status}"
        )

    return result


def create_or_update_telegram_membership(kpn_user, telegram_data: dict) -> 'TelegramMembership':
    """
    Create or update a TelegramMembership record from Telegram Login Widget callback data.

    telegram_data should contain: id, first_name, last_name, username, auth_date, hash
    (already validated server-side before calling this function)

    Returns the TelegramMembership instance.
    Raises ValueError if the Telegram account is already linked to a different KPN user.
    """
    from .models import TelegramMembership

    tg_user_id = int(telegram_data['id'])

    # Check if this Telegram ID is already linked to a DIFFERENT KPN user
    try:
        existing = TelegramMembership.objects.get(telegram_user_id=tg_user_id)
        if existing.user_id != kpn_user.pk:
            raise ValueError(
                f"This Telegram account is already linked to another KPN member. "
                f"Each Telegram account can only be connected to one KPN account."
            )
        # Same user — update the record
        tm = existing
    except TelegramMembership.DoesNotExist:
        tm = TelegramMembership(user=kpn_user, telegram_user_id=tg_user_id)

    tm.telegram_username = telegram_data.get('username', '')
    tm.telegram_first_name = telegram_data.get('first_name', '')
    tm.telegram_last_name = telegram_data.get('last_name', '')
    tm.telegram_photo_url = telegram_data.get('photo_url', '')
    tm.save()

    logger.info(
        f"Telegram linked: KPN user {kpn_user.username} ↔ "
        f"Telegram {tg_user_id} (@{tm.telegram_username})"
    )

    # Immediately verify channel membership
    verify_telegram_membership(tg_user_id)

    # Reload to get updated values
    tm.refresh_from_db()
    return tm


def send_telegram_message(chat_id, text: str, parse_mode: str = 'HTML',
                           reply_markup: dict = None) -> dict:
    """
    Send a message to a Telegram chat/user.
    Returns the Telegram API response.
    """
    params = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
    }
    if reply_markup:
        params['reply_markup'] = reply_markup

    try:
        return call_telegram_api('sendMessage', params)
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        return {'ok': False, 'error': str(e)}


def set_webhook(webhook_url: str, secret_token: str = None) -> dict:
    """
    Register the Django webhook URL with the Telegram Bot API.
    Call this once during deployment setup.
    """
    params = {'url': webhook_url}
    if secret_token:
        params['secret_token'] = secret_token
    params['allowed_updates'] = ['message', 'chat_member', 'my_chat_member', 'callback_query']
    return call_telegram_api('setWebhook', params)


def get_webhook_info() -> dict:
    """Get current webhook configuration from Telegram."""
    return call_telegram_api('getWebhookInfo')
