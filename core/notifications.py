"""Shared in-app and Android push notification service."""
from core.models import Notification
from django.db import transaction

def _push(notification):
    try:
        # Suppress a callback if its notification was deleted before commit.
        if not Notification.objects.filter(pk=notification.pk).exists():
            return
        from rest_api.push import send_to_devices
        send_to_devices(notification.user.devices, title=notification.title, body=notification.message,
                        data={'notification_id':notification.id,'event':notification.event,
                              'target_type':notification.target_type,'target_id':notification.target_id,
                              'route':notification.link})
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Notification push dispatch failed')

def notify(user, notif_type='INFO', title='', message='', link='', event='INFO', target_type='', target_id=None, push=True):
    notification=Notification.objects.create(user=user,notif_type=notif_type,event=event,target_type=target_type,
        target_id=target_id,title=title,message=message,link=link)
    if push:transaction.on_commit(lambda: _push(notification))
    return notification

def notify_many(users, notif_type='INFO', title='', message='', link='', event='INFO', target_type='', target_id=None, push=True):
    notifications=Notification.objects.bulk_create([Notification(user=u,notif_type=notif_type,event=event,
        target_type=target_type,target_id=target_id,title=title,message=message,link=link) for u in users])
    if push:
        for notification in notifications:
            transaction.on_commit(lambda item=notification: _push(item))
    return notifications

def notify_all_members(event, title, message, link='', target_type='', target_id=None, exclude_user_id=None):
    """Notify every verified member (in-app + push) — used when new
    public content is published (owner request, 27 Nov 2026: the app
    should notify all members when a news story or an opportunity is
    posted). Mirrors the announcements fan-out pattern. A failure here
    must never break the publish that triggered it."""
    try:
        from staff.models import User
        users = list(User.objects.filter(status='VERIFIED', is_active=True, is_superuser=False).exclude(pk=exclude_user_id))
        if users:
            return notify_many(users, 'INFO', title, message, link=link, event=event,
                               target_type=target_type, target_id=target_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('notify_all_members failed for event=%s', event)
    return []
