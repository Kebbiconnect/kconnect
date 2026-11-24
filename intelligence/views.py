from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from editorial.models import Source
from leadership.capabilities import capabilities_for
from leadership.models import LGA
from story_intelligence.models import Institution, Promise

from . import alerts as alert_service
from . import article_locations as article_location_service
from . import briefings as briefing_service
from . import field_reports as field_report_service
from . import cycle as cycle_service
from . import desk as desk_service
from . import projects as project_service
from . import promise_detection
from . import relevance as relevance_service
from . import security as security_service
from . import tracking as tracking_service
from .map_data import VIEWBOX as MAP_VIEWBOX
from .forms import (
    AlertRuleForm, ArticleLocationForm, CandidateConfirmForm, CommunityForm,
    DistrictForm, FieldReportForm, GeoAliasForm, IncidentClaimForm,
    IncidentStatusForm, IntelligenceSourceForm, ProjectEvidenceForm,
    ProjectForm, ProjectMilestoneForm, ProjectStatusForm, RedactForm,
    SecurityIncidentForm,
)
from .models import (
    ALERT_RULES, DESK_STATES, PROJECT_STATUSES, Alert, AlertDelivery,
    AlertRule, ArticleLocation, Briefing, CollectionControl, CollectionRun,
    Community, District, EventCluster, FieldReport, GeoAlias, GeoEntity,
    IntelligenceAudit, IntelligenceCategory, Project, PromiseCandidate,
    RawPublication, SecurityIncident, SourceHealth,
)


def _can(user, capability):
    return bool(user.is_authenticated and (user.is_superuser or capability in capabilities_for(user)))


# The tracking map is the dedicated page for the roles responsible for
# tracking: the promise/project tracking roles (they view tracking and
# upload/update tracking records) plus intelligence reporting roles.
TRACKING_CAPABILITIES = (
    'MANAGE_PROMISES', 'VERIFY_PROMISES',
    'MANAGE_PROJECTS', 'VERIFY_PROJECTS',
    'VIEW_INTELLIGENCE_REPORTS',
)


def _can_any(user, capabilities):
    return any(_can(user, capability) for capability in capabilities)


def _require(user, capability):
    if not _can(user, capability):
        raise PermissionDenied


def _audit(user, action, target_type='', target_id=None, detail=None):
    IntelligenceAudit.objects.create(
        actor=user if user.is_authenticated else None, action=action,
        target_type=target_type, target_id=target_id, detail=detail or {})


@login_required
def overview(request):
    _require(request.user, 'VIEW_INTELLIGENCE')
    # Phase 6: restricted (sensitive-category) records are excluded
    # from every count and list on this page for anyone without
    # VIEW_SECURITY_DESK — enforced in the querysets, so the numbers
    # cannot leak that restricted material exists (Doc 07 §4).
    can_security = _can(request.user, 'VIEW_SECURITY_DESK')
    item_qs = security_service.visible_items(request.user, RawPublication.objects.all())
    cluster_qs = security_service.visible_clusters(
        request.user, EventCluster.objects.all())
    health = cycle_service.cycle_health()
    sources = Source.objects.all().prefetch_related('intelligence_health')
    source_rows = []
    failing = 0
    for source in sources:
        try:
            record = source.intelligence_health
            state = record.state()
        except SourceHealth.DoesNotExist:
            record, state = None, 'DISABLED' if not source.enabled else 'NEVER_RUN'
        if state == 'FAILING':
            failing += 1
        source_rows.append({'source': source, 'health': record, 'state': state})
    map_rows = tracking_service.lga_tracking_rows()
    context = {
        'can_manage_sources': _can(request.user, 'MANAGE_SOURCES'),
        'can_view_map': _can_any(request.user, TRACKING_CAPABILITIES),
        'map_rows': map_rows,
        'map_totals': tracking_service.totals_for(map_rows),
        'map_viewbox': MAP_VIEWBOX,
        'cycle_health': health,
        'control': CollectionControl.objects.get_or_create(pk=1)[0],
        'runs_total': CollectionRun.objects.count(),
        'runs_recent': CollectionRun.objects.all()[:10],
        'sources_total': sources.count(),
        'sources_enabled': sources.filter(enabled=True).count(),
        'sources_failing': failing,
        'source_rows': source_rows,
        'lga_count': LGA.objects.count(),
        'district_count': District.objects.count(),
        'community_count': Community.objects.count(),
        'geo_entity_count': GeoEntity.objects.count(),
        'pending_aliases': GeoAlias.objects.filter(status='PENDING').count(),
        'category_count': IntelligenceCategory.objects.count(),
        'raw_items_total': item_qs.count(),
        'raw_items_recent': item_qs.select_related('source')[:5],
        'relevant_items': item_qs.filter(
            relevance__in=['CONFIRMED', 'STRONG_POSSIBLE']).count(),
        'unprocessed_items': item_qs.filter(
            relevance__isnull=True).count(),
        'cluster_total': cluster_qs.filter(state='OPEN').count(),
        'can_security': can_security,
        'can_view_reports': _can(request.user, 'VIEW_INTELLIGENCE_REPORTS'),
        'my_unread_alerts': AlertDelivery.objects.filter(
            channel='DASHBOARD', recipient=request.user.get_username(),
            is_read=False).count(),
        'latest_briefing': Briefing.objects.first(),
        'can_review_desk': _can(request.user, 'REVIEW_INTELLIGENCE'),
        'can_manage_projects': _can(request.user, 'MANAGE_PROJECTS'),
        'project_total': Project.objects.count(),
        'project_reported_abandoned': Project.objects.filter(
            status='REPORTED_ABANDONED').count(),
        'project_verified_abandoned': Project.objects.filter(
            status='VERIFIED_ABANDONED').count(),
        'can_manage_promises': _can(request.user, 'MANAGE_PROMISES'),
        'pending_candidates': PromiseCandidate.objects.filter(
            status='PENDING').count(),
        'can_submit_field_reports': _can(
            request.user, 'SUBMIT_FIELD_REPORTS'),
        'my_field_reports': FieldReport.objects.filter(
            reporter=request.user).count(),
        'field_reports_total': FieldReport.objects.count(),
        'article_location_total': ArticleLocation.objects.count(),
    }
    if can_security:
        context['restricted_units'] = (
            security_service.restricted_clusters().count()
            + security_service.restricted_items().count())
        context['open_incidents'] = SecurityIncident.objects.filter(
            status='OPEN').count()
        context['restricted_state_units'] = (
            EventCluster.objects.filter(state='OPEN', desk_state='RESTRICTED').count()
            + RawPublication.objects.filter(
                cluster__isnull=True, desk_state='RESTRICTED').count())
    if context['can_review_desk']:
        from collections import Counter
        counter = Counter(
            cluster_qs.filter(state='OPEN')
            .values_list('desk_state', flat=True))
        counter.update(
            item_qs.filter(cluster__isnull=True)
            .values_list('desk_state', flat=True))
        context['desk_counts'] = {
            state: counter.get(state, 0) for state, _label in DESK_STATES}
        context['desk_waiting'] = (
            counter.get('DISCOVERED', 0) + counter.get('UNDER_REVIEW', 0)
            + counter.get('VERIFICATION_IN_PROGRESS', 0)
            + counter.get('NEEDS_INFO', 0))
    return render(request, 'intelligence/overview.html', context)


