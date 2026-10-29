"""Private editorial drafts and explicitly human-initiated handoffs."""
import hashlib
import json
from datetime import date
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape
from django.utils.text import slugify
from .access import editor, items_for, manager
from .models import Audit, Delivery, Item, Job
from .fetch import canonical, FetchError

REPORT_FIELDS=('title','content')
COMMUNITY_FIELDS=('what_happened','who_was_involved','why_is_it_important')

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def snapshot(report):
    fields=REPORT_FIELDS if report._meta.model_name=='report' else COMMUNITY_FIELDS
    data={field:getattr(report,field) for field in fields}
    if 'title' not in data:data['title']='Community report'
    return data

def source_fingerprint(item): return fingerprint(item.original)

def queue_report(report):
    if not settings.KPN_EDITORIAL_ENABLED:return None
    community=report._meta.model_name=='communityreport'
    if report.status!=('PENDING' if community else 'SUBMITTED'):return None
    if not community and report.parent_report_id:return None  # Already consolidated by the existing approval chain.
    original=snapshot(report)
    key=f'{report._meta.model_name}:{report.pk}:'+fingerprint(original)[:48]
    defaults={'kind':'COMMUNITY_EDIT' if community else 'REPORT_EDIT','title':original['title'][:300],'original':original}
    defaults['community_report' if community else 'report']=report
    item,created=Item.objects.get_or_create(key=key,defaults=defaults)
    if created:
        Job.objects.create(key='generate:'+key,kind='GENERATE',item=item)
        Audit.objects.create(item=item,action='SUBMISSION_QUEUED')
    return item

def source_current(item):
    if item.kind not in {'REPORT_EDIT','COMMUNITY_EDIT'}:return True
    report=item.report if item.kind=='REPORT_EDIT' else item.community_report
    if report is None:return False
    report.refresh_from_db()
    pending=report.status in ({'SUBMITTED','UNDER_REVIEW'} if item.kind=='REPORT_EDIT' else {'PENDING','UNDER_REVIEW'})
    return pending and snapshot(report)==item.original

def recipients(item):
    from staff.models import User
    if item.kind=='REPORT_EDIT':
        return User.objects.filter(pk=item.report.submitted_to_id,is_active=True,status='VERIFIED') if item.report else User.objects.none()
    from .access import EDITORS
    return User.objects.filter(is_active=True,status='VERIFIED',role='STATE',role_definition__title__in=EDITORS)

def notify_ready(item):
    if not settings.KPN_EDITORIAL_NOTIFICATIONS:return
    from core.notifications import notify
    for user in recipients(item):
        with transaction.atomic():
            delivery,created=Delivery.objects.get_or_create(item=item,user=user)
            if created:
                notify(user,title='KPN Editorial Assistant: review needed',message=f'{item.get_kind_display()}: {item.title}',link=f'/editorial/items/{item.pk}/',event='EDITORIAL_REVIEW',target_type='editorial_item',target_id=item.pk)

def unique_slug(model,title):
    base=slugify(title)[:280] or 'kpn-editorial'
    suffix=1;slug=base
    while model.objects.filter(slug=slug).exists():suffix+=1;slug=f'{base}-{suffix}'
    return slug

@transaction.atomic
def save_review(user,item_id,data,version):
    if not items_for(user).filter(pk=item_id).exists():raise PermissionDenied
    item=Item.objects.select_for_update().get(pk=item_id)
    if item.state not in {'WAITING','REVIEW'}:raise ValidationError('This item has already been handed off or closed.')
    if item.version!=version:raise ValidationError('This draft changed. Reload before saving.')
    allowed={'title','body','category','provider','requirements','benefits','application_link','deadline','content','what_happened','who_was_involved','why_is_it_important','notes'}
    if any(k not in allowed or not isinstance(v,str) or len(v)>20000 for k,v in data.items()):raise ValidationError('Invalid draft fields.')
    if not data.get('title','').strip() or len(data['title'])>300:raise ValidationError('A title of at most 300 characters is required.')
    item.draft=data;item.title=data['title'];item.state='REVIEW';item.reviewed_by=user;item.version+=1;item.save()
    Audit.objects.create(item=item,actor=user,action='DRAFT_EDITED',detail={'version':item.version})
    return item

