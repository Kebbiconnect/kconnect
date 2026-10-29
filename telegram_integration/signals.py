"""When a website article is published, queue its Telegram channel share
and try to send it immediately. Gated by the master automation switch
(KPN_EDITORIAL_ENABLED) so nothing posts before the owner activates the
brain, and so the kill switch stops shares too."""
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from campaigns.models import Campaign


@receiver(post_save, sender=Campaign)
def share_published_article(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk or instance.status != 'PUBLISHED':
        return
    if not getattr(settings, 'KPN_EDITORIAL_ENABLED', False):
        return
    try:
        previous = Campaign.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    except Exception:
        return
    # post_save fires after the write, so `previous` is already PUBLISHED on
    # later edits; the outbox dedupe in enqueue_article_share is what makes
    # this fire exactly once per article.
    def _share():
        from .brain_service import enqueue_article_share, send_outbox_row
        row = enqueue_article_share(instance)
        if row is not None:
            send_outbox_row(row)
    transaction.on_commit(_share)