@login_required
def items(request):
    """Collected raw items with their Phase 3 processing results."""
    _require(request.user, 'VIEW_INTELLIGENCE')
    rows = security_service.visible_items(
        request.user,
        RawPublication.objects.select_related('source', 'duplicate_of', 'cluster')
        .prefetch_related('locations__lga', 'locations__district',
                          'locations__ward', 'locations__community',
                          'locations__geo_entity', 'category_links__category'))
    source_id = request.GET.get('source', '')
    status = request.GET.get('status', '')
    relevance = request.GET.get('relevance', '')
    category_id = request.GET.get('category', '')
    if source_id.isdigit():
        rows = rows.filter(source_id=int(source_id))
    if status in dict(RawPublication.FETCH_STATUS):
        rows = rows.filter(fetch_status=status)
    if relevance == 'UNPROCESSED':
        rows = rows.filter(relevance__isnull=True)
    elif relevance in dict(RawPublication.RELEVANCE):
        rows = rows.filter(relevance=relevance)
    if category_id.isdigit():
        rows = rows.filter(category_links__category_id=int(category_id)).distinct()
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'intelligence/items.html', {
        'page_obj': page,
        'sources': Source.objects.all(),
        'statuses': RawPublication.FETCH_STATUS,
        'relevances': RawPublication.RELEVANCE,
        'categories': IntelligenceCategory.objects.all(),
        'source_id': source_id,
        'status': status,
        'relevance': relevance,
        'category_id': category_id,
        'total': security_service.visible_items(
            request.user, RawPublication.objects.all()).count(),
        'can_review': _can(request.user, 'REVIEW_INTELLIGENCE'),
    })


@login_required
@require_POST
def item_reclassify(request, pk):
    """Staff reclassification of one item (Doc 03 §2.3 — audited)."""
    _require(request.user, 'REVIEW_INTELLIGENCE')
    pub = get_object_or_404(RawPublication, pk=pk)
    classification = request.POST.get('relevance', '')
    if classification in dict(RawPublication.RELEVANCE):
        relevance_service.set_manual_relevance(pub, classification, request.user)
        messages.success(request, 'Classification updated.')
    else:
        messages.error(request, 'Choose a classification.')
    return redirect(request.POST.get('next') or 'intelligence:items')


@login_required
def clusters(request):
    """Event clusters proposed by the Phase 3 clustering engine."""
    _require(request.user, 'VIEW_INTELLIGENCE')
    rows = security_service.visible_clusters(
        request.user,
        EventCluster.objects.filter(state='OPEN')
        .select_related('category', 'primary_lga')
        .annotate(member_count=Count('publications'))
        .order_by('-updated_at', '-pk'))
    category_id = request.GET.get('category', '')
    lga_id = request.GET.get('lga', '')
    if category_id.isdigit():
        rows = rows.filter(category_id=int(category_id))
    if lga_id.isdigit():
        rows = rows.filter(primary_lga_id=int(lga_id))
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'intelligence/clusters.html', {
        'page_obj': page,
        'categories': IntelligenceCategory.objects.all(),
        'lgas': LGA.objects.all().order_by('name'),
        'category_id': category_id,
        'lga_id': lga_id,
        'total': security_service.visible_clusters(
            request.user, EventCluster.objects.filter(state='OPEN')).count(),
    })


@login_required
def cluster_detail(request, pk):
    """One cluster and the member items that report the event."""
    _require(request.user, 'VIEW_INTELLIGENCE')
    cluster = get_object_or_404(
        security_service.visible_clusters(
            request.user,
            EventCluster.objects.select_related('category', 'primary_lga')),
        pk=pk)
    members = (cluster.publications.select_related('source')
               .prefetch_related('locations__lga', 'category_links__category')
               .order_by('published_at', 'discovered_at', 'pk'))
    earliest, latest = cluster.member_times()
    return render(request, 'intelligence/cluster_detail.html', {
        'cluster': cluster,
        'members': members,
        'earliest': earliest,
        'latest': latest,
    })


@login_required
def tracking_map(request):
    """Dedicated Kebbi State tracking map for the tracking roles.

    Desktop renders the geographic map (real COD-AB boundaries) beside
    the selected LGA's tracking details; mobile never renders the map
    (CSS hides it) and works from the location list alone. All figures
    are live counts — see intelligence/tracking.py.
    """
    if not _can_any(request.user, TRACKING_CAPABILITIES):
        raise PermissionDenied
    rows = tracking_service.lga_tracking_rows()
    selected = None
    selected_pk = request.GET.get('lga', '')
    if selected_pk.isdigit():
        for row in rows:
            if row['lga'].pk == int(selected_pk):
                promises = (
                    Promise.objects.filter(lga=row['lga'])
                    .select_related('institution')
                    .order_by('-announced_on', '-pk')[:50]
                )
                projects = (
                    Project.objects.filter(lga=row['lga'])
                    .select_related('institution')
                    .order_by('-updated_at', '-pk')[:50]
                )
                selected = {'row': row, 'promises': promises,
                            'projects': projects}
                break
    return render(request, 'intelligence/map.html', {
        'rows': rows,
        'totals': tracking_service.totals_for(rows),
        'project_totals': tracking_service.project_totals_for(rows),
        'selected': selected,
        'selected_pk': selected['row']['lga'].pk if selected else None,
        'map_viewbox': MAP_VIEWBOX,
        'can_manage_promises': _can(request.user, 'MANAGE_PROMISES'),
        'can_manage_projects': _can(request.user, 'MANAGE_PROJECTS'),
    })


@login_required
def sources(request):
    _require(request.user, 'VIEW_INTELLIGENCE')
    rows = []
    for source in Source.objects.all().prefetch_related('intelligence_health'):
        try:
            record = source.intelligence_health
            state = record.state()
        except SourceHealth.DoesNotExist:
            record, state = None, 'DISABLED' if not source.enabled else 'NEVER_RUN'
        rows.append({'source': source, 'health': record, 'state': state})
    return render(request, 'intelligence/sources.html', {
        'rows': rows, 'can_manage_sources': _can(request.user, 'MANAGE_SOURCES')})


