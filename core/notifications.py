"""
core/notifications.py
Utility functions for creating in-app notifications.

Usage anywhere in views.py:
    from core.notifications import notify
    notify(user, 'SUCCESS', 'Application Approved', 
           'Your membership application has been approved!', 
           '/account/dashboard/')
"""
from core.models import Notification


def notify(user, notif_type='INFO', title='', message='', link=''):
    """Create a notification for a user."""
    Notification.objects.create(
        user=user,
        notif_type=notif_type,
        title=title,
        message=message,
        link=link,
    )


def notify_many(users, notif_type='INFO', title='', message='', link=''):
    """Create the same notification for multiple users at once."""
    Notification.objects.bulk_create([
        Notification(
            user=u,
            notif_type=notif_type,
            title=title,
            message=message,
            link=link,
        )
        for u in users
    ])
