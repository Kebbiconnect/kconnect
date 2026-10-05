"""Shared in-app and Android push notification service."""
from core.models import Notification

def _push(notification):
    try:
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
    if push:_push(notification)
    return notification

def notify_many(users, notif_type='INFO', title='', message='', link='', event='INFO', target_type='', target_id=None, push=True):
    notifications=Notification.objects.bulk_create([Notification(user=u,notif_type=notif_type,event=event,
        target_type=target_type,target_id=target_id,title=title,message=message,link=link) for u in users])
    if push:
        for notification in notifications:_push(notification)
    return notifications