@login_required
def source_edit(request, pk=None):
    _require(request.user, 'MANAGE_SOURCES')
    source = get_object_or_404(Source, pk=pk) if pk else Source()
    form = IntelligenceSourceForm(request.POST or None, instance=source)
    if request.method == 'POST' and form.is_valid():
        source = form.save()
        SourceHealth.objects.get_or_create(source=source)
        _audit(request.user, 'SOURCE_SAVED', 'Source', source.pk, {'source_id': source.pk})
        messages.success(request, 'Source saved.')
        return redirect('intelligence:sources')
    return render(request, 'intelligence/source_form.html', {'form': form, 'source': source})


@login_required
@require_POST
def control(request):
    _require(request.user, 'MANAGE_SOURCES')
    with transaction.atomic():
        CollectionControl.objects.get_or_create(pk=1)
        row = CollectionControl.objects.select_for_update().get(pk=1)
        row.enabled = request.POST.get('enabled') == 'yes'
        row.save(update_fields=['enabled', 'updated_at'])
        _audit(request.user, 'COLLECTION_RESUMED' if row.enabled else 'COLLECTION_PAUSED',
               'CollectionControl', row.pk)
    messages.success(request, 'Collection resumed.' if row.enabled else 'Collection paused.')
    return redirect('intelligence:overview')


@login_required
def lgas(request):
    _require(request.user, 'VIEW_INTELLIGENCE')
    rows = (
        LGA.objects.select_related('zone')
        .annotate(ward_count=Count('wards', distinct=True),
                  district_count=Count('districts', distinct=True),
                  community_count=Count('communities', distinct=True))
        .order_by('name')
    )
    return render(request, 'intelligence/lgas.html', {'lgas': rows})


@login_required
def lga_detail(request, pk):
    _require(request.user, 'VIEW_INTELLIGENCE')
    lga = get_object_or_404(LGA.objects.select_related('zone'), pk=pk)
    can_manage = _can(request.user, 'MANAGE_SOURCES')
    return render(request, 'intelligence/lga_detail.html', {
        'lga': lga,
        'districts': lga.districts.all(),
        'wards': lga.wards.all(),
        'communities': lga.communities.select_related('ward', 'district'),
        'entities': lga.geo_entities.all(),
        'aliases': GeoAlias.objects.filter(lga=lga),
        'can_manage_sources': can_manage,
        'district_form': DistrictForm() if can_manage else None,
        'community_form': CommunityForm(lga=lga) if can_manage else None,
    })


@login_required
@require_POST
def district_add(request, pk):
    _require(request.user, 'MANAGE_SOURCES')
    lga = get_object_or_404(LGA, pk=pk)
    form = DistrictForm(request.POST)
    if form.is_valid():
        district = form.save(commit=False)
        district.lga = lga
        district.save()
        _audit(request.user, 'DISTRICT_CREATED', 'District', district.pk, {'lga_id': lga.pk})
        messages.success(request, 'District added.')
    else:
        messages.error(request, 'District could not be added. Check the name.')
    return redirect('intelligence:lga_detail', pk=lga.pk)


@login_required
@require_POST
def community_add(request, pk):
    _require(request.user, 'MANAGE_SOURCES')
    lga = get_object_or_404(LGA, pk=pk)
    form = CommunityForm(request.POST, lga=lga)
    if form.is_valid():
        community = form.save(commit=False)
        community.lga = lga
        community.full_clean()
        community.save()
        _audit(request.user, 'COMMUNITY_CREATED', 'Community', community.pk, {'lga_id': lga.pk})
        messages.success(request, 'Community added.')
    else:
        messages.error(request, 'Community could not be added. Check the name and links.')
    return redirect('intelligence:lga_detail', pk=lga.pk)


@login_required
def aliases(request):
    _require(request.user, 'VIEW_INTELLIGENCE')
    status = request.GET.get('status', '')
    rows = GeoAlias.objects.select_related('lga', 'district', 'ward', 'community', 'geo_entity')
    if status in dict(GeoAlias.STATUS):
        rows = rows.filter(status=status)
    can_manage = _can(request.user, 'MANAGE_SOURCES')
    form = GeoAliasForm(request.POST or None) if can_manage else None
    if request.method == 'POST' and can_manage and form.is_valid():
        alias = form.save(commit=False)
        alias.created_by = request.user
        alias.save()
        _audit(request.user, 'ALIAS_CREATED', 'GeoAlias', alias.pk, {'status': alias.status})
        messages.success(request, 'Alias recorded for review.')
        return redirect('intelligence:aliases')
    return render(request, 'intelligence/aliases.html', {
        'aliases': rows, 'form': form, 'status': status,
        'statuses': GeoAlias.STATUS, 'can_manage_sources': can_manage})


@login_required
@require_POST
def alias_review(request, pk, decision):
    _require(request.user, 'MANAGE_SOURCES')
    alias = get_object_or_404(GeoAlias, pk=pk)
    alias.status = decision
    alias.reviewed_by = request.user
    alias.reviewed_at = timezone.now()
    alias.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    _audit(request.user, 'ALIAS_APPROVED' if decision == 'APPROVED' else 'ALIAS_REJECTED',
           'GeoAlias', alias.pk, {'status': decision})
    messages.success(request, f'Alias {decision.lower()}.')
    return redirect('intelligence:aliases')


# ---------------------------------------------------------------------------
# Phase 4 — verification desk (Lane 2, human-gated)
# ---------------------------------------------------------------------------

_DESK_STATE_LABELS = dict(DESK_STATES)
_RELEVANCE_RANK = {'CONFIRMED': 0, 'STRONG_POSSIBLE': 1, 'UNCERTAIN': 2,
                   'NOT_RELEVANT': 3, None: 4}


def _unit_row(kind, obj, members):
    """One desk-queue row for a cluster or a standalone item."""
    if members:
        relevance = min((m.relevance for m in members),
                        key=lambda value: _RELEVANCE_RANK.get(value, 4))
        first_seen = min(m.event_time for m in members)
    else:
        relevance, first_seen = None, obj.created_at
    return {
        'kind': kind, 'obj': obj, 'title': obj.title,
        'state': obj.desk_state,
        'state_label': _DESK_STATE_LABELS.get(obj.desk_state, obj.desk_state),
        'category': desk_service.unit_category(obj),
        'lga': desk_service.unit_lga(obj),
        'relevance': relevance,
        'first_seen': first_seen,
        'member_count': len(members),
        'assigned_to': obj.assigned_to,
        'url': reverse(
            'intelligence:desk_cluster' if kind == 'cluster'
            else 'intelligence:desk_item', args=[obj.pk]),
    }


def _check_visible(user, unit):
    """Restricted units 404 for anyone without VIEW_SECURITY_DESK,
    even by direct URL (Doc 07 §4)."""
    if security_service.unit_is_restricted(unit) \
            and not security_service.is_holder(user):
        raise Http404


