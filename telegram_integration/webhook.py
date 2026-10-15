"""
KPN Telegram Webhook Processor
==============================
Validates and parses incoming Webhook POST requests from Telegram.
Routes data to bot.py handlers.
"""

import logging
import hmac
from django.conf import settings
from .bot import handle_message, handle_chat_member_update

logger = logging.getLogger('telegram_integration.webhook')

def process_webhook_update(request):
    """
    Validates the webhook secret token and routes the update payload.
    Called directly from the webhook view.
    """
    # Validate Secret Token (configured when setting the webhook)
    expected_token = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
    received_token=request.headers.get('X-Telegram-Bot-Api-Secret-Token','')
    if not expected_token or not hmac.compare_digest(received_token,expected_token):
        logger.warning('Webhook request rejected: missing or incorrect secret.')
        return False

    import json
    try:
        body = request.body.decode('utf-8')
        update = json.loads(body)
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        return False

    if not isinstance(update,dict):return False
    for kind in ('message','chat_member','my_chat_member'):
        if kind in update and not isinstance(update[kind],dict):return False

    # Route based on update type
    if 'message' in update:
        handle_message(update['message'])
    elif 'chat_member' in update:
        handle_chat_member_update(update['chat_member'])
    elif 'my_chat_member' in update:
        # Bot's own status changed (e.g. added/removed as admin)
        handle_chat_member_update(update['my_chat_member'])
    else:
        logger.debug(f"Unhandled webhook update type: {list(update.keys())}")

    return True
