"""Recipient-scoped inbox queries shared by website and native API."""
from django.db.models import Q
from core.models import Notification
from staff.models import Announcement


def visible_notifications(user):
    # Keep legacy notices without reliable target metadata. Never match by title.
    orphaned = (
        Q(event='ANNOUNCEMENT', target_type='announcement', target_id__isnull=False)
        & ~Q(target_id__in=Announcement.objects.values('pk'))
    )
    return Notification.objects.filter(user=user).exclude(orphaned)