def _desk_units(user):
    units = []
    clusters = security_service.visible_clusters(
        user,
        EventCluster.objects.filter(state='OPEN')
        .select_related('category', 'primary_lga', 'assigned_to')
        .prefetch_related('publications'))
    for cluster in clusters:
        units.append(_unit_row('cluster', cluster,
                               list(cluster.publications.all())))
    items = security_service.visible_items(
        user,
        RawPublication.objects.filter(cluster__isnull=True)
        .select_related('source', 'assigned_to')
        .prefetch_related('category_links__category',
                          'locations__lga'))
    for item in items:
        units.append(_unit_row('item', item, [item]))
    units.sort(key=lambda row: row['first_seen'], reverse=True)
    return units


@login_required
def desk(request):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    state = request.GET.get('state', '')
    relevance = request.GET.get('relevance', '')
    category = request.GET.get('category', '')
    lga = request.GET.get('lga', '')
    age = request.GET.get('age', '')
    units = _desk_units(request.user)
    total = len(units)
    if state:
        units = [row for row in units if row['state'] == state]
    if relevance:
        units = [row for row in units if row['relevance'] == relevance]
    if category:
        units = [row for row in units
                 if row['category'] and row['category'].slug == category]
    if lga:
        units = [row for row in units
                 if row['lga'] and str(row['lga'].pk) == lga]
    if age:
        now = timezone.now()
        if age == '24h':
            units = [row for row in units
                     if (now - row['first_seen']).total_seconds() <= 86400]
        elif age == '3d':
            units = [row for row in units
                     if 86400 < (now - row['first_seen']).total_seconds()
                     <= 3 * 86400]
        elif age == 'older':
            units = [row for row in units
                     if (now - row['first_seen']).total_seconds() > 3 * 86400]
    page = Paginator(units, 25).get_page(request.GET.get('page'))
    return render(request, 'intelligence/desk.html', {
        'page_obj': page,
        'states': DESK_STATES,
        'categories': IntelligenceCategory.objects.all(),
        'lgas': LGA.objects.all().order_by('name'),
        'filters': {'state': state, 'relevance': relevance,
                    'category': category, 'lga': lga, 'age': age},
        'total_units': total,
    })


def _reviewers():
    User = get_user_model()
    reviewers = []
    for candidate in User.objects.filter(is_active=True).order_by('username'):
        if desk_service.has_capability(candidate, 'REVIEW_INTELLIGENCE') \
                or desk_service.has_capability(candidate, 'VERIFY_INTELLIGENCE'):
            reviewers.append(candidate)
    return reviewers


def _desk_detail_context(request, unit, kind):
    members = (RawPublication.objects.filter(pk__in=[
        member.pk for member in desk_service.unit_members(unit)])
        .select_related('source', 'duplicate_of', 'duplicate_of__source')
        .prefetch_related('locations__lga', 'locations__ward',
                          'locations__district', 'locations__community',
                          'locations__geo_entity',
                          'category_links__category',
                          'near_duplicates')
        .order_by('published_at', 'discovered_at', 'pk'))
    sources, seen = [], set()
    for member in members:
        if member.source_id not in seen:
            seen.add(member.source_id)
            sources.append(desk_service.source_credibility(member.source))
    other_clusters = []
    if kind == 'cluster':
        other_clusters = security_service.visible_clusters(
            request.user,
            EventCluster.objects.filter(state='OPEN')
            .exclude(pk=unit.pk).order_by('-updated_at'))
    return {
        'unit': unit, 'kind': kind, 'members': members,
        'credibility': sources,
        'decisions': unit.review_decisions.select_related('actor').all(),
        'action_choices': [
            (action, desk_service.ACTION_BUTTON_LABELS[action])
            for action in desk_service.available_actions(unit, request.user)],
        'can_assign': desk_service.has_capability(
            request.user, 'REVIEW_INTELLIGENCE'),
        'can_merge_split': kind == 'cluster' and desk_service.has_capability(
            request.user, 'REVIEW_INTELLIGENCE'),
        'other_clusters': other_clusters,
        'reviewers': _reviewers(),
        'can_convert': (
            unit.desk_state == 'APPROVED' and not unit.article_id
            and desk_service.has_capability(request.user, 'APPROVE_INTELLIGENCE')),
        'can_create_project': (
            unit.desk_state in ('VERIFIED', 'APPROVED', 'PUBLISHED')
            and _can(request.user, 'MANAGE_PROJECTS')),
        'unit_projects': unit.projects.all(),
        'state_label': _DESK_STATE_LABELS.get(unit.desk_state, unit.desk_state),
        'category': desk_service.unit_category(unit),
        'lga': desk_service.unit_lga(unit),
        'sensitive': desk_service.unit_is_sensitive(unit),
    }


@login_required
def desk_cluster(request, pk):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    unit = get_object_or_404(
        EventCluster.objects.select_related(
            'category', 'primary_lga', 'assigned_to', 'article'),
        pk=pk, state='OPEN')
    _check_visible(request.user, unit)
    return render(request, 'intelligence/desk_detail.html',
                  _desk_detail_context(request, unit, 'cluster'))


@login_required
def desk_item(request, pk):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    unit = get_object_or_404(
        RawPublication.objects.select_related('source', 'assigned_to',
                                              'article'),
        pk=pk, cluster__isnull=True)
    _check_visible(request.user, unit)
    return render(request, 'intelligence/desk_detail.html',
                  _desk_detail_context(request, unit, 'item'))


def _desk_unit_or_404(kind, pk, user=None):
    if kind == 'cluster':
        unit = get_object_or_404(EventCluster, pk=pk, state='OPEN')
    else:
        unit = get_object_or_404(RawPublication, pk=pk, cluster__isnull=True)
    if user is not None:
        _check_visible(user, unit)
    return unit


def _desk_redirect(kind, pk):
    return redirect('intelligence:desk_cluster' if kind == 'cluster'
                    else 'intelligence:desk_item', pk=pk)


@login_required
@require_POST
def desk_transition(request, kind, pk):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    unit = _desk_unit_or_404(kind, pk, request.user)
    try:
        desk_service.apply_transition(
            unit, request.user, request.POST.get('action', ''),
            note=request.POST.get('note', ''))
        messages.success(request, 'Decision recorded.')
    except desk_service.DeskError as exc:
        messages.error(request, str(exc))
    return _desk_redirect(kind, pk)


@login_required
@require_POST
def desk_assign(request, kind, pk):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    unit = _desk_unit_or_404(kind, pk, request.user)
    assignee = get_user_model().objects.filter(
        pk=request.POST.get('assignee', '')).first()
    try:
        desk_service.assign_reviewer(unit, request.user, assignee)
        messages.success(request, 'Reviewer assigned.')
    except desk_service.DeskError as exc:
        messages.error(request, str(exc))
    return _desk_redirect(kind, pk)


