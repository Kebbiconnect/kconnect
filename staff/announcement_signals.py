from django.db.models.signals import post_save
from django.dispatch import receiver
from staff.models import Announcement


@receiver(post_save, sender=Announcement, dispatch_uid='kpn.announcement.inbox_delivery')
def announcement_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from staff.services.announcements import deliver_announcement
    deliver_announcement(instance.pk)
