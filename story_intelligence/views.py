"""Story desk — the internal editorial surface for KPN Media story
records (Phase 1). Every view enforces its capability server-side via
leadership.capabilities.capabilities_for(); hiding links in templates
is never the enforcement mechanism.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from campaigns.models import Campaign
from core.models import CommunityReport
from leadership.capabilities import capabilities_for

from .forms import (
    ArticleVerificationForm, ClaimForm, ClaimStatusForm, ConsentForm,
    CorrectionForm, EvidenceForm, InstitutionForm, LinkReportForm,
    PromiseForm, PromiseStatusForm, PromiseUpdateForm,
    PromiseVerificationClaimForm, RedactionForm, StoryProfileForm,
    StoryUpdateForm,
)
from .models import (
    Claim, EvidenceRecord, Institution, Promise, StoryAudit, StoryProfile,
    StorySourceLink, StoryUpdate,
)
from .services import (
    PromiseError, RedactionError, create_claim_from_report, link_report_to_story,
    log_audit, perform_redaction, record_promise_update, set_promise_status,
    set_article_verification_status, set_claim_status, unlink_report_from_story,
)


def story_capability_required(capability):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if capability not in capabilities_for(request.user):
                raise PermissionDenied(
                    'You do not have permission to manage story records.')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def _article(article_id):
    return get_object_or_404(Campaign, pk=article_id)


@story_capability_required('MANAGE_STORY_RECORDS')
def desk(request, article_id):
    article = _article(article_id)
    profile = StoryProfile.objects.filter(article=article).first()
    # Phase 4 editorial warnings (desk only — never public):
    # - a Future Signal with no linked evidence is flagged so editors
    #   attach stories/claims/evidence before relying on it;
    # - a Human Impact file blocked by the consent guard says so, with
    #   the exact reason the publish paths will refuse.
    from .services import consent_block_reason
    context = {
        'article': article,
        'profile': profile,
        'signal_missing_evidence': bool(
            profile and profile.kind == 'SIGNAL'
            and not profile.signal_has_evidence()),
        'consent_block_reason': consent_block_reason(article) if profile else '',
        'profile_form': StoryProfileForm(instance=profile, article=article),
        'update_form': StoryUpdateForm(),
        'claim_form': ClaimForm(),
        'evidence_form': EvidenceForm(article=article),
        'correction_form': CorrectionForm(article=article),
        'consent_form': ConsentForm(),
        'verification_form': ArticleVerificationForm(
            initial={'verification_status': article.verification_status}),
        'updates': article.story_updates.select_related('author'),
        'claims': article.claims.select_related('noted_by'),
        'evidence': article.evidence_records.select_related('added_by', 'claim'),
        'corrections': article.corrections.select_related('created_by'),
        'consents': article.consent_records.select_related('recorded_by'),
        'verification_events': article.verification_events.select_related('actor', 'claim')[:50],
        'audit_entries': StoryAudit.objects.filter(
            target_type='campaign', target_id=article.pk)[:50],
        'can_publish_updates': 'PUBLISH_STORY_UPDATES' in capabilities_for(request.user),
        'can_redact': 'PERFORM_REDACTION' in capabilities_for(request.user),
        'source_links': article.source_links.select_related(
            'report', 'report__lga', 'linked_by'),
        'link_report_form': LinkReportForm(),
        'linkable_reports': CommunityReport.objects.select_related('lga').order_by('-created_at')[:100],
        'can_manage_promises': 'MANAGE_PROMISES' in capabilities_for(request.user),
    }
    return render(request, 'story_intelligence/desk.html', context)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def save_profile(request, article_id):
    article = _article(article_id)
    profile = StoryProfile.objects.filter(article=article).first()
    form = StoryProfileForm(request.POST, instance=profile, article=article)
    if form.is_valid():
        saved = form.save(commit=False)
        saved.article = article
        saved.save()
        form.save_m2m()
        log_audit(request.user, 'STORY_PROFILE_SAVED', 'campaign', article.pk,
                  {'story_id': article.story_id})
        messages.success(request, 'Story profile saved.')
    else:
        messages.error(request, 'Please check the story profile form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def add_update(request, article_id):
    article = _article(article_id)
    form = StoryUpdateForm(request.POST)
    if form.is_valid():
        update = form.save(commit=False)
        update.article = article
        update.author = request.user
        if (form.cleaned_data.get('publish_now')
                and 'PUBLISH_STORY_UPDATES' in capabilities_for(request.user)):
            update.status = 'PUBLISHED'
            update.published_at = timezone.now()
        update.save()
        log_audit(request.user, 'STORY_UPDATE_ADDED', 'story_update', update.pk,
                  {'article_id': article.pk, 'status': update.status})
        messages.success(request, 'Story update saved.')
    else:
        messages.error(request, 'Please check the update form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('PUBLISH_STORY_UPDATES')
@require_POST
def publish_update(request, article_id, update_id):
    update = get_object_or_404(StoryUpdate, pk=update_id, article_id=article_id)
    update.status = 'PUBLISHED'
    update.published_at = timezone.now()
    update.save(update_fields=['status', 'published_at', 'updated_at'])
    log_audit(request.user, 'STORY_UPDATE_PUBLISHED', 'story_update', update.pk,
              {'article_id': update.article_id})
    messages.success(request, 'Story update published.')
    return redirect('story_intelligence:desk', article_id=article_id)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def delete_draft_update(request, article_id, update_id):
    update = get_object_or_404(StoryUpdate, pk=update_id, article_id=article_id)
    if update.status != 'DRAFT':
        messages.error(
            request,
            'Published updates are historical records and cannot be '
            'deleted; publish a correction instead.')
    else:
        update.delete()
        messages.success(request, 'Draft update deleted.')
    return redirect('story_intelligence:desk', article_id=article_id)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def add_claim(request, article_id):
    article = _article(article_id)
    form = ClaimForm(request.POST)
    if form.is_valid():
        claim = form.save(commit=False)
        claim.article = article
        claim.noted_by = request.user
        claim.save()
        log_audit(request.user, 'CLAIM_ADDED', 'claim', claim.pk,
                  {'article_id': article.pk, 'status': claim.status})
        messages.success(request, 'Claim recorded.')
    else:
        messages.error(request, 'Please check the claim form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def change_claim_status(request, article_id, claim_id):
    claim = get_object_or_404(Claim, pk=claim_id, article_id=article_id)
    form = ClaimStatusForm(request.POST)
    if form.is_valid():
        set_claim_status(claim, form.cleaned_data['status'], request.user,
                         reason=form.cleaned_data.get('reason', ''))
        messages.success(request, 'Claim status updated.')
    else:
        messages.error(request, 'Invalid claim status.')
    return redirect('story_intelligence:desk', article_id=article_id)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def add_evidence(request, article_id):
    article = _article(article_id)
    form = EvidenceForm(request.POST, request.FILES, article=article)
    if form.is_valid():
        evidence = form.save(commit=False)
        evidence.article = article
        evidence.added_by = request.user
        evidence.save()
        log_audit(request.user, 'EVIDENCE_ADDED', 'evidence', evidence.pk,
                  {'article_id': article.pk, 'kind': evidence.kind,
                   'is_public': evidence.is_public})
        messages.success(request, 'Evidence recorded.')
    else:
        messages.error(request, 'Please check the evidence form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def add_correction(request, article_id):
    article = _article(article_id)
    form = CorrectionForm(request.POST, article=article)
    if form.is_valid():
        correction = form.save(commit=False)
        correction.article = article
        correction.created_by = request.user
        correction.save()
        log_audit(request.user, 'CORRECTION_ADDED', 'correction', correction.pk,
                  {'article_id': article.pk, 'kind': correction.kind})
        messages.success(request, 'Correction recorded.')
    else:
        messages.error(request, 'Please check the correction form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def add_consent(request, article_id):
    article = _article(article_id)
    form = ConsentForm(request.POST)
    if form.is_valid():
        consent = form.save(commit=False)
        consent.article = article
        consent.recorded_by = request.user
        consent.save()
        # Audit metadata only: never the subject descriptor or notes.
        log_audit(request.user, 'CONSENT_RECORDED', 'consent_record', consent.pk,
                  {'article_id': article.pk, 'basis': consent.consent_basis})
        messages.success(request, 'Consent record saved (internal only).')
    else:
        messages.error(request, 'Please check the consent form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def set_verification(request, article_id):
    article = _article(article_id)
    form = ArticleVerificationForm(request.POST)
    if form.is_valid():
        set_article_verification_status(
            article, form.cleaned_data['verification_status'], request.user,
            reason=form.cleaned_data.get('reason', ''))
        messages.success(request, 'Article verification status updated.')
    else:
        messages.error(request, 'Invalid verification status.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('PERFORM_REDACTION')
def redact(request, article_id):
    article = _article(article_id)
    if request.method == 'POST':
        form = RedactionForm(request.POST)
        if form.is_valid():
            try:
                result = perform_redaction(
                    actor=request.user,
                    target_type=form.cleaned_data['target_type'],
                    target_id=form.cleaned_data['target_id'],
                    reason_category=form.cleaned_data['reason_category'])
            except RedactionError as exc:
                messages.error(
                    request,
                    f'Redaction could not be completed safely ({exc}). '
                    'Nothing was changed.')
                return redirect('story_intelligence:desk', article_id=article.pk)
            except (Campaign.DoesNotExist, Claim.DoesNotExist,
                    StoryUpdate.DoesNotExist, EvidenceRecord.DoesNotExist):
                messages.error(request, 'That record could not be found.')
                return redirect('story_intelligence:desk', article_id=article.pk)
            note = 'Redaction completed.'
            if result['file_removal'] == 'ok':
                note += ' The stored file was confirmed removed.'
            elif result['file_removal'] == 'not found':
                note += ' The stored file was already gone.'
            messages.success(request, note)
            return redirect('story_intelligence:desk', article_id=article.pk)
        messages.error(request, 'Please check the redaction form.')
    else:
        form = RedactionForm()
    context = {
        'article': article,
        'form': form,
        'updates': article.story_updates.all(),
        'claims': article.claims.all(),
        'evidence': article.evidence_records.all(),
    }
    return render(request, 'story_intelligence/redact.html', context)


# ─── Phase 2: Community Radar (story desk actions) ────────────────────────────

@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def link_report(request, article_id):
    article = _article(article_id)
    form = LinkReportForm(request.POST)
    if form.is_valid():
        report = get_object_or_404(CommunityReport, pk=form.cleaned_data['report_id'])
        _link, created = link_report_to_story(
            report, article, form.cleaned_data['kind'], request.user)
        messages.success(request, 'Community report linked to this story.'
                         if created else 'That report is already linked to this story.')
    else:
        messages.error(request, 'Please check the report link form.')
    return redirect('story_intelligence:desk', article_id=article.pk)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def unlink_report(request, article_id, link_id):
    link = get_object_or_404(StorySourceLink, pk=link_id, article_id=article_id)
    unlink_report_from_story(link, request.user)
    messages.success(request, 'Community report unlinked.')
    return redirect('story_intelligence:desk', article_id=article_id)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def claim_from_report(request, article_id, link_id):
    link = get_object_or_404(StorySourceLink, pk=link_id, article_id=article_id)
    claim = create_claim_from_report(link, request.user)
    messages.success(
        request,
        'Claim recorded from the community report. It starts as '
        '"Not established" — a community submission is never a verified '
        'claim until KPN checks it.')
    return redirect('story_intelligence:desk', article_id=article_id)


@story_capability_required('MANAGE_STORY_RECORDS')
def radar(request):
    """Community Radar desk: triage community reports into stories."""
    from django.db.models import Count
    unlinked_approved = (
        CommunityReport.objects.filter(status='APPROVED')
        .annotate(link_count=Count('story_links')).filter(link_count=0)
        .select_related('lga', 'zone').order_by('-created_at')[:50])
    reports = (CommunityReport.objects
               .select_related('lga', 'zone')
               .prefetch_related('story_links__article')
               .order_by('-created_at')[:50])
    context = {
        'unlinked_approved': unlinked_approved,
        'reports': reports,
        'published_articles': Campaign.objects.filter(
            status='PUBLISHED').order_by('-published_at')[:100],
        'link_kinds': StorySourceLink.KIND_CHOICES,
    }
    return render(request, 'story_intelligence/radar.html', context)


@story_capability_required('MANAGE_STORY_RECORDS')
@require_POST
def radar_link(request):
    report = get_object_or_404(CommunityReport, pk=request.POST.get('report_id'))
    article = get_object_or_404(Campaign, pk=request.POST.get('article_id'))
    kind = request.POST.get('kind', 'SOURCE')
    if kind not in dict(StorySourceLink.KIND_CHOICES):
        kind = 'SOURCE'
    _link, created = link_report_to_story(report, article, kind, request.user)
    messages.success(request, 'Report linked to the story.'
                     if created else 'That report is already linked to that story.')
    return redirect('story_intelligence:radar')


# ─── Phase 2: Promise desk (editorial) ────────────────────────────────────────

@story_capability_required('MANAGE_PROMISES')
def promise_desk(request):
    today = timezone.localdate()
    promises = (Promise.objects.select_related('institution', 'lga')
                .prefetch_related('updates'))
    context = {
        'promises': promises,
        'today': today,
        'institution_form': InstitutionForm(),
        'institutions': Institution.objects.all(),
        'can_verify': 'VERIFY_PROMISES' in capabilities_for(request.user),
    }
    return render(request, 'story_intelligence/promise_desk.html', context)


@story_capability_required('MANAGE_PROMISES')
@require_POST
def add_institution(request):
    form = InstitutionForm(request.POST)
    if form.is_valid():
        institution = form.save()
        log_audit(request.user, 'INSTITUTION_ADDED', 'institution', institution.pk,
                  {'name': institution.name})
        messages.success(request, 'Institution recorded.')
    else:
        messages.error(request, 'Please check the institution form.')
    return redirect('story_intelligence:promise_desk')


@story_capability_required('MANAGE_PROMISES')
def promise_create(request):
    if request.method == 'POST':
        form = PromiseForm(request.POST, request.FILES)
        if form.is_valid():
            promise = form.save(commit=False)
            promise.created_by = request.user
            promise.save()
            form.save_m2m()
            log_audit(request.user, 'PROMISE_CREATED', 'promise', promise.pk,
                      {'institution_id': promise.institution_id,
                       'status': promise.status})
            messages.success(request, 'Promise recorded. It starts as Announced.')
            return redirect('story_intelligence:promise_detail_desk', promise_id=promise.pk)
        messages.error(request, 'Please check the promise form.')
    else:
        form = PromiseForm()
    return render(request, 'story_intelligence/promise_form.html', {'form': form})


@story_capability_required('MANAGE_PROMISES')
def promise_detail_desk(request, promise_id):
    promise = get_object_or_404(
        Promise.objects.select_related('institution', 'lga', 'zone', 'ward'),
        pk=promise_id)
    context = {
        'promise': promise,
        'form': PromiseForm(instance=promise),
        'update_form': PromiseUpdateForm(initial={'update_date': timezone.localdate()}),
        'status_form': PromiseStatusForm(initial={'status': promise.status}),
        'claim_form': PromiseVerificationClaimForm(instance=promise, promise=promise),
        'updates': promise.updates.select_related('author'),
        'audit_entries': StoryAudit.objects.filter(
            target_type='promise', target_id=promise.pk)[:50],
        'can_verify': 'VERIFY_PROMISES' in capabilities_for(request.user),
        'has_verification_evidence': promise.has_verification_evidence(),
    }
    return render(request, 'story_intelligence/promise_detail_desk.html', context)


@story_capability_required('MANAGE_PROMISES')
@require_POST
def promise_save(request, promise_id):
    promise = get_object_or_404(Promise, pk=promise_id)
    form = PromiseForm(request.POST, request.FILES, instance=promise)
    if form.is_valid():
        form.save()
        log_audit(request.user, 'PROMISE_EDITED', 'promise', promise.pk, {})
        messages.success(request, 'Promise saved.')
    else:
        messages.error(request, 'Please check the promise form.')
    return redirect('story_intelligence:promise_detail_desk', promise_id=promise.pk)


@story_capability_required('MANAGE_PROMISES')
@require_POST
def promise_add_update(request, promise_id):
    promise = get_object_or_404(Promise, pk=promise_id)
    form = PromiseUpdateForm(request.POST)
    if form.is_valid():
        try:
            record_promise_update(
                promise, request.user,
                update_date=form.cleaned_data['update_date'],
                title=form.cleaned_data['title'],
                body=form.cleaned_data['body'],
                evidence_title=form.cleaned_data['evidence_title'],
                evidence_url=form.cleaned_data['evidence_url'],
                new_status=form.cleaned_data.get('new_status', ''))
        except PromiseError as exc:
            messages.error(
                request,
                'That status change was refused: a promise can only be '
                'marked "Completed — verified" with verification evidence '
                f'on record. ({exc}) Nothing was saved.')
        else:
            messages.success(request, 'Promise update recorded.')
    else:
        messages.error(request, 'Please check the update form.')
    return redirect('story_intelligence:promise_detail_desk', promise_id=promise.pk)


@story_capability_required('MANAGE_PROMISES')
@require_POST
def promise_change_status(request, promise_id):
    promise = get_object_or_404(Promise, pk=promise_id)
    form = PromiseStatusForm(request.POST)
    if form.is_valid():
        try:
            set_promise_status(promise, form.cleaned_data['status'],
                               request.user, note=form.cleaned_data.get('note', ''))
        except PromiseError as exc:
            messages.error(
                request,
                'That status change was refused: a promise can only be '
                'marked "Completed — verified" by a verifying editor with '
                f'verification evidence on record. ({exc}) Nothing changed.')
        else:
            messages.success(request, 'Promise status updated.')
    else:
        messages.error(request, 'Invalid promise status.')
    return redirect('story_intelligence:promise_detail_desk', promise_id=promise.pk)


@story_capability_required('MANAGE_PROMISES')
@require_POST
def promise_save_verification_claim(request, promise_id):
    promise = get_object_or_404(Promise, pk=promise_id)
    form = PromiseVerificationClaimForm(request.POST, instance=promise, promise=promise)
    if form.is_valid():
        form.save()
        log_audit(request.user, 'PROMISE_VERIFICATION_CLAIM_SET', 'promise',
                  promise.pk, {'claim_id': promise.verification_claim_id})
        messages.success(request, 'Verification claim link saved.')
    else:
        messages.error(request, 'Please check the verification claim form.')
    return redirect('story_intelligence:promise_detail_desk', promise_id=promise.pk)


# ─── Phase 2: Public Promise Tracker ──────────────────────────────────────────
# Public views: reader-safe fields ONLY. Institution contact notes,
# internal notes, audit entries and editor data are never exposed here.

# Period filter for the public tracker: applied to the date the
# institution announced the promise (`announced_on`). Values are the
# GET parameter; labels are what the filter panel shows.
PROMISE_PERIOD_CHOICES = [
    ('last_30', 'Last 30 days'),
    ('last_90', 'Last 90 days'),
    ('this_year', 'This year'),
    ('last_year', 'Last year'),
]


def _promise_stats(today):
    """At-a-glance figures for the public tracker, computed from real
    records only. "Delayed" is honest: explicitly marked DELAYED, or
    past the institution-announced deadline and not verified complete
    (the two sets overlap, so they are counted as one queryset)."""
    from django.db.models import Q
    base = Promise.objects.all()
    delayed = base.filter(
        Q(status='DELAYED')
        | Q(deadline__isnull=False, deadline__lt=today)
    ).exclude(status='COMPLETED_VERIFIED')
    return {
        'total': base.count(),
        'in_progress': base.filter(status='IN_PROGRESS').count(),
        'delayed': delayed.count(),
        'completed_verified': base.filter(status='COMPLETED_VERIFIED').count(),
    }


def promise_list(request):
    from datetime import timedelta

    from django.db.models import Max, Q

    from leadership.models import LGA

    today = timezone.localdate()
    params = {
        'q': request.GET.get('q', '').strip(),
        'sector': request.GET.get('sector', ''),
        'lga': request.GET.get('lga', ''),
        'institution': request.GET.get('institution', ''),
        'status': request.GET.get('status', ''),
        'period': request.GET.get('period', ''),
    }
    # Validate every filter against real vocabularies; anything else is
    # ignored rather than erroring or silently filtering to nothing.
    if params['sector'] not in dict(Promise.SECTOR_CHOICES):
        params['sector'] = ''
    if params['status'] not in dict(Promise.STATUS_CHOICES):
        params['status'] = ''
    if params['period'] not in dict(PROMISE_PERIOD_CHOICES):
        params['period'] = ''
    for key, model in (('lga', LGA), ('institution', Institution)):
        try:
            params[key] = int(params[key])
        except (TypeError, ValueError):
            params[key] = ''
        else:
            if not model.objects.filter(pk=params[key]).exists():
                params[key] = ''

    promises = (Promise.objects
                .select_related('institution', 'lga', 'zone', 'ward')
                .prefetch_related('stories')
                .annotate(last_update_date=Max('updates__update_date')))
    if params['q']:
        q = params['q']
        promises = promises.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
            | Q(institution__name__icontains=q)
            | Q(announced_by__icontains=q)
            | Q(lga__name__icontains=q) | Q(zone__name__icontains=q)
            | Q(ward__name__icontains=q))
    if params['sector']:
        promises = promises.filter(sector=params['sector'])
    if params['lga']:
        promises = promises.filter(lga_id=params['lga'])
    if params['institution']:
        promises = promises.filter(institution_id=params['institution'])
    if params['status']:
        promises = promises.filter(status=params['status'])
    if params['period'] == 'last_30':
        promises = promises.filter(announced_on__gte=today - timedelta(days=30))
    elif params['period'] == 'last_90':
        promises = promises.filter(announced_on__gte=today - timedelta(days=90))
    elif params['period'] == 'this_year':
        promises = promises.filter(announced_on__year=today.year)
    elif params['period'] == 'last_year':
        promises = promises.filter(announced_on__year=today.year - 1)
    promises = promises.distinct()

    # Attach display helpers the register cards need: the card
    # thumbnail is the promise's own uploaded image when it has one,
    # otherwise the first linked published story that carries a real
    # featured image (never a fabricated photo), and the delayed flag
    # follows the same honest definition as the headline statistic.
    promise_list_page = list(promises)
    for promise in promise_list_page:
        promise.thumbnail = promise.display_image
        promise.delayed_flag = promise.is_delayed(today)

    from .models import PromiseUpdate
    last_updated = None
    latest_promise = (Promise.objects.order_by('-updated_at')
                      .values_list('updated_at', flat=True).first())
    latest_update = (PromiseUpdate.objects.order_by('-updated_at')
                     .values_list('updated_at', flat=True).first())
    stamps = [s for s in (latest_promise, latest_update) if s]
    if stamps:
        last_updated = max(stamps)

    context = {
        'promises': promise_list_page,
        'result_count': len(promise_list_page),
        'stats': _promise_stats(today),
        'status_choices': Promise.STATUS_CHOICES,
        'sector_choices': Promise.SECTOR_CHOICES,
        'period_choices': PROMISE_PERIOD_CHOICES,
        'lgas': LGA.objects.select_related('zone').order_by('name'),
        'institutions': Institution.objects.all(),
        'params': params,
        'current_status': params['status'],
        'has_filters': any(params.values()),
        'last_updated': last_updated,
        'today': today,
    }
    return render(request, 'story_intelligence/promise_list.html', context)


def promise_detail(request, promise_id):
    promise = get_object_or_404(
        Promise.objects.select_related('institution', 'lga', 'zone', 'ward'),
        pk=promise_id)
    context = {
        'promise': promise,
        'updates': promise.updates.all(),
        'stories': promise.stories.filter(status='PUBLISHED'),
        'delayed_flag': promise.is_delayed(),
        # Provenance (intelligence Phase 5): this promise entered the
        # tracker through the monitoring candidate queue and a human
        # confirmation — say so on the public record.
        'detected_via_monitoring': promise.intelligence_candidates.filter(
            status='CONFIRMED').exists(),
    }
    return render(request, 'story_intelligence/promise_detail.html', context)
