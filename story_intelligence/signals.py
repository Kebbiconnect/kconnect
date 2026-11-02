"""Backstop safeguard ONLY (assessment §7.5): if a PUBLISHED article
without a Story ID is ever observed after commit — i.e. some path
bypassed the publishing services — record a StoryAudit anomaly so the
gap is visible to editors. This signal never allocates IDs and never
blocks a save; enforcement lives in campaigns.services.publish_campaign
and the editorial publish transactions.
"""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from campaigns.models import Campaign


@receiver(post_save, sender=Campaign)
def _published_without_story_id_backstop(sender, instance, **kwargs):
    if instance.status != 'PUBLISHED' or instance.story_id:
        return
    pk = instance.pk

    def _check():
        from .services import log_audit
        article = Campaign.objects.filter(pk=pk).values('status', 'story_id').first()
        if article and article['status'] == 'PUBLISHED' and not article['story_id']:
            log_audit(None, 'ANOMALY_PUBLISHED_WITHOUT_STORY_ID', 'campaign', pk, {})

    transaction.on_commit(_check)
