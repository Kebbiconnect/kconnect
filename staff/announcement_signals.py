from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from staff.models import Announcement


@receiver(post_save, sender=Announcement, dispatch_uid='kpn.announcement.inbox_delivery')
def announcement_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from staff.services.announcements import deliver_announcement
    deliver_announcement(instance.pk)


@receiver(post_delete, sender=Announcement, dispatch_uid='kpn.announcement.inbox_retraction')
def announcement_deleted(sender, instance, using, **kwargs):
    """Retract only this announcement's inbox copies, including bulk deletes."""
    from core.models import Notification
    Notification.objects.using(using).filter(
        event='ANNOUNCEMENT', target_type='announcement', target_id=instance.pk,
    ).delete()
