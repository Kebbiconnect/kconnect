"""Inbox delivery shared by website, admin and API announcement saves."""
from django.db import transaction
from django.utils import timezone
from core.models import Notification
from core.notifications import notify_many
from staff.models import Announcement, User


def deliver_announcement(announcement_id):
    with transaction.atomic():
        announcement = Announcement.objects.select_for_update().get(pk=announcement_id)
        if not announcement.is_active or (announcement.expires_at and announcement.expires_at <= timezone.now()):
            return 0
        # Serialize on the announcement row: edits/activation and API saves
        # cannot create a second publication notification for the same item.
        if Notification.objects.filter(event='ANNOUNCEMENT', target_type='announcement', target_id=announcement.pk).exists():
            return 0
        users = User.objects.filter(status='VERIFIED', is_active=True)
        if announcement.scope == 'STATE':
            users = users.filter(role='STATE', role_definition__tier='STATE', is_superuser=False)
        elif announcement.scope == 'ZONAL':
            users = users.filter(zone_id=announcement.target_zone_id)
        elif announcement.scope == 'LGA':
            users = users.filter(lga_id=announcement.target_lga_id)
        elif announcement.scope == 'WARD':
            users = users.filter(ward_id=announcement.target_ward_id)
        elif announcement.scope != 'GENERAL':
            return 0
        notifications = notify_many(users, 'INFO', announcement.title, announcement.content,
                                    event='ANNOUNCEMENT', target_type='announcement', target_id=announcement.pk)
        return len(notifications)
