"""
KPN Telegram Bot Handlers
=========================
Processes commands and messages received via the Telegram Webhook.
"""

import logging
from django.utils import timezone
from .models import TelegramMembership, KPNMeeting, MeetingAttendance
from .services import send_telegram_message, verify_telegram_membership
from .ai import ask_kpn_assistant

logger = logging.getLogger('telegram_integration.bot')

def handle_message(message: dict):
    """
    Process an incoming Telegram message.
    Routes to specific command handlers or the AI assistant.
    """
    chat = message.get('chat', {})
    chat_id = chat.get('id')
    chat_type = chat.get('type')
    from_user = message.get('from', {})
    user_id = from_user.get('id')
    text = message.get('text', '').strip()

    if not chat_id or not text:
        return

    # In groups, only respond to explicit commands or mentions
    # For now, let's keep AI primarily in private chat, or via /ask command
    is_private = chat_type == 'private'

    if text.startswith('/'):
        # Parse command
        parts = text.split(maxsplit=1)
        command = parts[0].split('@')[0].lower() # handle /command@BotName
        args = parts[1] if len(parts) > 1 else ''

        if command == '/start':
            handle_start(chat_id, user_id, from_user.get('first_name', ''))
        elif command == '/help':
            handle_help(chat_id)
        elif command == '/verify' or command == '/membership':
            handle_verify(chat_id, user_id)
        elif command == '/meetings':
            handle_meetings(chat_id, user_id)
        elif command == '/present':
            handle_present(chat_id, user_id)
        elif command == '/kpn' or command == '/ask':
            # Force AI response for these commands even in groups
            handle_ai_query(chat_id, user_id, args)
        else:
            if is_private:
                send_telegram_message(
                    chat_id, 
                    "Unknown command. Type /help to see available KPN commands."
                )
    elif is_private:
        # In private chat, any non-command text goes to the AI assistant
        handle_ai_query(chat_id, user_id, text)


def handle_start(chat_id: int, user_id: int, first_name: str):
    """Handler for /start command"""
    text = (
        f"👋 Welcome to the official <b>Kebbi Progressive Youth Network (KPN)</b> Assistant, {first_name}!\n\n"
        "<i>\"One Voice, One Change.\"</i>\n\n"
        "I can help you with information about KPN, verify your membership status, and track meeting attendance.\n\n"
        "<b>Available Commands:</b>\n"
        "🟢 /verify - Check your KPN channel membership status\n"
        "🟢 /meetings - View upcoming KPN meetings\n"
        "🟢 /present - Mark yourself present at an active meeting\n"
        "🟢 /help - Show all commands\n\n"
        "You can also just type any question about KPN policies, structure, or guidelines here!"
    )
    send_telegram_message(chat_id, text)


def handle_help(chat_id: int):
    """Handler for /help command"""
    text = (
        "<b>KPN Assistant Help</b>\n\n"
        "<b>Membership</b>\n"
        "/verify - Check and update your channel membership status\n"
        "/membership - Same as /verify\n\n"
        "<b>Meetings</b>\n"
        "/meetings - List scheduled and active KPN meetings\n"
        "/present - Confirm your attendance for an active meeting\n\n"
        "<b>Information</b>\n"
        "/kpn [question] - Ask a specific question about KPN\n"
        "/help - Show this message\n\n"
        "<i>Note: If you have a KPN leadership role, you must link your Telegram account on the KPN website dashboard.</i>"
    )
    send_telegram_message(chat_id, text)


def handle_verify(chat_id: int, user_id: int):
    """Handler for /verify command"""
    # Run the core verification service
    result = verify_telegram_membership(user_id)
    
    if not result['success']:
        send_telegram_message(chat_id, f"⚠️ Verification check failed: {result['error']}")
        return

    status = result['status']
    is_member = result['is_member']
    membership = result['membership']

    if membership:
        kpn_name = membership.user.get_full_name()
        kpn_role = membership.user.get_role_display()
        link_status = f"✅ Linked to KPN Profile: <b>{kpn_name}</b> ({kpn_role})"
    else:
        link_status = (
            "⚠️ <b>Not linked to a KPN Profile.</b>\n"
            "To link your account, log in to <a href='https://kpn.com.ng'>kpn.com.ng</a> and click 'Verify Membership'."
        )

    if is_member:
        channel_status = f"✅ Active channel member (Status: {status})"
    else:
        channel_status = (
            f"❌ Not an active member of the official KPN channel.\n"
            f"(Status: {status})"
        )

    text = (
        "<b>KPN Membership Status</b>\n\n"
        f"Telegram ID: <code>{user_id}</code>\n"
        f"Channel Status: {channel_status}\n\n"
        f"Website Link: {link_status}"
    )
    
    send_telegram_message(chat_id, text, parse_mode='HTML')


