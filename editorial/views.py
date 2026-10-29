from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db import transaction
from .access import active, editor, manager, items_for
from .forms import DraftForm, SourceForm
from .models import Audit, Control, Item, Job, LinkCheck, Source
from .services import act, save_review, source_current

def errors(request,exc):
    for text in exc.messages:messages.error(request,text)

@login_required
def index(request):
    if not active(request.user):raise PermissionDenied
    rows=items_for(request.user)
    kind=request.GET.get('kind','');state=request.GET.get('state','')
    if kind in dict(Item.KIND):rows=rows.filter(kind=kind)
    if state in dict(Item.STATE):rows=rows.filter(state=state)
    if request.GET.get('report','').isdigit():rows=rows.filter(report_id=int(request.GET['report']))
    page=Paginator(rows,25).get_page(request.GET.get('page'))
    control,_=Control.objects.get_or_create(pk=1)
    jobs=Job.objects.filter(item__in=items_for(request.user)).exclude(state='DONE').select_related('item')[:20]
    if manager(request.user):jobs=Job.objects.exclude(state='DONE').select_related('item','source')[:30]
    return render(request,'editorial/index.html',{'page':page,'kinds':Item.KIND,'states':Item.STATE,'kind':kind,'state':state,'control':control,'feature_enabled':settings.KPN_EDITORIAL_ENABLED,'can_manage':manager(request.user),'can_edit':editor(request.user),'jobs':jobs,'brain_waiting':Item.objects.filter(state='WAITING').count(),'brain_queued':Job.objects.filter(kind='GENERATE',state='QUEUED').count(),'sources':Source.objects.all() if manager(request.user) else [],'links':LinkCheck.objects.select_related('opportunity').order_by('-day','pk')[:20] if editor(request.user) else []})

@login_required
def detail(request,pk):
    item=get_object_or_404(items_for(request.user),pk=pk)
    form=DraftForm(request.POST or None,item=item)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);version=data.pop('version')
        try:save_review(request.user,pk,data,version)
        except ValidationError as exc:errors(request,exc)
        else:messages.success(request,'Private draft saved. Nothing was published.');return redirect('editorial:detail',pk=pk)
    from leadership.capabilities import capabilities_for
    return render(request,'editorial/detail.html',{'can_publish_opportunity':request.user.is_superuser or 'MANAGE_HUBS' in capabilities_for(request.user),'item':item,'form':form,'current':source_current(item),'audit':item.audit.select_related('actor')[:30]})

@login_required
@require_POST
def action(request,pk):
    get_object_or_404(items_for(request.user),pk=pk)
    try:
        version=int(request.POST.get('version','0'))
        item=act(request.user,pk,request.POST.get('action',''),version,request.POST.get('confirmed')=='yes')
    except ValueError:messages.error(request,'Invalid item version.')
    except ValidationError as exc:errors(request,exc)
    else:
        messages.success(request,'Action completed by your account. Existing approval rules remain in place.')
    return redirect('editorial:detail',pk=pk)

@login_required
@require_POST
def control(request):
    if not manager(request.user):raise PermissionDenied
    with transaction.atomic():
        Control.objects.get_or_create(pk=1)
        row=Control.objects.select_for_update().get(pk=1)
        row.enabled=request.POST.get('enabled')=='yes';row.save()
        Audit.objects.create(actor=request.user,action='RESUMED' if row.enabled else 'PAUSED')
    messages.success(request,'Automation resumed.' if row.enabled else 'Automation paused.')
    return redirect('editorial:index')

@login_required
def source_edit(request,pk=None):
    if not manager(request.user):raise PermissionDenied
    source=get_object_or_404(Source,pk=pk) if pk else Source()
    form=SourceForm(request.POST or None,instance=source)
    if request.method=='POST' and form.is_valid():
        source=form.save();Audit.objects.create(actor=request.user,action='SOURCE_SAVED',detail={'source_id':source.pk})
        messages.success(request,'Source saved. Pages are fetched only by the bounded job runner.');return redirect('editorial:index')
    return render(request,'editorial/source.html',{'form':form,'source':source})

@login_required
@require_POST
def retry(request,pk):
    job=get_object_or_404(Job,pk=pk)
    if job.item_id:
        if not items_for(request.user).filter(pk=job.item_id).exists():raise PermissionDenied
    elif not manager(request.user):raise PermissionDenied
    with transaction.atomic():
        job=Job.objects.select_for_update().get(pk=pk)
        if job.state not in {'FAILED','BLOCKED'}:messages.error(request,'Only failed or blocked jobs can be retried.')
        elif job.item_id and job.item.state!='WAITING':messages.error(request,'The item is no longer waiting; existing human edits are protected.')
        else:
            from django.utils import timezone
            job.state='QUEUED';job.attempts=0;job.available_at=timezone.now();job.error_code='';job.save()
            Audit.objects.create(item=job.item,actor=request.user,action='JOB_RETRY_REQUESTED',detail={'job':pk})
            messages.success(request,'Queued for the next worker run. No external request was made by this page.')
    return redirect('editorial:index')