@login_required
@require_POST
def desk_merge(request, pk):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    target = get_object_or_404(EventCluster, pk=pk, state='OPEN')
    _check_visible(request.user, target)
    source_cluster = get_object_or_404(
        EventCluster, pk=request.POST.get('other_cluster', ''), state='OPEN')
    _check_visible(request.user, source_cluster)
    try:
        desk_service.merge_clusters(request.user, target, source_cluster,
                                    note=request.POST.get('note', ''))
        messages.success(request, 'Clusters merged.')
    except desk_service.DeskError as exc:
        messages.error(request, str(exc))
    return _desk_redirect('cluster', pk)


@login_required
@require_POST
def desk_split(request, pk):
    _require(request.user, 'REVIEW_INTELLIGENCE')
    cluster = get_object_or_404(EventCluster, pk=pk, state='OPEN')
    _check_visible(request.user, cluster)
    try:
        desk_service.split_cluster(request.user, cluster,
                                   request.POST.getlist('items'),
                                   note=request.POST.get('note', ''))
        messages.success(request, 'Cluster split.')
    except desk_service.DeskError as exc:
        messages.error(request, str(exc))
    return _desk_redirect('cluster', pk)


@login_required
def desk_convert(request, kind, pk):
    _require(request.user, 'APPROVE_INTELLIGENCE')
    unit = _desk_unit_or_404(kind, pk, request.user)
    if request.method == 'POST':
        if request.POST.get('confirm') != 'yes':
            messages.error(
                request,
                'Nothing was created. Conversion needs the confirmation '
                'step to be completed.')
            return _desk_redirect(kind, pk)
        try:
            article = desk_service.convert_to_draft(unit, request.user)
        except desk_service.DeskError as exc:
            messages.error(request, str(exc))
            return _desk_redirect(kind, pk)
        messages.success(
            request,
            'Newsroom draft created. It is not published — it goes '
            'through the normal newsroom review and publish flow.')
        return redirect('campaigns:edit_article', article_id=article.pk)
    if unit.desk_state != 'APPROVED' or unit.article_id:
        messages.error(
            request, 'Only an approved unit with no draft yet can be '
            'converted.')
        return _desk_redirect(kind, pk)
    category = desk_service.unit_category(unit)
    return render(request, 'intelligence/desk_convert.html', {
        'unit': unit, 'kind': kind,
        'members': desk_service.unit_members(unit),
        'category': category,
        'mapped_category': desk_service.CATEGORY_MAP.get(
            category.slug if category else '', 'GENERAL'),
    })


# ---------------------------------------------------------------------------
# Phase 5 — public project tracker (staff management) + promise candidates
# ---------------------------------------------------------------------------

@login_required
def projects(request):
    """Staff project register (MANAGE_PROJECTS)."""
    _require(request.user, 'MANAGE_PROJECTS')
    rows = (Project.objects.select_related('institution', 'lga')
            .order_by('-updated_at', '-pk'))
    status = request.GET.get('status', '')
    lga_id = request.GET.get('lga', '')
    if status in dict(PROJECT_STATUSES):
        rows = rows.filter(status=status)
    if lga_id.isdigit():
        rows = rows.filter(lga_id=int(lga_id))
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'intelligence/projects.html', {
        'page_obj': page,
        'statuses': PROJECT_STATUSES,
        'status': status,
        'lgas': LGA.objects.all().order_by('name'),
        'lga_id': lga_id,
        'total': Project.objects.count(),
        'can_verify_projects': _can(request.user, 'VERIFY_PROJECTS'),
    })


@login_required
def project_new(request):
    _require(request.user, 'MANAGE_PROJECTS')
    form = ProjectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        project = project_service.create_project(
            request.user, **form.cleaned_data)
        messages.success(
            request, f'Project registered as {project.project_code}.')
        return redirect('intelligence:project_detail', pk=project.pk)
    return render(request, 'intelligence/project_form.html', {
        'form': form, 'project': None, 'from_unit': None})


@login_required
def project_from_unit(request, kind, pk):
    """Register a project proposed from a verified desk unit.

    The form is prefilled only from the unit's own records; staff
    confirm and complete it. The created project keeps the link back
    to the unit as its evidence provenance.
    """
    _require(request.user, 'MANAGE_PROJECTS')
    unit = _desk_unit_or_404(kind, pk, request.user)
    try:
        initial = project_service.propose_from_unit(request.user, unit)
    except project_service.ProjectError as exc:
        messages.error(request, str(exc))
        return _desk_redirect(kind, pk)
    form = ProjectForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        links = ({'source_cluster': unit} if kind == 'cluster'
                 else {'source_publication': unit})
        project = project_service.create_project(
            request.user, **links, **form.cleaned_data)
        messages.success(
            request, f'Project registered as {project.project_code}.')
        return redirect('intelligence:project_detail', pk=project.pk)
    return render(request, 'intelligence/project_form.html', {
        'form': form, 'project': None, 'from_unit': unit,
        'from_kind': kind})


@login_required
def project_detail(request, pk):
    _require(request.user, 'MANAGE_PROJECTS')
    project = get_object_or_404(
        Project.objects.select_related(
            'institution', 'lga', 'ward', 'district', 'community',
            'assigned_officer', 'source_cluster', 'source_publication'),
        pk=pk)
    return render(request, 'intelligence/project_manage.html', {
        'project': project,
        'milestones': project.milestones.select_related('recorded_by'),
        'evidence': project.evidence.select_related('captured_by'),
        'status_form': ProjectStatusForm(initial={'status': project.status}),
        'milestone_form': ProjectMilestoneForm(
            initial={'date': timezone.localdate()}),
        'evidence_form': ProjectEvidenceForm(),
        'can_verify_projects': _can(request.user, 'VERIFY_PROJECTS'),
        'qualifying_evidence': project_service.qualifying_evidence(project),
    })


@login_required
def project_edit(request, pk):
    _require(request.user, 'MANAGE_PROJECTS')
    project = get_object_or_404(Project, pk=pk)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _audit(request.user, 'PROJECT_EDITED', 'Project', project.pk, {})
        messages.success(request, 'Project updated.')
        return redirect('intelligence:project_detail', pk=project.pk)
    return render(request, 'intelligence/project_form.html', {
        'form': form, 'project': project, 'from_unit': None})


@login_required
@require_POST
def project_status(request, pk):
    _require(request.user, 'MANAGE_PROJECTS')
    project = get_object_or_404(Project, pk=pk)
    form = ProjectStatusForm(request.POST)
    if form.is_valid():
        try:
            project_service.set_project_status(
                project, form.cleaned_data['status'], request.user,
                note=form.cleaned_data.get('note', ''))
            messages.success(request, 'Project status updated.')
        except (project_service.ProjectError, PermissionDenied) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'Choose a status.')
    return redirect('intelligence:project_detail', pk=pk)


