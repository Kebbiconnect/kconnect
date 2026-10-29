"""Bounded database worker for a free scheduled runner or a manual management command.

The worker runs DISCOVER jobs and deterministic maintenance only. GENERATE
(drafting) jobs are never executed here: they stay QUEUED until Muse, the
external brain, returns a draft through brain_inbox."""
import time
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Audit, Control, Item, Job, Source
from .services import source_current, notify_ready
from .discovery import discover
from .fetch import FetchError
from .maintenance import local_day, briefings, deadline_reminders, link_checks

class Paused(Exception):pass

@transaction.atomic
def acquire():
    Control.objects.get_or_create(pk=1)
    control=Control.objects.select_for_update().get(pk=1)
    if not settings.KPN_EDITORIAL_ENABLED or not control.enabled:raise Paused('Automation is disabled or paused.')
    if control.lease_until and control.lease_until>timezone.now():raise Paused('Another worker holds the lease.')
    token=uuid.uuid4().hex;control.lease_token=token;control.lease_until=timezone.now()+timedelta(minutes=20);control.save()
    return token

def schedule():
    day=local_day()
    for source in Source.objects.filter(enabled=True):
        Job.objects.get_or_create(key=f'discover:{source.pk}:{day}',defaults={'kind':'DISCOVER','source':source})
    # Capture already published articles if captions were enabled after publication.
    from campaigns.models import Campaign
    from .signals import published
    for article in Campaign.objects.filter(status='PUBLISHED').order_by('-published_at')[:10]:published(Campaign,article)

@transaction.atomic
def claim(token):
    control=Control.objects.select_for_update().get(pk=1)
    if not control.enabled or control.lease_token!=token:raise Paused('Paused or worker lease changed.')
    control.lease_until=timezone.now()+timedelta(minutes=20);control.save(update_fields=['lease_until'])
    # A crashed job can be recovered by a later worker; retry count is not reset.
    stale=timezone.now()-timedelta(minutes=20)
    Job.objects.filter(state='RUNNING',started_at__lt=stale,attempts__lt=3).update(state='QUEUED',error_code='recovered_after_worker_exit')
    Job.objects.filter(state='RUNNING',started_at__lt=stale,attempts__gte=3).update(state='FAILED',error_code='retry_limit')
    job=Job.objects.select_for_update().filter(kind='DISCOVER',state='QUEUED',available_at__lte=timezone.now(),attempts__lt=3).first()
    if job:
        job.state='RUNNING';job.attempts+=1;job.started_at=timezone.now();job.save()
    return job

def process(job):
    if job.kind=='DISCOVER':discover(job.source);return
    # GENERATE jobs belong to the external brain (Muse) via brain_inbox.
    return

def run(max_jobs=15,max_seconds=600):
    token=acquire();done=0;start=time.monotonic()
    try:
        schedule()
        while done<max_jobs and time.monotonic()-start<max_seconds:
            job=claim(token)
            if not job:break
            try:
                process(job);job.state='DONE';job.error_code=''
            except FetchError as exc:
                job.error_code=str(exc)[:100];job.state='FAILED'
            except Exception as exc:
                # Never log response bodies, source text or database credentials.
                job.error_code='internal_'+type(exc).__name__;job.state='FAILED'
            job.save(update_fields=['state','error_code','available_at']);done+=1
        control=Control.objects.get(pk=1)
        if control.enabled and control.lease_token==token:
            deadline_reminders();link_checks(limit=10);briefings()
    finally:
        Control.objects.filter(pk=1,lease_token=token).update(lease_token='',lease_until=None)
    return done
