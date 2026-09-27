"""
KPN Telegram Integration Views
==============================
Handles Telegram Login Widget flows and Webhook receiving.
"""

import hashlib
import hmac
import time
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.contrib import messages
from django.conf import settings

from .models import TelegramMembership
from .services import verify_telegram_membership, create_or_update_telegram_membership
from .webhook import process_webhook_update


def check_telegram_auth_hash(data: dict) -> bool:
    """
    Validates the data received from the Telegram Login Widget.
    Uses HMAC-SHA256 based on the bot token as described in Telegram docs.
    """
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return False

    # The hash provided by Telegram
    received_hash = data.get('hash')
    if not received_hash:
        return False

    # Collect all data fields except 'hash', sort them alphabetically
    data_check_arr = []
    for key, value in data.items():
        if key != 'hash':
            data_check_arr.append(f"{key}={value}")
    
    data_check_arr.sort()
    data_check_string = '\n'.join(data_check_arr)

    # SHA256 of the bot token is used as the secret key
    secret_key = hashlib.sha256(bot_token.encode('utf-8')).digest()
    
    # Calculate HMAC-SHA256 signature
    calculated_hash = hmac.new(
        secret_key, 
        data_check_string.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()

    return calculated_hash == received_hash


@login_required
def telegram_connect(request):
    """
    Page displaying the Telegram Login Widget for users to link their account.
    """
    bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'KPNKebbiBot') # Provide default or from env
    
    # Check if already connected
    try:
        tm = request.user.telegram_membership
        if tm.is_verified:
            messages.info(request, "Your Telegram account is already connected and verified.")
            return redirect('staff:dashboard')
    except TelegramMembership.DoesNotExist:
        pass

    context = {
        'bot_username': bot_username,
        # Callback URL needs to be absolute or relative path, Widget handles it.
        # But Telegram Widget requires the domain to be set up in BotFather via /setdomain
    }
    return render(request, 'telegram_integration/connect.html', context)


@login_required
def telegram_callback(request):
    """
    Handles the callback from the Telegram Login Widget.
    """
    # Telegram sends data via GET parameters
    tg_data = request.GET.dict()
    
    if not tg_data or 'id' not in tg_data or 'hash' not in tg_data:
        messages.error(request, "Invalid data received from Telegram.")
        return redirect('telegram_integration:connect')

    # Validate data integrity
    if not check_telegram_auth_hash(tg_data):
        messages.error(request, "Telegram authentication failed. Invalid signature.")
        return redirect('telegram_integration:connect')

    # Check expiration (24 hours)
    auth_date = int(tg_data.get('auth_date', 0))
    if time.time() - auth_date > 86400:
        messages.error(request, "Telegram login session expired. Please try again.")
        return redirect('telegram_integration:connect')

    try:
        # Create or update membership
        tm = create_or_update_telegram_membership(request.user, tg_data)
        
        if tm.is_verified:
            messages.success(request, f"Successfully linked and verified Telegram account @{tm.telegram_username}!")
        else:
            messages.warning(request, f"Telegram account linked, but you are not currently an active member of the KPN Channel. Please join the channel.")
            
        return redirect('staff:dashboard')
        
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('telegram_integration:connect')
    except Exception as e:
        messages.error(request, f"An error occurred while linking Telegram: {e}")
        return redirect('telegram_integration:connect')


@login_required
def telegram_verify(request):
    """
    Manually triggers a re-verification of the user's Telegram membership status.
    Useful if they just joined the channel and want immediate access.
    """
    try:
        tm = request.user.telegram_membership
    except TelegramMembership.DoesNotExist:
        messages.error(request, "You must link your Telegram account first.")
        return redirect('telegram_integration:connect')

    result = verify_telegram_membership(tm.telegram_user_id)
    
    if not result['success']:
        messages.error(request, f"Verification failed: {result['error']}")
    elif result['is_member']:
        messages.success(request, "Your Telegram channel membership has been verified!")
    else:
        messages.warning(request, f"You are not an active member of the KPN Telegram channel. Status: {result['status']}")

    return redirect('staff:dashboard')


@login_required
@require_POST
def telegram_disconnect(request):
    """
    Unlinks the Telegram account from the KPN profile.
    """
    try:
        request.user.telegram_membership.delete()
        messages.success(request, "Your Telegram account has been disconnected.")
    except TelegramMembership.DoesNotExist:
        messages.info(request, "You don't have a connected Telegram account.")
        
    return redirect('staff:dashboard')


@csrf_exempt
@require_POST
def webhook_handler(request):
    """
    Endpoint for Telegram Bot API to send updates.
    """
    success = process_webhook_update(request)
    if success:
        return HttpResponse("OK")
    else:
        return HttpResponseBadRequest("Invalid Request")