@login_required
@require_POST
def project_milestone(request, pk):
    _require(request.user, 'MANAGE_PROJECTS')
    project = get_object_or_404(Project, pk=pk)
    form = ProjectMilestoneForm(request.POST)
    if form.is_valid():
        project_service.add_milestone(
            project, request.user, date=form.cleaned_data['date'],
            title=form.cleaned_data['title'],
            body=form.cleaned_data.get('body', ''))
        messages.success(request, 'Timeline entry added.')
    else:
        messages.error(request, 'Check the timeline entry.')
    return redirect('intelligence:project_detail', pk=pk)


@login_required
@require_POST
def project_evidence(request, pk):
    _require(request.user, 'MANAGE_PROJECTS')
    project = get_object_or_404(Project, pk=pk)
    form = ProjectEvidenceForm(request.POST, request.FILES)
    if form.is_valid():
        project_service.add_evidence(
            project, request.user, **form.cleaned_data)
        messages.success(request, 'Evidence filed.')
    else:
        messages.error(request, 'Check the evidence form.')
    return redirect('intelligence:project_detail', pk=pk)


@login_required
def promise_candidates(request):
    """The promise-candidate queue (MANAGE_PROMISES).

    Detector leads only — nothing here is public. Confirming creates
    a real Promise on the promise tracker; dismissing requires a
    recorded reason.
    """
    _require(request.user, 'MANAGE_PROMISES')
    status = request.GET.get('status', 'PENDING')
    if status not in dict(PromiseCandidate.STATUS):
        status = 'PENDING'
    rows = (PromiseCandidate.objects.filter(status=status)
            .select_related('publication__source', 'cluster', 'lga',
                            'promise', 'decided_by')
            .order_by('-created_at', '-pk'))
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'intelligence/promise_candidates.html', {
        'page_obj': page,
        'status': status,
        'statuses': PromiseCandidate.STATUS,
        'pending_total': PromiseCandidate.objects.filter(
            status='PENDING').count(),
    })


@login_required
def promise_candidate_confirm(request, pk):
    _require(request.user, 'MANAGE_PROMISES')
    candidate = get_object_or_404(
        PromiseCandidate.objects.select_related(
            'publication__source', 'lga', 'cluster'), pk=pk)
    if candidate.status != 'PENDING':
        messages.error(request, 'This candidate has already been decided.')
        return redirect('intelligence:promise_candidates')
    pub = candidate.publication
    institution = None
    if candidate.institution_name:
        institution = Institution.objects.filter(
            name=candidate.institution_name).first()
    initial = {
        'institution': institution,
        'institution_name': '' if institution else candidate.institution_name,
        'title': promise_detection._default_title(candidate),
        'description': candidate.quote,
        'announced_on': (pub.published_at or pub.discovered_at).date(),
    }
    form = CandidateConfirmForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            promise = promise_detection.confirm_candidate(
                candidate, request.user,
                institution=form.cleaned_data.get('institution'),
                institution_name=form.cleaned_data.get('institution_name', ''),
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                announced_by=form.cleaned_data.get('announced_by', ''),
                announced_on=form.cleaned_data['announced_on'],
                deadline=form.cleaned_data.get('deadline'),
                sector=form.cleaned_data.get('sector', ''))
        except (promise_detection.CandidateError, PermissionDenied) as exc:
            messages.error(request, str(exc))
            return redirect('intelligence:promise_candidates')
        messages.success(
            request,
            f'Promise recorded on the tracker ({promise.public_code}).')
        return redirect('intelligence:promise_candidates')
    return render(request, 'intelligence/promise_candidate_confirm.html', {
        'candidate': candidate, 'form': form})


