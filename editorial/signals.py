from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from core.models import Report, CommunityReport
from campaigns.models import Campaign
from .services import queue_report, fingerprint, article_text
from .models import Item, Job

@receiver(pre_save,sender=Report,dispatch_uid='editorial.report.previous')
@receiver(pre_save,sender=CommunityReport,dispatch_uid='editorial.community.previous')
def previous_status(sender,instance,**kwargs):
    if not settings.KPN_EDITORIAL_ENABLED:return
    instance._editorial_previous=sender.objects.filter(pk=instance.pk).values_list('status',flat=True).first() if instance.pk else None

@receiver(post_save,sender=Report,dispatch_uid='editorial.report.submitted')
@receiver(post_save,sender=CommunityReport,dispatch_uid='editorial.community.submitted')
def submitted(sender,instance,created,raw=False,**kwargs):
    if raw or not settings.KPN_EDITORIAL_ENABLED:return
    target='SUBMITTED' if sender==Report else 'PENDING'
    previous=getattr(instance,'_editorial_previous',None)
    if instance.status==target and (created or previous!=target):
        pk=instance.pk
        def enqueue():
            obj=sender.objects.filter(pk=pk).first()
            if obj:queue_report(obj)
        transaction.on_commit(enqueue,robust=True)

@receiver(post_save,sender=Campaign,dispatch_uid='editorial.published.caption')
def published(sender,instance,raw=False,**kwargs):
    if raw or not settings.KPN_EDITORIAL_ENABLED or instance.status!='PUBLISHED':return
    pk=instance.pk
    def enqueue():
        article=Campaign.objects.filter(pk=pk,status='PUBLISHED').first()
        if not article:return
        # One caption suggestion per article. Later article edits never overwrite a human-reviewed caption.
        item,created=Item.objects.get_or_create(key=f'caption:{pk}',defaults={'kind':'CAPTION','title':article.title,'article':article,'original':{'title':article.title,'text':article_text(article),'url':f'/campaigns/article/{article.slug}/'}})
        if created:Job.objects.create(key=f'caption:{pk}',kind='GENERATE',item=item)
    transaction.on_commit(enqueue,robust=True)