def handle_meetings(chat_id: int, user_id: int):
    """Handler for /meetings command - list upcoming and active meetings"""
    now = timezone.now()
    
    # Active meetings
    active_meetings = KPNMeeting.objects.filter(status='ACTIVE').order_by('scheduled_start')
    # Upcoming scheduled meetings
    upcoming_meetings = KPNMeeting.objects.filter(
        status='SCHEDULED', 
        scheduled_start__gte=now
    ).order_by('scheduled_start')[:5]

    text = "<b>KPN Meetings</b>\n\n"

    if active_meetings.exists():
        text += "🟢 <b>ACTIVE NOW</b>\n"
        for m in active_meetings:
            text += f"• <b>{m.title}</b> ({m.get_meeting_type_display()})\n"
            text += "<i>Type /present to mark your attendance!</i>\n\n"
    
    if upcoming_meetings.exists():
        text += "📅 <b>UPCOMING</b>\n"
        for m in upcoming_meetings:
            date_str = m.scheduled_start.strftime('%d %b %Y, %I:%M %p')
            text += f"• {m.title}\n  <i>{date_str}</i>\n"
    
    if not active_meetings.exists() and not upcoming_meetings.exists():
        text += "No active or upcoming meetings scheduled at the moment."

    send_telegram_message(chat_id, text)


def handle_present(chat_id: int, user_id: int):
    """Handler for /present command - record attendance"""
    active_meetings = KPNMeeting.objects.filter(status='ACTIVE')
    
    if not active_meetings.exists():
        send_telegram_message(chat_id, "There are no active KPN meetings right now.")
        return

    # Check if user is linked
    try:
        membership = TelegramMembership.objects.get(telegram_user_id=user_id)
        kpn_user = membership.user
    except TelegramMembership.DoesNotExist:
        send_telegram_message(
            chat_id, 
            "⚠️ You must link your Telegram account to your KPN profile on the website before you can record attendance."
        )
        return

    # Assuming there's only one active meeting, or they are marking present for all active ones they are expected at
    marked_count = 0
    text = ""

    for meeting in active_meetings:
        # Is user expected? If it has expected participants and user isn't one, skip unless it's general
        if meeting.expected_participants.exists() and not meeting.expected_participants.filter(id=kpn_user.id).exists():
            continue

        attendance, created = MeetingAttendance.objects.get_or_create(
            meeting=meeting,
            user=kpn_user,
            defaults={
                'telegram_user_id': user_id,
                'status': 'PRESENT',
                'confirmed_at': timezone.now()
            }
        )

        if not created and attendance.status == 'PRESENT':
            text += f"✅ You are already marked PRESENT for: <b>{meeting.title}</b>\n"
        else:
            attendance.status = 'PRESENT'
            attendance.confirmed_at = timezone.now()
            attendance.telegram_user_id = user_id
            attendance.save()
            marked_count += 1
            text += f"✅ Attendance recorded for: <b>{meeting.title}</b>\n"

    if not text:
        text = "You are not listed as an expected participant for any currently active meetings."

    send_telegram_message(chat_id, text)


def handle_ai_query(chat_id: int, user_id: int, query: str):
    """Pass query to AI assistant and send response"""
    if not query:
        send_telegram_message(chat_id, "Please ask a question. Example: /kpn What is the KPN motto?")
        return

    # Add a typing action here if we had the method, but sending a waiting message is okay too
    # send_telegram_message(chat_id, "<i>Thinking...</i>")

    extra_context = ""
    # Try to get user context
    try:
        membership = TelegramMembership.objects.get(telegram_user_id=user_id)
        extra_context = f"User Name: {membership.user.get_full_name()}\nUser Role: {membership.user.get_role_display()}"
    except TelegramMembership.DoesNotExist:
        pass

    response = ask_kpn_assistant(message=query, telegram_user_id=user_id, extra_context=extra_context)
    send_telegram_message(chat_id, response)


def handle_chat_member_update(update: dict):
    """
    Process chat_member updates from the webhook.
    Fired when a user joins, leaves, or is restricted in the channel.
    """
    chat = update.get('chat', {})
    chat_id = str(chat.get('id', ''))
    
    from django.conf import settings
    configured_channel = getattr(settings, 'TELEGRAM_CHANNEL_ID', '')
    
    # We only care about updates from our configured channel
    # Note: configured_channel might be a username like @officialkpn, 
    # while chat_id is always numeric. We should ideally trigger verification.
    
    new_chat_member = update.get('new_chat_member', {})
    user = new_chat_member.get('user', {})
    user_id = user.get('id')
    status = new_chat_member.get('status')

    if not user_id:
        return

    # The most robust way is to just call our central verification service
    # which will fetch the latest authoritative state and update the DB
    try:
        verify_telegram_membership(user_id)
    except Exception as e:
        logger.error(f"Error verifying membership on chat_member update: {e}")