@transaction.atomic
def act(user,item_id,action,version,confirmed=False):
    if not items_for(user).filter(pk=item_id).exists():raise PermissionDenied
    item=Item.objects.select_for_update().get(pk=item_id)
    if item.version!=version:raise ValidationError('This item changed. Reload first.')
    if item.state not in {'REVIEW','WAITING'}:raise ValidationError('This item is already closed or handed off.')
    if action=='dismiss':
        item.state='DISMISSED'
    elif action=='handoff':
        if not editor(user) or item.kind not in {'NEWS','OPPORTUNITY'}:raise PermissionDenied
        if not confirmed:raise ValidationError('Confirm that you checked the sources and facts.')
        if item.original.get('synthetic'):raise ValidationError('Synthetic test drafts cannot be handed off or published.')
        d=item.draft
        if not d.get('title') or not d.get('body'):raise ValidationError('Review a completed draft first.')
        if item.kind=='NEWS':
            from campaigns.models import Campaign
            category=d.get('category','GENERAL')
            if category not in dict(Campaign.CATEGORY_CHOICES):raise ValidationError('Select an existing KPN news category.')
            paragraphs=[p.strip() for p in d['body'].split('\n') if p.strip()]
            source_line=f'Source: {item.source_url}' if item.source_url else ''
            blocks=[{'type':'paragraph','data':{'text':str(escape(p))}} for p in paragraphs]
            if source_line:blocks.append({'type':'paragraph','data':{'text':str(escape(source_line))}})
            item.article=Campaign.objects.create(author=user,title=d['title'],slug=unique_slug(Campaign,d['title']),content=str(escape(d['body']))+'\n\n'+str(escape(source_line)),content_json={'blocks':blocks},category=category,status='PENDING',verification_status='DEVELOPING',reporter_credit='KPN_EDITORIAL')
        else:
            from leadership.capabilities import capabilities_for
            if not user.is_superuser and 'MANAGE_HUBS' not in capabilities_for(user):raise PermissionDenied
            from core.models import Opportunity
            if d.get('category') not in dict(Opportunity.CATEGORY_CHOICES):raise ValidationError('Select an existing opportunity category.')
            if not d.get('provider','').strip():raise ValidationError('Confirm the opportunity provider.')
            try:link=canonical(d.get('application_link',''))
            except (FetchError,ValueError):raise ValidationError('Confirm a valid HTTPS application link.')
            try:deadline=date.fromisoformat(d['deadline']) if d.get('deadline') else None
            except ValueError:raise ValidationError('Use YYYY-MM-DD for the deadline, or leave blank.')
            if deadline and deadline<timezone.localdate():raise ValidationError('This application deadline has passed.')
            if len(link)>200:raise ValidationError('The application URL exceeds the existing opportunity field limit (200 characters).')
            item.opportunity=Opportunity.objects.create(title=d['title'],slug=unique_slug(Opportunity,d['title']),category=d['category'],provider=d['provider'][:200],description=d['body']+'\n\nSource: '+item.source_url,requirements=d.get('requirements',''),benefits=d.get('benefits',''),application_link=link,deadline=deadline,status='OPEN')
        item.state='HANDED_OFF'
    elif action=='apply':
        if item.kind not in {'REPORT_EDIT','COMMUNITY_EDIT'}:raise PermissionDenied
        if not confirmed:raise ValidationError('Confirm you compared the edit with the original.')
        report=item.report if item.kind=='REPORT_EDIT' else item.community_report
        report=type(report).objects.select_for_update().get(pk=report.pk)
        if not source_current(item):raise ValidationError('The report was edited or reviewed after this suggestion. Nothing was changed.')
        fields=REPORT_FIELDS if item.kind=='REPORT_EDIT' else COMMUNITY_FIELDS
        for field in fields:
            value=item.draft.get(field)
            if not isinstance(value,str) or (field in {'title','content','what_happened'} and not value.strip()):raise ValidationError('The edited report is incomplete.')
            if field=='title' and len(value)>300:raise ValidationError('Report title is too long.')
            setattr(report,field,value)
        # Preserve status, approval fields, attribution and the original snapshot in Item.
        report.save(update_fields=list(fields));item.state='APPLIED'
    else:raise ValidationError('Unknown action.')
    item.reviewed_by=user;item.version+=1;item.save()
    Job.objects.filter(item=item,state__in=['QUEUED','BLOCKED']).update(state='DONE',error_code='closed_by_human')
    Audit.objects.create(item=item,actor=user,action=action.upper(),detail={'version':item.version})
    return item


def article_text(article):
    from .fetch import readable
    content=article.content or ''
    if not content and isinstance(article.content_json,dict):
        def strings(value):
            if isinstance(value,str):return [value]
            if isinstance(value,list):return [t for x in value for t in strings(x)]
            if isinstance(value,dict):return [t for key,v in value.items() if key in {'text','content','items'} for t in strings(v)]
            return []
        content='\n'.join(t for block in article.content_json.get('blocks',[]) if isinstance(block,dict) for t in strings(block.get('data',{})))
    return readable(content.encode())[:24000]
