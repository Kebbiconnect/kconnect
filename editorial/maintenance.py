"""Deterministic briefings, deadline reminders, link checks and weekly counts.
No AI is needed for these aggregate jobs; nothing is published automatically.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from .models import Item, Source, LinkCheck, Audit
from .services import notify_ready, fingerprint
from .fetch import hosts_for, fetch, FetchError

def local_day(): return timezone.now().astimezone(ZoneInfo('Africa/Lagos')).date()

def record(key,kind,title,draft,**refs):
    item,created=Item.objects.get_or_create(key=key,defaults={'kind':kind,'state':'REVIEW','title':title,'draft':dict(title=title,**draft),**refs})
    if created:Audit.objects.create(item=item,action='AUTOMATION_SUMMARY_CREATED');notify_ready(item)
    return item

def briefings():
    from campaigns.models import Campaign
    from core.models import Report, CommunityReport
    day=local_day()
    pending=Item.objects.filter(state='REVIEW',kind__in=['NEWS','OPPORTUNITY','DUPLICATE','LINK_ALERT'])
    lines=[f'Editorial briefing — {day}',f'News drafts needing review: {pending.filter(kind="NEWS").count()}',f'Opportunity drafts needing review: {pending.filter(kind="OPPORTUNITY").count()}',f'Duplicate alerts: {pending.filter(kind="DUPLICATE").count()}',f'Application-link alerts: {pending.filter(kind="LINK_ALERT").count()}',f'Article review queue: {Campaign.objects.filter(status="PENDING").count()}', 'Suggested order: urgent deadlines, factual checks, add images, review and publish.']
    for row in pending.order_by('-created_at')[:10]:lines.append(f'- {row.get_kind_display()}: {row.title}')
    item=record(f'brief:{day}','BRIEFING',f'Daily editorial briefing — {day}',{'body':'\n'.join(lines)})
    # Refresh a still-open deterministic briefing; never replace a human-edited or dismissed briefing.
    if item.state=='REVIEW' and item.reviewed_by_id is None:
        Item.objects.filter(pk=item.pk).update(draft={'title':item.title,'body':'\n'.join(lines)},version=item.version+1)
    start=day-timedelta(days=day.weekday())
    start_dt=timezone.datetime.combine(start-timedelta(days=7),timezone.datetime.min.time(),tzinfo=ZoneInfo('Africa/Lagos'))
    end_dt=timezone.datetime.combine(start,timezone.datetime.min.time(),tzinfo=ZoneInfo('Africa/Lagos'))
    # Reports lack review-event history, so this is explicitly current-row timestamp counting, not throughput analytics.
    published=Campaign.objects.filter(published_at__gte=start_dt,published_at__lt=end_dt,status='PUBLISHED').count()
    reviewed=Report.objects.filter(reviewed_at__gte=start_dt,reviewed_at__lt=end_dt).count()
    edits=Audit.objects.filter(action='APPLY',created_at__gte=start_dt,created_at__lt=end_dt).count()
    body=(f'Period: {start_dt.date()} to {(end_dt-timedelta(days=1)).date()}\nCurrently published articles with publication timestamps in period: {published}\nReport records with latest review timestamps in period: {reviewed}\nHuman-applied editorial report edits in period: {edits}\nPending submitted hierarchical reports now: {Report.objects.filter(status="SUBMITTED").count()}\nPending community reports now: {CommunityReport.objects.filter(status="PENDING").count()}\nCommunity reports have no review timestamp, so weekly community-review throughput cannot be inferred reliably. Counts are snapshots, not a reconstruction of all historical decisions.')
    record(f'weekly:{start}','WEEKLY',f'Weekly publishing and report-review summary — {start}',{'body':body})

def deadline_reminders():
    from core.models import Opportunity
    day=local_day()
    for offset in [7,3,1,0]:
        for opp in Opportunity.objects.filter(status__in=['OPEN','CLOSING_SOON'],deadline=day+timedelta(days=offset)).order_by('pk')[:100]:
            record(f'deadline:{opp.pk}:{day}','DEADLINE',f'Opportunity deadline: {opp.title}'[:300],{'body':f'Deadline: {opp.deadline}. Days remaining: {offset}. Confirm the provider deadline and timezone before sharing.','application_link':opp.application_link},opportunity=opp)

def link_checks(limit=10):
    from core.models import Opportunity
    approved=set()
    for source in Source.objects.filter(enabled=True):
        try:approved.update(hosts_for(source))
        except FetchError:continue
    checked=set(LinkCheck.objects.filter(day=local_day()).values_list('opportunity_id',flat=True))
    count=0
    for opp in Opportunity.objects.filter(status__in=['OPEN','CLOSING_SOON']).exclude(application_link='').order_by('pk'):
        if opp.pk in checked:continue
        if count>=limit:break
        state='UNVERIFIED';status=None
        try:
            # Unknown host stays unverified. Reviewer must explicitly approve that hostname in Sources.
            status,_,_=fetch(opp.application_link,approved,method='HEAD')
            if status==405:status,_,_=fetch(opp.application_link,approved,method='GET')
            if 200<=status<300:state='OK'
            elif status in {404,410}:state='BROKEN'
            elif status in {401,403,429}:state='RESTRICTED'
            else:state='UNVERIFIED'
        except (FetchError,ValueError):pass
        row,created=LinkCheck.objects.get_or_create(opportunity=opp,day=local_day(),defaults={'url':opp.application_link,'state':state,'http_status':status})
        count+=1
        if created and state=='BROKEN':
            record(f'link:{opp.pk}:{local_day()}','LINK_ALERT',f'Check application link: {opp.title}'[:300],{'body':f'Application link returned HTTP {status}. Verify manually; the opportunity has NOT been changed or closed.','application_link':opp.application_link},opportunity=opp)
    return count
