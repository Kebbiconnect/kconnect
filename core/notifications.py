"""Shared in-app + push notification event abstraction."""
from django.db import transaction
from core.models import Notification

def notify(user, notif_type='INFO', title='', message='', link='', event='INFO'):
    notification=Notification.objects.create(user=user,event=event,notif_type=notif_type,title=title,message=message,link=link)
    transaction.on_commit(lambda: _push(notification.pk))
    return notification

def _push(pk):
    from core.models import Notification
    from core.push import send_notification
    try: send_notification(Notification.objects.get(pk=pk))
    except Exception: pass  # delivery failures are recorded and never roll back business actions

def notify_many(users, notif_type='INFO', title='', message='', link='', event='INFO'):
    return [notify(u,notif_type,title,message,link,event) for u in users]

def announcement_recipients(announcement):
    from staff.models import User
    qs=User.objects.filter(status='VERIFIED',is_active=True)
    if announcement.scope=='ZONAL': qs=qs.filter(zone=announcement.target_zone)
    elif announcement.scope=='LGA': qs=qs.filter(lga=announcement.target_lga)
    elif announcement.scope=='WARD': qs=qs.filter(ward=announcement.target_ward)
    return qs

def verified_members():
    from staff.models import User
    return User.objects.filter(status='VERIFIED', is_active=True)

def notify_event_audience(event_name, event, message):
    """Events are statewide in the current Event model (no geographic scope field)."""
    return notify_many(verified_members(), 'INFO', event.title, message, f'/events/{event.pk}/', event=event_name)
