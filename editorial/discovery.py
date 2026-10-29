"""Allowlisted source discovery, provenance and duplicate alerts. No broad web crawler."""
from datetime import timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree
from django.conf import settings
from django.utils import timezone
from .fetch import permitted_fetch, readable, hosts_for, canonical, FetchError, application_links
from .models import Item, Job, Audit
from .services import fingerprint, notify_ready

def entries(body,base,feed=True):
    if not feed:
        text=readable(body)
        return [{'title':text.split('\n')[0][:300] or base,'url':base,'date':'','summary':text[:3000]}]
    if b'<!doctype' in body.lower() or b'<!entity' in body.lower():raise FetchError('unsafe_xml')
    try:root=ElementTree.fromstring(body)
    except ElementTree.ParseError:raise FetchError('invalid_feed')
    result=[]
    nodes=[e for e in root.iter() if e.tag.split('}')[-1] in {'item','entry'}]
    for node in nodes[:30]:
        data={'title':'','url':'','date':'','summary':''}
        for child in node:
            tag=child.tag.split('}')[-1];text=''.join(child.itertext()).strip()
            if tag=='title':data['title']=text[:300]
            elif tag=='link' and child.attrib.get('rel','alternate')=='alternate':data['url']=urljoin(base,child.attrib.get('href') or text)
            elif tag in {'pubDate','published','updated'} and not data['date']:data['date']=text
            elif tag in {'description','summary'}:data['summary']=readable(text.encode())[:3000]
        if data['url']:result.append(data)
    return result

def is_old(value):
    if not value:return False
    try:
        try:dt=parsedate_to_datetime(value)
        except (TypeError,ValueError):dt=timezone.datetime.fromisoformat(value.replace('Z','+00:00'))
        if timezone.is_naive(dt):dt=timezone.make_aware(dt)
        return dt<timezone.now()-timedelta(days=3) or dt>timezone.now()+timedelta(days=1)
    except (TypeError,ValueError,OverflowError):return False

def similar(title,kind):
    from campaigns.models import Campaign
    from core.models import Opportunity
    import re
    norm=lambda s:' '.join(re.findall(r'\w+',s.casefold()))
    clean=norm(title)
    if len(clean)<16:return []
    model=Campaign if kind=='NEWS' else Opportunity
    records=list(model.objects.order_by('-created_at').values_list('pk','title')[:200])
    records += [(f'draft:{pk}',t) for pk,t in Item.objects.filter(kind=kind).exclude(state='DISMISSED').order_by('-created_at').values_list('pk','title')[:200]]
    return [{'id':str(pk),'title':t} for pk,t in records if SequenceMatcher(None,clean,norm(t)).ratio()>=0.9][:5]

def discover(source):
    if not source.enabled:return 0
    allowed=hosts_for(source);body,final=permitted_fetch(source.url,allowed)
    count=0
    for entry in entries(body,final,source.feed):
        if count>=min(5,source.max_items):break
        if is_old(entry['date']):continue
        if source.kind=='NEWS':
            words=[s.strip().casefold() for s in source.keywords.split(',') if s.strip()]
            if not words or not any(w in (entry['title']+' '+entry['summary']).casefold() for w in words):continue
        try:url=canonical(entry['url'])
        except FetchError:continue
        key='source:'+source.kind+':'+fingerprint(url)[:55]
        if Item.objects.filter(key=key).exists():continue
        today=timezone.now().astimezone(__import__('zoneinfo').ZoneInfo('Africa/Lagos')).date()
        if Item.objects.filter(kind=source.kind,created_at__date=today).count()>=settings.KPN_EDITORIAL_DAILY_DRAFTS:break
        duplicates=similar(entry['title'],source.kind)
        if duplicates:
            item,created=Item.objects.get_or_create(key=key,defaults={'kind':'DUPLICATE','state':'REVIEW','title':('Possible duplicate: '+entry['title'])[:300],'source':source,'source_url':url,'original':entry,'draft':{'title':entry['title'],'body':'Possible duplicate; compare before commissioning another draft.','matches':duplicates}})
            if created:Audit.objects.create(item=item,action='DUPLICATE_FLAGGED');notify_ready(item);count+=1
            continue
        try:
            article_body,article_url=permitted_fetch(url,allowed)
            content=readable(article_body)
        except FetchError as exc:
            Audit.objects.create(action='SOURCE_ITEM_SKIPPED',detail={'source_id':source.pk,'url_hash':fingerprint(url),'code':str(exc)[:100]})
            continue
        if len(content)<200:continue
        original={'title':entry['title'],'text':content,'source_url':article_url,'source_name':source.name,'source_date':entry['date'],'discovered_at':timezone.now().isoformat(),'excerpt_only':True,'application_links':application_links(article_body,article_url) if source.kind=='OPPORTUNITY' else [],'date_warning':'Editor must confirm the publication date and whether this item is still current.'}
        item,created=Item.objects.get_or_create(key=key,defaults={'kind':source.kind,'title':entry['title'][:300] or source.name,'source':source,'source_url':article_url,'original':original})
        if created:
            Job.objects.create(key='generate:'+key,kind='GENERATE',item=item)
            Audit.objects.create(item=item,action='SOURCE_CAPTURED');count+=1
    return count