@login_required
@require_POST
def promise_candidate_dismiss(request, pk):
    _require(request.user, 'MANAGE_PROMISES')
    candidate = get_object_or_404(PromiseCandidate, pk=pk)
    try:
        promise_detection.dismiss_candidate(
            candidate, request.user,
            reason=request.POST.get('reason', ''))
        messages.success(request, 'Candidate dismissed.')
    except (promise_detection.CandidateError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect('intelligence:promise_candidates')


# ---------------------------------------------------------------------------
# Phase 6 — security desk, alerts, briefings.
#
# Every security view is gated on VIEW_SECURITY_DESK (held by exactly
# two staff titles — owner decision D6). Restricted records never
# reach these handlers for anyone else: the URLs 403 at the gate, and
# the general surfaces exclude the records in their querysets.
# Viewing a restricted unit or incident writes an audit row (Doc 07
# §4: restricted-record access is logged).
# ---------------------------------------------------------------------------

def _security_unit(kind, pk):
    if kind == 'cluster':
        return get_object_or_404(EventCluster, pk=pk, state='OPEN')
    return get_object_or_404(RawPublication, pk=pk, cluster__isnull=True)


def _security_redirect(kind, pk):
    return redirect('intelligence:security_unit', kind=kind, pk=pk)


@login_required
def security_desk(request):
    _require(request.user, 'VIEW_SECURITY_DESK')
    clusters = security_service.restricted_clusters()
    items = security_service.restricted_items()
    rows = []
    for cluster in clusters:
        rows.append(_unit_row('cluster', cluster,
                              list(cluster.publications.all())))
    for item in items:
        rows.append(_unit_row('item', item, [item]))
    rows.sort(key=lambda row: row['first_seen'], reverse=True)
    incidents = (SecurityIncident.objects.select_related('lga', 'cluster')
                 .prefetch_related('claims'))
    return render(request, 'intelligence/security.html', {
        'rows': rows,
        'total_units': len(rows),
        'incidents': incidents,
        'states': DESK_STATES,
    })


@login_required
def security_unit(request, kind, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    unit = _security_unit(kind, pk)
    if not security_service.unit_is_restricted(unit):
        # Not a restricted unit: its home is the general desk.
        return _desk_redirect(kind, pk)
    _audit(request.user, 'SECURITY_VIEW',
           'EventCluster' if kind == 'cluster' else 'RawPublication',
           unit.pk, {})
    members = (RawPublication.objects.filter(pk__in=[
        member.pk for member in desk_service.unit_members(unit)])
        .select_related('source', 'duplicate_of')
        .prefetch_related('locations__lga', 'category_links__category')
        .order_by('published_at', 'discovered_at', 'pk'))
    incidents = unit.security_incidents.select_related('lga').all()
    return render(request, 'intelligence/security_detail.html', {
        'unit': unit, 'kind': kind, 'members': members,
        'incidents': incidents,
        'decisions': unit.review_decisions.select_related('actor').all(),
        'action_choices': [
            (action, desk_service.ACTION_BUTTON_LABELS[action])
            for action in desk_service.available_actions(unit, request.user)],
        'state_label': _DESK_STATE_LABELS.get(unit.desk_state, unit.desk_state),
        'category': desk_service.unit_category(unit),
        'lga': desk_service.unit_lga(unit),
        'redact_form': RedactForm(),
    })


@login_required
@require_POST
def security_transition(request, kind, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    unit = _security_unit(kind, pk)
    if not security_service.unit_is_restricted(unit):
        raise Http404
    try:
        desk_service.apply_transition(
            unit, request.user, request.POST.get('action', ''),
            note=request.POST.get('note', ''))
        messages.success(request, 'Decision recorded.')
    except desk_service.DeskError as exc:
        messages.error(request, str(exc))
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    return _security_redirect(kind, pk)


@login_required
@require_POST
def security_working_copy(request, kind, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    unit = _security_unit(kind, pk)
    if not security_service.unit_is_restricted(unit):
        raise Http404
    action = request.POST.get('action', '')
    try:
        if action == 'prepare':
            security_service.prepare_working_copy(unit, request.user)
            messages.success(request, 'Working copy prepared.')
        elif action == 'redact':
            form = RedactForm(request.POST)
            if form.is_valid():
                count = security_service.redact_passage(
                    unit, request.user, form.cleaned_data['passage'])
                messages.success(
                    request, f'Passage blanked ({count} occurrence(s)). '
                             'The original evidence is unchanged.')
            else:
                messages.error(request, 'Enter the exact passage to blank out.')
        else:
            messages.error(request, 'Unknown working-copy action.')
    except security_service.SecurityError as exc:
        messages.error(request, str(exc))
    return _security_redirect(kind, pk)


@login_required
def security_incident_new(request):
    _require(request.user, 'VIEW_SECURITY_DESK')
    unit = None
    kind = request.GET.get('kind', '')
    pk = request.GET.get('pk', '')
    if kind in ('cluster', 'item') and pk.isdigit():
        unit = _security_unit(kind, int(pk))
    if request.method == 'POST':
        form = SecurityIncidentForm(request.POST)
        if form.is_valid():
            incident = security_service.create_incident(
                request.user, unit=unit, **form.cleaned_data)
            messages.success(request, 'Incident recorded on the security desk.')
            return redirect('intelligence:security_incident', pk=incident.pk)
    else:
        initial = {}
        if unit is not None:
            initial = {'title': unit.title[:300],
                       'lga': desk_service.unit_lga(unit)}
        form = SecurityIncidentForm(initial=initial)
    return render(request, 'intelligence/incident_form.html', {
        'form': form, 'unit': unit, 'kind': kind,
    })


@login_required
def security_incident(request, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    incident = get_object_or_404(
        SecurityIncident.objects.select_related('lga', 'cluster', 'publication'),
        pk=pk)
    _audit(request.user, 'SECURITY_VIEW', 'SecurityIncident', incident.pk, {})
    return render(request, 'intelligence/incident_detail.html', {
        'incident': incident,
        'claims': incident.claims.select_related('created_by').all(),
        'claim_form': IncidentClaimForm(),
        'status_form': IncidentStatusForm(initial={'status': incident.status}),
        'redact_form': RedactForm(),
    })


@login_required
@require_POST
def security_incident_claim(request, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    incident = get_object_or_404(SecurityIncident, pk=pk)
    form = IncidentClaimForm(request.POST)
    if form.is_valid():
        security_service.add_claim(request.user, incident, **form.cleaned_data)
        messages.success(
            request, 'Figure recorded as an attributed claim. It is '
                     'never shown as a verified fact.')
    else:
        messages.error(request, 'A claim needs a label, a count and the '
                                  'source that reported it.')
    return redirect('intelligence:security_incident', pk=pk)


@login_required
@require_POST
def security_incident_status(request, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    incident = get_object_or_404(SecurityIncident, pk=pk)
    form = IncidentStatusForm(request.POST)
    if form.is_valid():
        try:
            security_service.set_incident_status(
                request.user, incident, form.cleaned_data['status'])
            messages.success(request, 'Incident status updated.')
        except security_service.SecurityError as exc:
            messages.error(request, str(exc))
    return redirect('intelligence:security_incident', pk=pk)


@login_required
@require_POST
def security_incident_redact(request, pk):
    _require(request.user, 'VIEW_SECURITY_DESK')
    incident = get_object_or_404(SecurityIncident, pk=pk)
    form = RedactForm(request.POST)
    if form.is_valid():
        try:
            count = security_service.redact_incident_notes(
                request.user, incident, form.cleaned_data['passage'])
            messages.success(
                request, f'Passage blanked ({count} occurrence(s)).')
        except security_service.SecurityError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'Enter the exact passage to blank out.')
    return redirect('intelligence:security_incident', pk=pk)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@login_required
def alerts_list(request):
    _require(request.user, 'VIEW_INTELLIGENCE')
    deliveries = (AlertDelivery.objects.filter(
        channel='DASHBOARD', recipient=request.user.get_username())
        .select_related('alert').order_by('-created_at', '-pk'))
    page = Paginator(deliveries, 25).get_page(request.GET.get('page'))
    return render(request, 'intelligence/alerts.html', {
        'page_obj': page,
        'unread': deliveries.filter(is_read=False).count(),
        'can_configure': _can(request.user, 'MANAGE_SOURCES'),
    })


@login_required
@require_POST
def alert_mark_read(request, pk):
    _require(request.user, 'VIEW_INTELLIGENCE')
    delivery = get_object_or_404(
        AlertDelivery, pk=pk, channel='DASHBOARD',
        recipient=request.user.get_username())
    if not delivery.is_read:
        delivery.is_read = True
        delivery.read_at = timezone.now()
        delivery.save(update_fields=['is_read', 'read_at'])
    return redirect('intelligence:alerts')


@login_required
def alert_rules(request):
    _require(request.user, 'MANAGE_SOURCES')
    rules = [alert_service.get_rule(key) for key, _label in ALERT_RULES]
    deliveries = (AlertDelivery.objects.select_related('alert')
                  .order_by('-created_at', '-pk')[:20])
    return render(request, 'intelligence/alert_rules.html', {
        'rules': rules,
        'recent_alerts': Alert.objects.all()[:10],
        'recent_deliveries': deliveries,
    })


@login_required
def alert_rule_edit(request, pk):
    _require(request.user, 'MANAGE_SOURCES')
    rule = get_object_or_404(AlertRule, pk=pk)
    if request.method == 'POST':
        form = AlertRuleForm(request.POST, instance=rule)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.updated_by = request.user
            rule.save()
            _audit(request.user, 'ALERT_RULE_UPDATED', 'AlertRule', rule.pk,
                   {'key': rule.key, 'enabled': rule.enabled,
                    'channels': rule.channels})
            messages.success(request, 'Alert rule updated.')
            return redirect('intelligence:alert_rules')
    else:
        form = AlertRuleForm(instance=rule)
    return render(request, 'intelligence/alert_rule_form.html', {
        'form': form, 'rule': rule,
    })


# ---------------------------------------------------------------------------
# Briefings
# ---------------------------------------------------------------------------

@login_required
def briefings_list(request):
    _require(request.user, 'VIEW_INTELLIGENCE_REPORTS')
    page = Paginator(Briefing.objects.all(), 25).get_page(
        request.GET.get('page'))
    return render(request, 'intelligence/briefings.html', {
        'page_obj': page,
    })


@login_required
@require_POST
def briefing_generate(request):
    _require(request.user, 'VIEW_INTELLIGENCE_REPORTS')
    kind = request.POST.get('period', 'DAILY')
    if kind not in dict(Briefing.PERIOD):
        kind = 'DAILY'
    alert_service.evaluate_cycle_alerts()
    briefing = briefing_service.generate(
        kind=kind, actor=request.user,
        force=request.POST.get('force') == 'yes')
    messages.success(request, 'Briefing ready.')
    return redirect('intelligence:briefing_detail', pk=briefing.pk)


@login_required
def briefing_detail(request, pk):
    _require(request.user, 'VIEW_INTELLIGENCE_REPORTS')
    briefing = get_object_or_404(Briefing, pk=pk)
    data = briefing_service.briefing_data(briefing)
    show_security = security_service.is_holder(request.user)
    hero_stats = list(data['stats'])
    if show_security:
        security_facts = data['facts']['security']
        hero_stats.append({
            'icon': 'fa-shield-halved', 'label': 'Security units verified',
            'value': len(security_facts['headlines'])})
    return render(request, 'intelligence/briefing_detail.html', {
        'briefing': briefing,
        'data': data,
        'hero_stats': hero_stats,
        'show_security': show_security,
        'telegram_text': briefing_service.short_text(briefing),
        'telegram_deliveries': briefing.deliveries.filter(
            channel='TELEGRAM'),
    })


@login_required
@require_POST
def briefing_telegram(request, pk):
    _require(request.user, 'VIEW_INTELLIGENCE_REPORTS')
    briefing = get_object_or_404(Briefing, pk=pk)
    deliveries = briefing_service.send_telegram(
        briefing, actor=request.user)
    sent = [d for d in deliveries if d.status == 'SENT']
    skipped = [d for d in deliveries if d.status == 'SKIPPED']
    failed = [d for d in deliveries if d.status == 'FAILED']
    if sent:
        messages.success(
            request, f'Short briefing sent to {len(sent)} Telegram '
                     f'chat(s).')
    if failed:
        messages.error(
            request, f'Telegram delivery failed for {len(failed)} '
                     f'chat(s) — recorded on the briefing, not retried.')
    if skipped and not sent and not failed:
        messages.error(
            request, skipped[0].error or 'Telegram delivery skipped.')
    return redirect('intelligence:briefing_detail', pk=briefing.pk)


@login_required
@require_POST
def briefing_email(request, pk):
    _require(request.user, 'VIEW_INTELLIGENCE_REPORTS')
    briefing = get_object_or_404(Briefing, pk=pk)
    briefing_service.email_briefing(briefing, actor=request.user)
    if briefing.email_status.startswith('Sent'):
        messages.success(request, briefing.email_status)
    else:
        messages.error(request, briefing.email_status)
    return redirect('intelligence:briefing_detail', pk=pk)


# ---------------------------------------------------------------------------
# Phase 7 — field reporting + article↔LGA tagging
# ---------------------------------------------------------------------------

@login_required
def field_report_new(request):
    _require(request.user, 'SUBMIT_FIELD_REPORTS')
    form = FieldReportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        report = field_report_service.submit_field_report(
            request.user,
            headline=form.cleaned_data['headline'],
            text=form.cleaned_data['report_text'],
            lga=form.cleaned_data['lga'],
            category=form.cleaned_data['category'],
            occurred_at=form.cleaned_data['occurred_at'],
            photo=form.cleaned_data['photo'])
        messages.success(
            request,
            f'Field report filed. Reference #{report.pk} — the '
            f'verification desk now has it, and its progress will '
            f'appear under “My field reports”.')
        return redirect('intelligence:field_reports_mine')
    return render(request, 'intelligence/field_report_form.html', {
        'form': form})


@login_required
def field_reports_mine(request):
    _require(request.user, 'SUBMIT_FIELD_REPORTS')
    reports = (FieldReport.objects.filter(reporter=request.user)
               .select_related('lga', 'category', 'publication',
                               'publication__cluster'))
    rows = [{
        'report': report,
        'status_label': field_report_service.report_status_label(report),
        'desk_state': field_report_service.report_desk_state(report),
    } for report in reports]
    return render(request, 'intelligence/field_reports_mine.html', {
        'rows': rows})


@login_required
def article_locations(request):
    _require(request.user, 'MANAGE_SOURCES')
    from campaigns.models import Campaign
    query = (request.GET.get('q') or '').strip()
    articles = (Campaign.objects
                .prefetch_related('lga_links__lga')
                .order_by('-published_at', '-created_at', '-pk'))
    if query:
        articles = articles.filter(title__icontains=query)
    articles = articles[:25]
    rows = [{
        'article': article,
        'links': list(article.lga_links.all()),
        'form': ArticleLocationForm(),
    } for article in articles]
    return render(request, 'intelligence/article_locations.html', {
        'rows': rows, 'query': query,
        'total_links': ArticleLocation.objects.count()})


@login_required
@require_POST
def article_location_add(request, pk):
    _require(request.user, 'MANAGE_SOURCES')
    from campaigns.models import Campaign
    article = get_object_or_404(Campaign, pk=pk)
    form = ArticleLocationForm(request.POST)
    if form.is_valid():
        lga = form.cleaned_data['lga']
        _row, created = article_location_service.link(
            article, lga, 'MANUAL', actor=request.user)
        if created:
            _audit(request.user, 'ARTICLE_LGA_TAGGED', 'Campaign',
                   article.pk, {'lga_id': lga.pk})
            messages.success(
                request, f'“{article.title}” tagged to {lga.name} LGA.')
        else:
            messages.info(
                request, f'“{article.title}” is already linked to '
                         f'{lga.name} LGA.')
    else:
        messages.error(request, 'Choose an LGA to tag.')
    return redirect('intelligence:article_locations')


@login_required
@require_POST
def article_location_remove(request, pk):
    _require(request.user, 'MANAGE_SOURCES')
    link = get_object_or_404(ArticleLocation, pk=pk)
    title, lga_name = link.article.title, link.lga.name
    _audit(request.user, 'ARTICLE_LGA_UNTAGGED', 'Campaign',
           link.article_id, {'lga_id': link.lga_id, 'kind': link.kind})
    link.delete()
    messages.success(
        request, f'“{title}” is no longer linked to {lga_name} LGA.')
    return redirect('intelligence:article_locations')
