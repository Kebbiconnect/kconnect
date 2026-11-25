"""Staff API for the KPN Android 2.0.0 rebuild (screens 38, 131, 132,
136–139, 160–202).

Additive endpoints under /api/v1/ that expose the EXISTING web staff
surfaces — intelligence desk/security/projects, story-intelligence
promise & story desks, the editorial brain workspace and the ICT Admin
console — to the native app. Every write goes through the same service
layer / form the web view uses, so state machines, capability checks
and audit rows are identical on web and mobile. State names are the
model choice values in intelligence/models.py, unchanged.

Desk/security "units" are clusters or standalone items, exactly like
the web desk. In URLs a unit is addressed by a ref: ``cluster-<pk>``
or ``item-<pk>``; a bare numeric ref resolves to a cluster first, then
a standalone item (the desk list always returns the explicit ref).
"""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from leadership.capabilities import capabilities_for
from leadership.models import LGA

from .pagination import StandardPagination
from .permissions import IsVerifiedMember

AUTH = [permissions.IsAuthenticated, IsVerifiedMember]


# ─── Shared helpers ──────────────────────────────────────────────────────────

def cap(user, capability):
    """intelligence/views._can semantics: superuser or capability holder."""
    return bool(user is not None and user.is_authenticated
                and (user.is_superuser or capability in capabilities_for(user)))


def require_cap(user, capability):
    if not cap(user, capability):
        raise PermissionDenied('Your KPN role does not permit this action.')


def story_cap(user, capability):
    """story_intelligence web semantics: capability only, no bypass."""
    return capability in capabilities_for(user)


def require_story_cap(user, capability):
    if not story_cap(user, capability):
        raise PermissionDenied('You do not have permission to manage story records.')


def service_call(func, *args, **kwargs):
    """Run a web service function, translating its exceptions into the
    API error envelope (400 for workflow errors, 403 for capability)."""
    from intelligence.desk import DeskError
    from intelligence.projects import ProjectError
    from intelligence.promise_detection import CandidateError
    from intelligence.security import SecurityError
    from story_intelligence.services import PromiseError, RedactionError
    try:
        return func(*args, **kwargs)
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc) or 'Permission denied.')
    except (DeskError, ProjectError, SecurityError, CandidateError,
            PromiseError, RedactionError) as exc:
        raise ValidationError(str(exc))
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages)


def form_or_400(form):
    if not form.is_valid():
        raise ValidationError(form.errors)
    return form


def paginate(request, view, rows, serialize):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request, view=view)
    return paginator.get_paginated_response([serialize(row) for row in page])


def user_row(user):
    if user is None:
        return None
    return {'id': user.pk, 'username': user.get_username(),
            'name': user.get_full_name()}


# ─── A1. Report a suspicious opportunity listing (screen 38) ────────────────

class OpportunityReportThrottle(SimpleRateThrottle):
    """Same limit as the web route: django-ratelimit 5/hour per IP."""
    scope = 'opportunity_report'

    def get_rate(self):
        return '5/hour'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope, 'ident': self.get_ident(request)}


class OpportunityReportInput(serializers.Serializer):
    reason = serializers.CharField(max_length=5000)
    details = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    contact = serializers.CharField(required=False, allow_blank=True, max_length=200)
    reporter_contact = serializers.CharField(required=False, allow_blank=True, max_length=200)
    reporter_name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    name = serializers.CharField(required=False, allow_blank=True, max_length=120)


class OpportunityReportView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OpportunityReportThrottle]

    @extend_schema(auth=[], request=OpportunityReportInput,
                   responses={201: OpenApiTypes.OBJECT})
    def post(self, request, slug):
        from core.models import Opportunity, OpportunityReport
        opportunity = get_object_or_404(Opportunity, slug=slug)
        data = OpportunityReportInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        reason = values['reason'].strip()
        if values.get('details'):
            reason = f"{reason}\n\nDetails: {values['details'].strip()}"
        report = OpportunityReport.objects.create(
            opportunity=opportunity, reason=reason,
            reporter_name=values.get('reporter_name') or values.get('name') or '',
            reporter_contact=(values.get('contact')
                              or values.get('reporter_contact') or ''))
        return Response({
            'id': report.pk, 'opportunity': opportunity.slug,
            'status': report.status, 'created_at': report.created_at,
            'message': ('Thank you. Your report has been received and will '
                        'be reviewed by the KPN team.'),
        }, status=status.HTTP_201_CREATED)


# ─── A2. Field reports (screens 137–138) ─────────────────────────────────────

def field_report_row(report):
    from intelligence import field_reports as field_service
    return {
        'id': report.pk, 'headline': report.headline,
        'report_text': report.report_text,
        'reporter': user_row(report.reporter),
        'lga': report.lga_id,
        'lga_name': report.lga.name if report.lga_id else None,
        'category': report.category_id,
        'category_label': report.category.label if report.category_id else None,
        'occurred_at': report.occurred_at,
        'publication': report.publication_id,
        'desk_state': field_service.report_desk_state(report),
        'status_label': field_service.report_status_label(report),
        'created_at': report.created_at,
    }


class FieldReportListCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from intelligence.models import FieldReport
        if cap(request.user, 'REVIEW_INTELLIGENCE'):
            rows = (FieldReport.objects
                    .select_related('reporter', 'lga', 'category', 'publication',
                                    'publication__cluster')
                    .order_by('-created_at', '-pk'))
            scope = 'queue'
        elif cap(request.user, 'SUBMIT_FIELD_REPORTS'):
            rows = (FieldReport.objects.filter(reporter=request.user)
                    .select_related('lga', 'category', 'publication',
                                    'publication__cluster')
                    .order_by('-created_at', '-pk'))
            scope = 'mine'
        else:
            raise PermissionDenied('Your KPN role does not permit this action.')
        response = paginate(request, self, list(rows), field_report_row)
        response.data['scope'] = scope
        return response

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_cap(request.user, 'SUBMIT_FIELD_REPORTS')
        from intelligence import field_reports as field_service
        from intelligence.forms import FieldReportForm
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        occurred = data.get('occurred_at')
        if isinstance(occurred, str):
            parsed = parse_datetime(occurred)
            if parsed is not None:
                data['occurred_at'] = parsed
        form = form_or_400(FieldReportForm(data, request.FILES or None))
        report = field_service.submit_field_report(
            request.user,
            headline=form.cleaned_data['headline'],
            text=form.cleaned_data['report_text'],
            lga=form.cleaned_data['lga'],
            category=form.cleaned_data['category'],
            occurred_at=form.cleaned_data['occurred_at'],
            photo=form.cleaned_data['photo'])
        return Response(field_report_row(report), status=status.HTTP_201_CREATED)


# ─── A3. Network rankings (screen 139) ───────────────────────────────────────

class NetworkRankingsView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        # Mirrors core.views.network_rankings exactly.
        from core.models import CommunityReport
        from leadership.models import Ward
        from staff.models import User
        top_lgas = (LGA.objects
                    .annotate(active_members=Count(
                        'members', filter=Q(members__status='VERIFIED')))
                    .filter(active_members__gt=0)
                    .order_by('-active_members')[:5])
        top_wards = (Ward.objects
                     .annotate(active_members=Count(
                         'members', filter=Q(members__status='VERIFIED')))
                     .filter(active_members__gt=0)
                     .order_by('-active_members')[:5])
        trusted = User.objects.filter(status='VERIFIED', is_trusted_reporter=True)
        data = {
            'top_lgas': [{'id': lga.pk, 'name': lga.name,
                          'active_members': lga.active_members}
                         for lga in top_lgas],
            'top_wards': [{'id': ward.pk, 'name': ward.name,
                           'lga': ward.lga_id, 'lga_name': ward.lga.name,
                           'active_members': ward.active_members}
                          for ward in top_wards],
            'trusted_reporters': [user_row(u) for u in trusted],
            'internal_data': None,
        }
        user = request.user
        if user.is_authenticated and user.is_leader():
            inactive = (LGA.objects
                        .annotate(active_members=Count(
                            'members', filter=Q(members__status='VERIFIED')))
                        .filter(active_members=0).order_by('name'))
            data['internal_data'] = {
                'inactive_lgas': [{'id': lga.pk, 'name': lga.name}
                                  for lga in inactive],
                'pending_reports': CommunityReport.objects.filter(
                    status='PENDING').count(),
            }
        return Response(data)


# ─── A4. Events calendar + all minutes (screens 131–132) ────────────────────

class EventCalendarView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_EVENTS')
        from events.models import Event
        rows = Event.objects.all().order_by('start_date', 'pk')
        date_from = request.query_params.get('from', '')
        date_to = request.query_params.get('to', '')
        if date_from:
            parsed = parse_datetime(date_from)
            if parsed is not None:
                rows = rows.filter(start_date__gte=parsed)
        if date_to:
            parsed = parse_datetime(date_to)
            if parsed is not None:
                rows = rows.filter(start_date__lte=parsed)
        # The web Event model carries no LGA field; lga is null rather
        # than guessed from the location text.
        return paginate(request, self, rows, lambda event: {
            'id': event.pk, 'title': event.title,
            'starts_at': event.start_date, 'ends_at': event.end_date,
            'start_date': event.start_date, 'end_date': event.end_date,
            'location': event.location, 'lga': None,
        })


class AllMinutesView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_EVENTS')
        from events.models import MeetingMinutes
        from .serializers import MeetingMinutesSerializer
        rows = (MeetingMinutes.objects.select_related('event')
                .order_by('-recorded_at', '-pk'))

        def row(minutes):
            data = MeetingMinutesSerializer(minutes).data
            data['event_title'] = minutes.event.title
            return data
        return paginate(request, self, rows, row)


# ─── A5. Advocacy decision (screen 136) ──────────────────────────────────────
# FLAG: the web has NO decision workflow for advocacy campaigns (public
# list/detail + MANAGE_HUBS CRUD via management/<kind>/ only). This is
# the minimal decision endpoint the screen needs: a capability-gated
# status transition recorded as a dated AdvocacyActivity audit entry.

ADVOCACY_DECISIONS = {
    'APPROVE': ('ACTIVE', True),
    'PAUSE': ('PAUSED', True),
    'COMPLETE': ('COMPLETED', True),
    'CLOSE': ('CLOSED', False),
    'REJECT': ('CLOSED', False),
}


class AdvocacyDecisionView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_HUBS')
        from core.models import AdvocacyActivity, AdvocacyCampaign
        campaign = get_object_or_404(AdvocacyCampaign, pk=pk)
        action = str(request.data.get('action', '')).upper()
        if action not in ADVOCACY_DECISIONS:
            raise ValidationError(
                {'action': f'Choose one of: {", ".join(ADVOCACY_DECISIONS)}.'})
        new_status, is_active = ADVOCACY_DECISIONS[action]
        old_status = campaign.status
        campaign.status = new_status
        campaign.is_active = is_active
        campaign.save(update_fields=['status', 'is_active', 'updated_at'])
        note = str(request.data.get('note', '') or '').strip()
        entry = (f'Staff decision via KPN app: {action} — status changed '
                 f'from {old_status} to {new_status} by '
                 f'{request.user.get_username()}.')
        if note:
            entry = f'{entry} Note: {note}'
        AdvocacyActivity.objects.create(
            campaign=campaign, date=timezone.localdate(), entry=entry[:2000])
        from .serializers import AdvocacyCampaignSerializer
        data = AdvocacyCampaignSerializer(campaign).data
        data['status'] = campaign.status
        data['decision'] = {'action': action, 'from_status': old_status,
                            'to_status': new_status}
        return Response(data)


# ─── B. Intelligence: shared serializers/helpers ─────────────────────────────

def source_row(source):
    from intelligence.models import SourceHealth
    try:
        health = source.intelligence_health
        health_state = health.state()
        health_data = {
            'last_cycle_at': health.last_cycle_at,
            'last_success_at': health.last_success_at,
            'last_error': health.last_error,
            'consecutive_failures': health.consecutive_failures,
        }
    except SourceHealth.DoesNotExist:
        health_state = 'DISABLED' if not source.enabled else 'NEVER_RUN'
        health_data = None
    return {
        'id': source.pk, 'name': source.name, 'kind': source.kind,
        'kind_label': source.get_kind_display(), 'url': source.url,
        'feed': source.feed, 'connector_kind': source.connector_kind,
        'connector_kind_label': source.get_connector_kind_display(),
        'poll_interval_minutes': source.poll_interval_minutes,
        'keywords': source.keywords, 'allowed_hosts': source.allowed_hosts,
        'max_items': source.max_items, 'enabled': source.enabled,
        'home_lga': source.home_lga_id,
        'home_lga_name': source.home_lga.name if source.home_lga_id else None,
        'last_success_at': source.last_success_at,
        'last_error': source.last_error,
        'consecutive_failures': source.consecutive_failures,
        'health_state': health_state, 'health': health_data,
        'created_at': source.created_at,
    }


def raw_item_row(item):
    categories = [{
        'id': link.category_id, 'slug': link.category.slug,
        'label': link.category.label, 'is_primary': link.is_primary,
        'is_sensitive': link.category.is_sensitive,
    } for link in item.category_links.all()]
    locations = [{
        'id': loc.pk, 'lga': loc.lga_id,
        'lga_name': loc.lga.name if loc.lga_id else None,
        'ward': loc.ward_id, 'district': loc.district_id,
        'community': loc.community_id, 'geo_entity': loc.geo_entity_id,
        'match_kind': loc.match_kind, 'matched_text': loc.matched_text,
    } for loc in item.locations.all()]
    return {
        'id': item.pk, 'title': item.title, 'summary': item.summary,
        'text': item.text,
        'source': {'id': item.source_id, 'name': item.source.name},
        'original_url': item.original_url, 'canonical_url': item.canonical_url,
        'published_at': item.published_at, 'discovered_at': item.discovered_at,
        'event_time': item.event_time,
        'fetch_status': item.fetch_status,
        'fetch_status_label': item.get_fetch_status_display(),
        'relevance': item.relevance,
        'relevance_label': (item.get_relevance_display() if item.relevance else None),
        'relevance_reasons': item.relevance_reasons,
        'relevance_manual': item.relevance_manual,
        'processed_at': item.processed_at,
        'desk_state': item.desk_state,
        'desk_state_label': item.get_desk_state_display(),
        'cluster': item.cluster_id, 'duplicate_of': item.duplicate_of_id,
        'assigned_to': user_row(item.assigned_to) if item.assigned_to_id else None,
        'article': item.article_id,
        'categories': categories, 'locations': locations,
    }


def unit_ref(kind, pk):
    return f'{kind}-{pk}'


def resolve_unit(ref):
    """Resolve a desk/security unit ref to (kind, unit) or raise 404."""
    from intelligence.models import EventCluster, RawPublication
    kind = None
    pk = None
    if isinstance(ref, str) and ref.startswith('cluster-'):
        kind, pk = 'cluster', ref[len('cluster-'):]
    elif isinstance(ref, str) and ref.startswith('item-'):
        kind, pk = 'item', ref[len('item-'):]
    elif str(ref).isdigit():
        pk = ref
    if pk is None or not str(pk).isdigit():
        raise NotFound('Unknown desk unit.')
    pk = int(pk)
    if kind == 'cluster':
        return 'cluster', get_object_or_404(EventCluster, pk=pk, state='OPEN')
    if kind == 'item':
        return 'item', get_object_or_404(
            RawPublication, pk=pk, cluster__isnull=True)
    cluster = EventCluster.objects.filter(pk=pk, state='OPEN').first()
    if cluster is not None:
        return 'cluster', cluster
    return 'item', get_object_or_404(RawPublication, pk=pk, cluster__isnull=True)


def check_unit_visible(user, unit):
    from intelligence import security as security_service
    if (security_service.unit_is_restricted(unit)
            and not security_service.is_holder(user)):
        raise NotFound('Desk unit not found.')


def decision_row(decision):
    return {
        'id': decision.pk, 'action': decision.action,
        'action_label': decision.get_action_display(),
        'from_state': decision.from_state, 'from_label': decision.from_label,
        'to_state': decision.to_state, 'to_label': decision.to_label,
        'note': decision.note,
        'actor': user_row(decision.actor) if decision.actor_id else None,
        'created_at': decision.created_at,
    }


def unit_row(kind, unit, members=None):
    from intelligence import desk as desk_service
    from intelligence.models import RawPublication  # noqa: F401  (labels)
    if members is None:
        members = desk_service.unit_members(unit)
    category = desk_service.unit_category(unit)
    lga = desk_service.unit_lga(unit)
    relevance = None
    if members:
        rank = {'CONFIRMED': 0, 'STRONG_POSSIBLE': 1, 'UNCERTAIN': 2,
                'NOT_RELEVANT': 3, None: 4}
        relevance = min((m.relevance for m in members),
                        key=lambda value: rank.get(value, 4))
    return {
        'ref': unit_ref(kind, unit.pk), 'kind': kind, 'id': unit.pk,
        'title': desk_service.unit_title(unit),
        'desk_state': unit.desk_state,
        'desk_state_label': unit.get_desk_state_display(),
        'category': ({'id': category.pk, 'slug': category.slug,
                      'label': category.label,
                      'is_sensitive': category.is_sensitive}
                     if category else None),
        'lga': ({'id': lga.pk, 'name': lga.name} if lga else None),
        'relevance': relevance,
        'relevance_label': (dict(RawPublication.RELEVANCE).get(relevance)
                            if relevance else None),
        'member_count': len(members),
        'member_ids': [m.pk for m in members],
        'assigned_to': user_row(unit.assigned_to) if unit.assigned_to_id else None,
        'article': unit.article_id,
        'is_sensitive': desk_service.unit_is_sensitive(unit),
        'created_at': getattr(unit, 'created_at',
                              getattr(unit, 'discovered_at', None)),
        'updated_at': getattr(unit, 'updated_at', None),
    }


# ─── B. Intelligence overview / items (screens 160–161) ─────────────────────

class IntelligenceOverviewView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from collections import Counter
        from editorial.models import Source
        from intelligence import cycle as cycle_service
        from intelligence import security as security_service
        from intelligence import tracking as tracking_service
        from intelligence.models import (
            DESK_STATES, AlertDelivery, ArticleLocation, Briefing,
            CollectionControl, CollectionRun, Community, District,
            EventCluster, FieldReport, GeoAlias, IntelligenceCategory,
            Project, PromiseCandidate, RawPublication, SecurityIncident,
            SourceHealth,
        )
        from leadership.models import LGA as LgaModel
        item_qs = security_service.visible_items(request.user, RawPublication.objects.all())
        cluster_qs = security_service.visible_clusters(request.user, EventCluster.objects.all())
        sources = Source.objects.all().prefetch_related('intelligence_health')
        failing = 0
        for source in sources:
            try:
                if source.intelligence_health.state() == 'FAILING':
                    failing += 1
            except SourceHealth.DoesNotExist:
                pass
        map_rows = tracking_service.lga_tracking_rows()
        health = cycle_service.cycle_health()
        last_run = health.get('last_run')
        if last_run is not None:
            # cycle_health() returns the CollectionRun instance; the API
            # payload must carry plain data or the renderer fails (500)
            # as soon as any collection run exists.
            health = {**health, 'last_run': {
                'id': last_run.pk, 'trigger': last_run.trigger,
                'status': last_run.status,
                'started_at': last_run.started_at,
                'finished_at': last_run.finished_at,
            }}
        data = {
            'cycle_health': health,
            'collection_enabled': CollectionControl.objects.get_or_create(pk=1)[0].enabled,
            'runs_total': CollectionRun.objects.count(),
            'sources_total': sources.count(),
            'sources_enabled': sources.filter(enabled=True).count(),
            'sources_failing': failing,
            'lga_count': LgaModel.objects.count(),
            'district_count': District.objects.count(),
            'community_count': Community.objects.count(),
            'pending_aliases': GeoAlias.objects.filter(status='PENDING').count(),
            'category_count': IntelligenceCategory.objects.count(),
            'raw_items_total': item_qs.count(),
            'relevant_items': item_qs.filter(
                relevance__in=['CONFIRMED', 'STRONG_POSSIBLE']).count(),
            'unprocessed_items': item_qs.filter(relevance__isnull=True).count(),
            'cluster_total': cluster_qs.filter(state='OPEN').count(),
            'my_unread_alerts': AlertDelivery.objects.filter(
                channel='DASHBOARD', recipient=request.user.get_username(),
                is_read=False).count(),
            'latest_briefing': (Briefing.objects.first().pk
                                if Briefing.objects.exists() else None),
            'project_total': Project.objects.count(),
            'project_reported_abandoned': Project.objects.filter(
                status='REPORTED_ABANDONED').count(),
            'project_verified_abandoned': Project.objects.filter(
                status='VERIFIED_ABANDONED').count(),
            'pending_candidates': PromiseCandidate.objects.filter(
                status='PENDING').count(),
            'my_field_reports': FieldReport.objects.filter(
                reporter=request.user).count(),
            'field_reports_total': FieldReport.objects.count(),
            'article_location_total': ArticleLocation.objects.count(),
            'map_totals': tracking_service.totals_for(map_rows),
            'capabilities': {
                'can_manage_sources': cap(request.user, 'MANAGE_SOURCES'),
                'can_review_desk': cap(request.user, 'REVIEW_INTELLIGENCE'),
                'can_security': cap(request.user, 'VIEW_SECURITY_DESK'),
                'can_view_reports': cap(request.user, 'VIEW_INTELLIGENCE_REPORTS'),
                'can_manage_projects': cap(request.user, 'MANAGE_PROJECTS'),
                'can_manage_promises': cap(request.user, 'MANAGE_PROMISES'),
                'can_submit_field_reports': cap(request.user, 'SUBMIT_FIELD_REPORTS'),
            },
        }
        if data['capabilities']['can_security']:
            data['restricted_units'] = (
                security_service.restricted_clusters().count()
                + security_service.restricted_items().count())
            data['open_incidents'] = SecurityIncident.objects.filter(
                status='OPEN').count()
        if data['capabilities']['can_review_desk']:
            counter = Counter(cluster_qs.filter(state='OPEN')
                              .values_list('desk_state', flat=True))
            counter.update(item_qs.filter(cluster__isnull=True)
                           .values_list('desk_state', flat=True))
            data['desk_counts'] = {
                state: counter.get(state, 0) for state, _ in DESK_STATES}
            data['desk_waiting'] = sum(
                counter.get(s, 0) for s in (
                    'DISCOVERED', 'UNDER_REVIEW',
                    'VERIFICATION_IN_PROGRESS', 'NEEDS_INFO'))
        return Response(data)


class IntelligenceItemsView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence import security as security_service
        from intelligence.models import RawPublication
        rows = security_service.visible_items(
            request.user,
            RawPublication.objects.select_related('source', 'duplicate_of', 'cluster', 'assigned_to')
            .prefetch_related('locations__lga', 'locations__ward',
                              'locations__district', 'locations__community',
                              'locations__geo_entity', 'category_links__category'))
        params = request.query_params
        if params.get('source', '').isdigit():
            rows = rows.filter(source_id=int(params['source']))
        if params.get('status', '') in dict(RawPublication.FETCH_STATUS):
            rows = rows.filter(fetch_status=params['status'])
        relevance = params.get('relevance', '')
        if relevance == 'UNPROCESSED':
            rows = rows.filter(relevance__isnull=True)
        elif relevance in dict(RawPublication.RELEVANCE):
            rows = rows.filter(relevance=relevance)
        from intelligence.models import DESK_STATES
        if params.get('state', '') in dict(DESK_STATES):
            rows = rows.filter(desk_state=params['state'])
        category = params.get('category', '')
        if category.isdigit():
            rows = rows.filter(category_links__category_id=int(category)).distinct()
        elif category:
            rows = rows.filter(category_links__category__slug=category).distinct()
        if params.get('lga', '').isdigit():
            rows = rows.filter(locations__lga_id=int(params['lga'])).distinct()
        return paginate(request, self, rows, raw_item_row)


# ─── B. Verification desk (screens 162–165) ──────────────────────────────────

class DeskListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'REVIEW_INTELLIGENCE')
        from intelligence.views import _desk_units
        units = _desk_units(request.user)
        params = request.query_params
        total = len(units)
        if params.get('state'):
            units = [r for r in units if r['state'] == params['state']]
        if params.get('relevance'):
            units = [r for r in units if r['relevance'] == params['relevance']]
        if params.get('category'):
            units = [r for r in units if r['category']
                     and (str(r['category'].pk) == params['category']
                          or r['category'].slug == params['category'])]
        if params.get('lga'):
            units = [r for r in units if r['lga']
                     and str(r['lga'].pk) == params['lga']]

        def row(r):
            return {
                'ref': unit_ref(r['kind'], r['obj'].pk), 'kind': r['kind'],
                'id': r['obj'].pk, 'title': r['title'],
                'desk_state': r['state'], 'desk_state_label': r['state_label'],
                'category': ({'id': r['category'].pk, 'slug': r['category'].slug,
                              'label': r['category'].label,
                              'is_sensitive': r['category'].is_sensitive}
                             if r['category'] else None),
                'lga': ({'id': r['lga'].pk, 'name': r['lga'].name}
                        if r['lga'] else None),
                'relevance': r['relevance'],
                'first_seen': r['first_seen'],
                'member_count': r['member_count'],
                'assigned_to': user_row(r['assigned_to']) if r['assigned_to'] else None,
            }
        response = paginate(request, self, units, row)
        response.data['total_units'] = total
        return response


class DeskDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, ref):
        require_cap(request.user, 'REVIEW_INTELLIGENCE')
        kind, unit = resolve_unit(ref)
        check_unit_visible(request.user, unit)
        from intelligence import desk as desk_service
        from intelligence.views import _desk_detail_context
        context = _desk_detail_context(request, unit, kind)
        data = unit_row(kind, unit, members=list(context['members']))
        data.update({
            'members': [raw_item_row(m) for m in context['members']],
            'decisions': [decision_row(d) for d in context['decisions']],
            'available_actions': [
                {'action': action,
                 'label': desk_service.ACTION_BUTTON_LABELS[action]}
                for action in desk_service.available_actions(unit, request.user)],
            'credibility': [{
                'source': {'id': c['source'].pk, 'name': c['source'].name},
                'health_state': c['health_state'],
                'items_collected': c['items_collected'],
                'units_verified': c['units_verified'],
                'units_rejected': c['units_rejected'],
            } for c in context['credibility']],
            'can_assign': context['can_assign'],
            'can_merge_split': context['can_merge_split'],
            'can_convert': context['can_convert'],
            'can_create_project': context['can_create_project'],
            'unit_projects': [p.pk for p in context['unit_projects']],
            'working_text': unit.working_text,
            'other_clusters': [
                {'ref': unit_ref('cluster', c.pk), 'id': c.pk, 'title': c.title}
                for c in context['other_clusters']],
        })
        return Response(data)


class DeskTransitionView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, ref):
        require_cap(request.user, 'REVIEW_INTELLIGENCE')
        kind, unit = resolve_unit(ref)
        check_unit_visible(request.user, unit)
        from intelligence import desk as desk_service
        decision = service_call(
            desk_service.apply_transition, unit, request.user,
            str(request.data.get('action', '')),
            note=str(request.data.get('note', '') or ''))
        unit.refresh_from_db()
        data = unit_row(kind, unit)
        data['decision'] = decision_row(decision)
        return Response(data)


class DeskConvertView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, ref):
        require_cap(request.user, 'APPROVE_INTELLIGENCE')
        kind, unit = resolve_unit(ref)
        check_unit_visible(request.user, unit)
        confirm = request.data.get('confirm')
        if confirm not in (True, 'yes', 'true', 'YES', 'Yes'):
            raise ValidationError(
                {'confirm': 'Nothing was created. Conversion needs the '
                            'confirmation step to be completed.'})
        from intelligence import desk as desk_service
        article = service_call(desk_service.convert_to_draft, unit, request.user)
        return Response({
            'article': {'id': article.pk, 'slug': article.slug,
                        'title': article.title, 'status': article.status,
                        'story_id': article.story_id},
            'unit': unit_row(kind, unit),
            'message': ('Newsroom draft created. It is not published — it '
                        'goes through the normal newsroom review and '
                        'publish flow.'),
        }, status=status.HTTP_201_CREATED)


# ─── B. Clusters (screens 166–167) ───────────────────────────────────────────

def cluster_row(cluster):
    earliest, latest = cluster.member_times()
    return {
        'id': cluster.pk, 'ref': unit_ref('cluster', cluster.pk),
        'title': cluster.title, 'state': cluster.state,
        'state_label': cluster.get_state_display(),
        'created_from': cluster.created_from,
        'desk_state': cluster.desk_state,
        'desk_state_label': cluster.get_desk_state_display(),
        'category': ({'id': cluster.category.pk, 'slug': cluster.category.slug,
                      'label': cluster.category.label,
                      'is_sensitive': cluster.category.is_sensitive}
                     if cluster.category_id else None),
        'primary_lga': ({'id': cluster.primary_lga.pk,
                         'name': cluster.primary_lga.name}
                        if cluster.primary_lga_id else None),
        'member_count': cluster.publications.count(),
        'earliest': earliest, 'latest': latest,
        'assigned_to': user_row(cluster.assigned_to) if cluster.assigned_to_id else None,
        'article': cluster.article_id, 'merged_into': cluster.merged_into_id,
        'created_at': cluster.created_at, 'updated_at': cluster.updated_at,
    }


class ClusterListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence import security as security_service
        from intelligence.models import EventCluster
        rows = security_service.visible_clusters(
            request.user,
            EventCluster.objects.filter(state='OPEN')
            .select_related('category', 'primary_lga', 'assigned_to')
            .order_by('-updated_at', '-pk'))
        if request.query_params.get('category', '').isdigit():
            rows = rows.filter(category_id=int(request.query_params['category']))
        if request.query_params.get('lga', '').isdigit():
            rows = rows.filter(primary_lga_id=int(request.query_params['lga']))
        return paginate(request, self, rows, cluster_row)


class ClusterDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence import security as security_service
        from intelligence.models import EventCluster
        cluster = get_object_or_404(
            security_service.visible_clusters(
                request.user,
                EventCluster.objects.select_related(
                    'category', 'primary_lga', 'assigned_to')),
            pk=pk)
        members = (cluster.publications.select_related('source')
                   .prefetch_related('locations__lga', 'category_links__category')
                   .order_by('published_at', 'discovered_at', 'pk'))
        data = cluster_row(cluster)
        data['members'] = [raw_item_row(m) for m in members]
        data['decisions'] = [decision_row(d) for d in
                             cluster.review_decisions.select_related('actor').all()]
        return Response(data)


class ClusterMergeView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'REVIEW_INTELLIGENCE')
        from intelligence import desk as desk_service
        from intelligence.models import EventCluster
        target = get_object_or_404(EventCluster, pk=pk, state='OPEN')
        check_unit_visible(request.user, target)
        other = (request.data.get('other_cluster')
                 or request.data.get('source_cluster'))
        source_cluster = get_object_or_404(EventCluster, pk=other, state='OPEN')
        check_unit_visible(request.user, source_cluster)
        decision = service_call(
            desk_service.merge_clusters, request.user, target, source_cluster,
            note=str(request.data.get('note', '') or ''))
        target.refresh_from_db()
        data = cluster_row(target)
        data['decision'] = decision_row(decision)
        return Response(data)


class ClusterSplitView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'REVIEW_INTELLIGENCE')
        from intelligence import desk as desk_service
        from intelligence.models import EventCluster
        cluster = get_object_or_404(EventCluster, pk=pk, state='OPEN')
        check_unit_visible(request.user, cluster)
        items = request.data.get('items') or []
        new_cluster = service_call(
            desk_service.split_cluster, request.user, cluster, list(items),
            note=str(request.data.get('note', '') or ''))
        cluster.refresh_from_db()
        data = cluster_row(cluster)
        data['new_cluster'] = cluster_row(new_cluster) if new_cluster else None
        return Response(data)


# ─── B. Sources / runs / aliases / LGAs / article locations ─────────────────

class IntelligenceSourceListCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from editorial.models import Source
        rows = Source.objects.all().prefetch_related('intelligence_health')
        return Response({
            'results': [source_row(s) for s in rows],
            'can_manage_sources': cap(request.user, 'MANAGE_SOURCES'),
        })

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_cap(request.user, 'MANAGE_SOURCES')
        from editorial.models import Source
        from intelligence.forms import IntelligenceSourceForm
        from intelligence.models import IntelligenceAudit, SourceHealth
        source_id = request.data.get('id')
        instance = get_object_or_404(Source, pk=source_id) if source_id else Source()
        form = form_or_400(IntelligenceSourceForm(request.data, instance=instance))
        source = form.save()
        SourceHealth.objects.get_or_create(source=source)
        IntelligenceAudit.objects.create(
            actor=request.user, action='SOURCE_SAVED', target_type='Source',
            target_id=source.pk, detail={'source_id': source.pk})
        return Response(source_row(source),
                        status=status.HTTP_201_CREATED if not source_id
                        else status.HTTP_200_OK)


def collection_run_row(run):
    return {
        'id': run.pk, 'trigger': run.trigger,
        'trigger_label': run.get_trigger_display(),
        'status': run.status, 'status_label': run.get_status_display(),
        'started_at': run.started_at, 'finished_at': run.finished_at,
        'sources_due': run.sources_due, 'sources_ok': run.sources_ok,
        'sources_failed': run.sources_failed, 'items_new': run.items_new,
        'error': run.error,
    }


class CollectionRunListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence.models import CollectionRun
        return paginate(request, self, CollectionRun.objects.all(),
                        collection_run_row)


class CollectionRunTriggerView(APIView):
    """Manual collection run (screen 170 — the reference screen shows
    a "Run now" affordance). Runs one cycle through the shared
    intelligence cycle service with trigger MANUAL, under the existing
    lease machinery in intelligence/cycle.py, so a normal CollectionRun
    record is produced (COMPLETED, or SKIPPED_LEASED / PAUSED exactly
    as a scheduled invocation would record). Gated on MANAGE_SOURCES,
    the same capability that manages sources and collection control.
    """
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence import cycle as cycle_service
        run = cycle_service.run_cycle(trigger='MANUAL')
        return Response(collection_run_row(run), status=status.HTTP_201_CREATED)


def alias_row(alias):
    target = alias.target
    return {
        'id': alias.pk, 'alias': alias.alias,
        'target_kind': alias.target_kind,
        'target': ({'id': target.pk, 'name': str(target)}
                   if target is not None else None),
        'lga': alias.lga_id, 'district': alias.district_id,
        'ward': alias.ward_id, 'community': alias.community_id,
        'geo_entity': alias.geo_entity_id,
        'status': alias.status,
        'status_label': alias.get_status_display(),
        'created_by': user_row(alias.created_by) if alias.created_by_id else None,
        'reviewed_by': user_row(alias.reviewed_by) if alias.reviewed_by_id else None,
        'reviewed_at': alias.reviewed_at,
        'created_at': alias.created_at,
    }


class AliasListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence.models import GeoAlias
        rows = GeoAlias.objects.select_related(
            'lga', 'district', 'ward', 'community', 'geo_entity')
        wanted = request.query_params.get('status', '')
        if wanted in dict(GeoAlias.STATUS):
            rows = rows.filter(status=wanted)
        return paginate(request, self, rows, alias_row)

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        # Round 2 (screen 171): alias create, mirroring the web
        # aliases page (intelligence.views.aliases) — the same
        # GeoAliasForm fields, created_by recorded, the model's
        # default PENDING status under the existing review workflow,
        # the ALIAS_CREATED audit, gated on MANAGE_SOURCES exactly
        # like alias review.
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence.forms import GeoAliasForm
        from intelligence.models import IntelligenceAudit
        form = form_or_400(GeoAliasForm(request.data))
        alias = form.save(commit=False)
        alias.created_by = request.user
        alias.save()
        IntelligenceAudit.objects.create(
            actor=request.user, action='ALIAS_CREATED',
            target_type='GeoAlias', target_id=alias.pk,
            detail={'status': alias.status})
        return Response(alias_row(alias), status=status.HTTP_201_CREATED)


class AliasReviewView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence.models import GeoAlias, IntelligenceAudit
        decision = str(request.data.get('decision', '')).upper()
        if decision not in ('APPROVED', 'REJECTED'):
            raise ValidationError({'decision': 'Decision must be APPROVED or REJECTED.'})
        alias = get_object_or_404(GeoAlias, pk=pk)
        alias.status = decision
        alias.reviewed_by = request.user
        alias.reviewed_at = timezone.now()
        alias.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
        IntelligenceAudit.objects.create(
            actor=request.user,
            action='ALIAS_APPROVED' if decision == 'APPROVED' else 'ALIAS_REJECTED',
            target_type='GeoAlias', target_id=alias.pk,
            detail={'status': decision})
        return Response({'id': alias.pk, 'status': alias.status,
                         'reviewed_at': alias.reviewed_at})


class IntelligenceLgaListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence import article_locations
        rows = (LGA.objects.select_related('zone')
                .annotate(ward_count=Count('wards', distinct=True),
                          district_count=Count('districts', distinct=True),
                          community_count=Count('communities', distinct=True))
                .order_by('name'))
        return Response({'results': [{
            'id': lga.pk, 'name': lga.name, 'slug': article_locations.lga_slug(lga),
            'zone': lga.zone_id, 'zone_name': lga.zone.name,
            'ward_count': lga.ward_count,
            'district_count': lga.district_count,
            'community_count': lga.community_count,
        } for lga in rows]})


class IntelligenceLgaDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, slug):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence import article_locations
        from intelligence.models import GeoAlias
        lga = article_locations.lga_for_slug(slug)
        if lga is None:
            raise NotFound('Unknown LGA.')
        return Response({
            'id': lga.pk, 'name': lga.name, 'slug': slug,
            'zone': lga.zone_id, 'zone_name': lga.zone.name,
            'districts': [{'id': d.pk, 'name': d.name} for d in lga.districts.all()],
            'wards': [{'id': w.pk, 'name': w.name} for w in lga.wards.all()],
            'communities': [{
                'id': c.pk, 'name': c.name, 'ward': c.ward_id,
                'district': c.district_id,
            } for c in lga.communities.select_related('ward', 'district')],
            'entities': [{
                'id': e.pk, 'name': e.name, 'kind': e.kind,
                'kind_label': e.get_kind_display(),
            } for e in lga.geo_entities.all()],
            'aliases': [{
                'id': a.pk, 'alias': a.alias, 'status': a.status,
                'target_kind': a.target_kind,
            } for a in GeoAlias.objects.filter(lga=lga)],
            'counts': {
                'districts': lga.districts.count(),
                'communities': lga.communities.count(),
                'wards': lga.wards.count(),
            },
            'can_manage_sources': cap(request.user, 'MANAGE_SOURCES'),
        })


class ArticleLocationListCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'MANAGE_SOURCES')
        from campaigns.models import Campaign
        from intelligence.models import ArticleLocation
        query = (request.query_params.get('q') or '').strip()
        articles = (Campaign.objects.prefetch_related('lga_links__lga')
                    .order_by('-published_at', '-created_at', '-pk'))
        if query:
            articles = articles.filter(title__icontains=query)
        articles = list(articles[:25])
        return Response({
            'results': [{
                'article': {'id': a.pk, 'title': a.title, 'slug': a.slug,
                            'status': a.status},
                'links': [{'id': link.pk, 'lga': link.lga_id,
                           'lga_name': link.lga.name, 'kind': link.kind,
                           'kind_label': link.get_kind_display()}
                          for link in a.lga_links.all()],
            } for a in articles],
            'total_links': ArticleLocation.objects.count(),
        })

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_cap(request.user, 'MANAGE_SOURCES')
        from campaigns.models import Campaign
        from intelligence import article_locations as location_service
        from intelligence.forms import ArticleLocationForm
        from intelligence.models import IntelligenceAudit
        article = get_object_or_404(Campaign, pk=request.data.get('article_id'))
        form = form_or_400(ArticleLocationForm(request.data))
        lga = form.cleaned_data['lga']
        row, created = location_service.link(article, lga, 'MANUAL', actor=request.user)
        if created:
            IntelligenceAudit.objects.create(
                actor=request.user, action='ARTICLE_LGA_TAGGED',
                target_type='Campaign', target_id=article.pk,
                detail={'lga_id': lga.pk})
        return Response({
            'id': row.pk, 'article': article.pk, 'lga': lga.pk,
            'lga_name': lga.name, 'kind': row.kind, 'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ─── B. Briefings + alert rules + my alerts (screens 175–179) ───────────────

def briefing_row(briefing):
    return {
        'id': briefing.pk, 'period_kind': briefing.period_kind,
        'period_kind_label': briefing.get_period_kind_display(),
        'period_start': briefing.period_start, 'period_end': briefing.period_end,
        'title': briefing.title, 'body': briefing.body,
        'email_status': briefing.email_status, 'emailed_at': briefing.emailed_at,
        'generated_by': user_row(briefing.generated_by) if briefing.generated_by_id else None,
        'created_at': briefing.created_at, 'updated_at': briefing.updated_at,
    }


class BriefingListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE_REPORTS')
        from intelligence.models import Briefing
        return paginate(request, self, Briefing.objects.all(), briefing_row)


class BriefingGenerateView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE_REPORTS')
        from intelligence import alerts as alert_service
        from intelligence import briefings as briefing_service
        from intelligence.models import Briefing
        kind = str(request.data.get('period', 'DAILY')).upper()
        if kind not in dict(Briefing.PERIOD):
            kind = 'DAILY'
        alert_service.evaluate_cycle_alerts()
        briefing = service_call(
            briefing_service.generate, kind=kind, actor=request.user,
            force=request.data.get('force') in (True, 'yes', 'true'))
        return Response(briefing_row(briefing), status=status.HTTP_201_CREATED)


class BriefingDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'VIEW_INTELLIGENCE_REPORTS')
        from intelligence import briefings as briefing_service
        from intelligence import security as security_service
        from intelligence.models import Briefing
        briefing = get_object_or_404(Briefing, pk=pk)
        data = briefing_row(briefing)
        data['data'] = briefing_service.briefing_data(briefing)
        data['telegram_text'] = briefing_service.short_text(briefing)
        data['show_security'] = security_service.is_holder(request.user)
        data['telegram_deliveries'] = [{
            'id': d.pk, 'recipient': d.recipient, 'status': d.status,
            'error': d.error, 'sent_at': d.sent_at,
        } for d in briefing.deliveries.filter(channel='TELEGRAM')]
        return Response(data)


class BriefingTelegramView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'VIEW_INTELLIGENCE_REPORTS')
        from intelligence import briefings as briefing_service
        from intelligence.models import Briefing
        briefing = get_object_or_404(Briefing, pk=pk)
        deliveries = briefing_service.send_telegram(briefing, actor=request.user)
        return Response({
            'briefing': briefing.pk,
            'deliveries': [{
                'id': d.pk, 'recipient': d.recipient, 'status': d.status,
                'error': d.error, 'sent_at': d.sent_at,
            } for d in deliveries],
            'sent': sum(1 for d in deliveries if d.status == 'SENT'),
            'failed': sum(1 for d in deliveries if d.status == 'FAILED'),
            'skipped': sum(1 for d in deliveries if d.status == 'SKIPPED'),
        })


def alert_rule_row(rule):
    return {
        'id': rule.pk, 'key': rule.key, 'label': rule.get_key_display(),
        'enabled': rule.enabled, 'channels': rule.channels,
        'recipient_capability': rule.recipient_capability,
        'recipient_emails': rule.recipient_emails,
        'email_list': rule.email_list(),
        'telegram_chat_ids': rule.telegram_chat_ids,
        'chat_id_list': rule.chat_id_list(),
        'updated_by': user_row(rule.updated_by) if rule.updated_by_id else None,
        'updated_at': rule.updated_at,
    }


class AlertRuleListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence import alerts as alert_service
        from intelligence.models import ALERT_RULES
        rules = [alert_service.get_rule(key) for key, _label in ALERT_RULES]
        return Response({'results': [alert_rule_row(r) for r in rules]})

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        """Part B (screen 177, owner approved): create a rule
        CONFIGURATION for a chosen kind.

        AlertRule.key is unique and the engine (intelligence/alerts
        .get_rule) resolves exactly ONE row per kind via
        get_or_create(key=...), so multiple rows per kind cannot
        work: creation is restricted to kinds with no existing rule
        row and returns a clear 400 for an already-configured kind
        (edit that rule instead). Kinds remain the fixed server-side
        ALERT_RULES vocabulary — no arbitrary kinds. Note the GET
        above lazily get_or_creates every kind, so in practice this
        endpoint serves deployments where a rule row is genuinely
        absent (e.g. a kind added to the vocabulary after the list
        was last read, or a row removed in admin). The configuration
        fields and validation are the existing AlertRuleForm's, and
        the audit row mirrors ALERT_RULE_UPDATED.
        """
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence.forms import AlertRuleForm
        from intelligence.models import ALERT_RULES, AlertRule, IntelligenceAudit
        key = request.data.get('key')
        if not key:
            raise ValidationError({'key': 'This field is required.'})
        if key not in dict(ALERT_RULES):
            raise ValidationError({'key': 'Unknown alert rule kind. Use one of: '
                                   + ', '.join(k for k, _label in ALERT_RULES)})
        if AlertRule.objects.filter(key=key).exists():
            raise ValidationError({'key': 'An alert rule for this kind is already '
                                   'configured. Edit the existing rule instead.'})
        form = form_or_400(AlertRuleForm(request.data))
        rule = form.save(commit=False)
        rule.key = key
        rule.updated_by = request.user
        rule.save()
        IntelligenceAudit.objects.create(
            actor=request.user, action='ALERT_RULE_CREATED',
            target_type='AlertRule', target_id=rule.pk,
            detail={'key': rule.key, 'enabled': rule.enabled,
                    'channels': rule.channels})
        return Response(alert_rule_row(rule), status=status.HTTP_201_CREATED)


class AlertRuleDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence.models import AlertRule
        return Response(alert_rule_row(get_object_or_404(AlertRule, pk=pk)))

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def put(self, request, pk):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence.forms import AlertRuleForm
        from intelligence.models import AlertRule, IntelligenceAudit
        rule = get_object_or_404(AlertRule, pk=pk)
        form = form_or_400(AlertRuleForm(request.data, instance=rule))
        rule = form.save(commit=False)
        rule.updated_by = request.user
        rule.save()
        IntelligenceAudit.objects.create(
            actor=request.user, action='ALERT_RULE_UPDATED',
            target_type='AlertRule', target_id=rule.pk,
            detail={'key': rule.key, 'enabled': rule.enabled,
                    'channels': rule.channels})
        return Response(alert_rule_row(rule))


class MyAlertsView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence.models import AlertDelivery
        deliveries = (AlertDelivery.objects.filter(
            channel='DASHBOARD', recipient=request.user.get_username())
            .select_related('alert').order_by('-created_at', '-pk'))
        unread = deliveries.filter(is_read=False).count()
        response = paginate(request, self, deliveries, lambda d: {
            'id': d.pk, 'alert': d.alert_id,
            'title': d.alert.title, 'message': d.alert.message,
            'kind': d.alert.kind, 'link': d.alert.link,
            'status': d.status, 'is_read': d.is_read, 'read_at': d.read_at,
            'created_at': d.created_at,
        })
        response.data['unread'] = unread
        return response


class AlertReadView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'VIEW_INTELLIGENCE')
        from intelligence.models import AlertDelivery
        delivery = get_object_or_404(
            AlertDelivery, pk=pk, channel='DASHBOARD',
            recipient=request.user.get_username())
        if not delivery.is_read:
            delivery.is_read = True
            delivery.read_at = timezone.now()
            delivery.save(update_fields=['is_read', 'read_at'])
        return Response({'id': delivery.pk, 'is_read': delivery.is_read,
                         'read_at': delivery.read_at})


# ─── B. Promise candidates (screens 180–181) ─────────────────────────────────

def candidate_row(candidate):
    return {
        'id': candidate.pk, 'status': candidate.status,
        'status_label': candidate.get_status_display(),
        'quote': candidate.quote, 'matched_pattern': candidate.matched_pattern,
        'institution_name': candidate.institution_name,
        'deadline_text': candidate.deadline_text,
        'publication': candidate.publication_id,
        'publication_title': (candidate.publication.title
                              if candidate.publication_id else None),
        'cluster': candidate.cluster_id,
        'lga': candidate.lga_id,
        'lga_name': candidate.lga.name if candidate.lga_id else None,
        'promise': candidate.promise_id,
        'decided_by': user_row(candidate.decided_by) if candidate.decided_by_id else None,
        'decided_at': candidate.decided_at,
        'decision_note': candidate.decision_note,
        'created_at': candidate.created_at,
    }


class PromiseCandidateListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'MANAGE_PROMISES')
        from intelligence.models import PromiseCandidate
        wanted = request.query_params.get('status', 'PENDING')
        if wanted not in dict(PromiseCandidate.STATUS):
            wanted = 'PENDING'
        rows = (PromiseCandidate.objects.filter(status=wanted)
                .select_related('publication__source', 'cluster', 'lga',
                                'promise', 'decided_by')
                .order_by('-created_at', '-pk'))
        response = paginate(request, self, rows, candidate_row)
        response.data['pending_total'] = PromiseCandidate.objects.filter(
            status='PENDING').count()
        return response


class PromiseCandidateDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'MANAGE_PROMISES')
        from intelligence import promise_detection
        from intelligence.models import PromiseCandidate
        candidate = get_object_or_404(
            PromiseCandidate.objects.select_related(
                'publication__source', 'lga', 'cluster'), pk=pk)
        data = candidate_row(candidate)
        pub = candidate.publication
        data['publication_detail'] = {
            'id': pub.pk, 'title': pub.title,
            'source': pub.source.name, 'original_url': pub.original_url,
            'published_at': pub.published_at,
            'default_title': promise_detection._default_title(candidate),
            'default_announced_on': (pub.published_at or pub.discovered_at).date(),
        }
        return Response(data)


class PromiseCandidateConfirmView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_PROMISES')
        from intelligence import promise_detection
        from intelligence.forms import CandidateConfirmForm
        from intelligence.models import PromiseCandidate
        from story_intelligence.models import Institution
        candidate = get_object_or_404(
            PromiseCandidate.objects.select_related(
                'publication__source', 'lga', 'cluster'), pk=pk)
        if candidate.status != 'PENDING':
            raise ValidationError('This candidate has already been decided.')
        pub = candidate.publication
        institution = None
        if candidate.institution_name:
            institution = Institution.objects.filter(
                name=candidate.institution_name).first()
        data = {
            'institution': (request.data.get('institution')
                            or (institution.pk if institution else '')),
            'institution_name': (request.data.get('institution_name')
                                 or ('' if institution else candidate.institution_name)),
            'title': (request.data.get('title')
                      or promise_detection._default_title(candidate)),
            'description': request.data.get('description') or candidate.quote,
            'announced_by': request.data.get('announced_by') or '',
            'announced_on': (request.data.get('announced_on')
                             or (pub.published_at or pub.discovered_at).date()),
            'deadline': request.data.get('deadline') or '',
            'sector': request.data.get('sector') or '',
        }
        form = form_or_400(CandidateConfirmForm(data))
        promise = service_call(
            promise_detection.confirm_candidate, candidate, request.user,
            institution=form.cleaned_data.get('institution'),
            institution_name=form.cleaned_data.get('institution_name', ''),
            title=form.cleaned_data['title'],
            description=form.cleaned_data['description'],
            announced_by=form.cleaned_data.get('announced_by', ''),
            announced_on=form.cleaned_data['announced_on'],
            deadline=form.cleaned_data.get('deadline'),
            sector=form.cleaned_data.get('sector', ''))
        from .public_content import PromiseSerializer
        return Response({
            'promise': PromiseSerializer(
                promise, context={'request': request}).data,
            'candidate': candidate_row(candidate),
        }, status=status.HTTP_201_CREATED)


class PromiseCandidateDismissView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_PROMISES')
        from intelligence import promise_detection
        from intelligence.models import PromiseCandidate
        candidate = get_object_or_404(PromiseCandidate, pk=pk)
        candidate = service_call(
            promise_detection.dismiss_candidate, candidate, request.user,
            reason=str(request.data.get('reason', '') or ''))
        return Response(candidate_row(candidate))


# ─── B. Security desk (screens 182–185) — holders only (D6) ─────────────────

def incident_row(incident, include_claims=False):
    from intelligence import security as security_service
    data = {
        'id': incident.pk, 'title': incident.title,
        'incident_type': incident.incident_type,
        'reported_at': incident.reported_at, 'occurred_at': incident.occurred_at,
        'lga': incident.lga_id,
        'lga_name': incident.lga.name if incident.lga_id else None,
        'location_text': incident.location_text,
        'status': incident.status,
        'status_label': incident.get_status_display(),
        'sensitivity': incident.sensitivity,
        'has_offline_detail': incident.has_offline_detail,
        'working_notes': incident.working_notes,
        'cluster': incident.cluster_id, 'publication': incident.publication_id,
        'article': incident.article_id,
        'created_by': user_row(incident.created_by) if incident.created_by_id else None,
        'created_at': incident.created_at, 'updated_at': incident.updated_at,
        # Casualty figures exist ONLY as attributed claims.
        'claims_lines': security_service.claims_lines(incident),
    }
    if include_claims:
        data['claims'] = [{
            'id': c.pk, 'label': c.label, 'count': c.count,
            'source_name': c.source_name, 'source_url': c.source_url,
            'attribution': c.attribution,
            'created_by': user_row(c.created_by) if c.created_by_id else None,
            'created_at': c.created_at,
        } for c in incident.claims.all()]
    return data


class SecurityDeskView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence import security as security_service
        from intelligence.models import SecurityIncident
        rows = []
        for cluster in security_service.restricted_clusters():
            rows.append(unit_row('cluster', cluster,
                                 members=list(cluster.publications.all())))
        for item in security_service.restricted_items():
            rows.append(unit_row('item', item, members=[item]))
        incidents = (SecurityIncident.objects.select_related('lga', 'cluster')
                     .prefetch_related('claims'))
        return Response({
            'units': rows, 'total_units': len(rows),
            'incidents': [incident_row(i, include_claims=True) for i in incidents],
        })


class SecurityUnitDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, ref):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        kind, unit = resolve_unit(ref)
        from intelligence import security as security_service
        if not security_service.unit_is_restricted(unit):
            raise NotFound('This unit is not on the security desk.')
        from intelligence.models import IntelligenceAudit
        IntelligenceAudit.objects.create(
            actor=request.user, action='SECURITY_VIEW',
            target_type='EventCluster' if kind == 'cluster' else 'RawPublication',
            target_id=unit.pk, detail={})
        from intelligence import desk as desk_service
        members = desk_service.unit_members(unit)
        data = unit_row(kind, unit, members=members)
        data.update({
            'members': [raw_item_row(m) for m in members],
            'working_text': unit.working_text,
            'decisions': [decision_row(d) for d in
                          unit.review_decisions.select_related('actor').all()],
            'available_actions': [
                {'action': a, 'label': desk_service.ACTION_BUTTON_LABELS[a]}
                for a in desk_service.available_actions(unit, request.user)],
            'incidents': [incident_row(i, include_claims=True)
                          for i in unit.security_incidents.select_related('lga').all()],
        })
        return Response(data)


class SecurityTransitionView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, ref):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        kind, unit = resolve_unit(ref)
        from intelligence import security as security_service
        if not security_service.unit_is_restricted(unit):
            raise NotFound('This unit is not on the security desk.')
        from intelligence import desk as desk_service
        decision = service_call(
            desk_service.apply_transition, unit, request.user,
            str(request.data.get('action', '')),
            note=str(request.data.get('note', '') or ''))
        unit.refresh_from_db()
        data = unit_row(kind, unit)
        data['decision'] = decision_row(decision)
        return Response(data)


class SecurityIncidentListCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence.models import SecurityIncident
        rows = (SecurityIncident.objects.select_related('lga', 'cluster')
                .prefetch_related('claims'))
        return paginate(request, self, rows,
                        lambda i: incident_row(i, include_claims=True))

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence import security as security_service
        from intelligence.forms import SecurityIncidentForm
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if isinstance(data.get('occurred_at'), str):
            parsed = parse_datetime(data['occurred_at'])
            if parsed is not None:
                data['occurred_at'] = parsed
        form = form_or_400(SecurityIncidentForm(data))
        unit = None
        ref = request.data.get('unit_ref') or request.data.get('unit')
        if ref:
            _kind, unit = resolve_unit(str(ref))
        incident = service_call(
            security_service.create_incident, request.user, unit=unit,
            **form.cleaned_data)
        return Response(incident_row(incident, include_claims=True),
                        status=status.HTTP_201_CREATED)


class SecurityIncidentDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence.models import IntelligenceAudit, SecurityIncident
        incident = get_object_or_404(
            SecurityIncident.objects.select_related('lga', 'cluster', 'publication'),
            pk=pk)
        IntelligenceAudit.objects.create(
            actor=request.user, action='SECURITY_VIEW',
            target_type='SecurityIncident', target_id=incident.pk, detail={})
        return Response(incident_row(incident, include_claims=True))


class SecurityIncidentClaimView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence import security as security_service
        from intelligence.forms import IncidentClaimForm
        from intelligence.models import SecurityIncident
        incident = get_object_or_404(SecurityIncident, pk=pk)
        form = form_or_400(IncidentClaimForm(request.data))
        claim = service_call(
            security_service.add_claim, request.user, incident,
            label=form.cleaned_data['label'], count=form.cleaned_data['count'],
            source_name=form.cleaned_data['source_name'],
            source_url=form.cleaned_data.get('source_url') or '')
        return Response({
            'id': claim.pk, 'label': claim.label, 'count': claim.count,
            'source_name': claim.source_name, 'source_url': claim.source_url,
            'attribution': claim.attribution,
        }, status=status.HTTP_201_CREATED)


class SecurityIncidentStatusView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence import security as security_service
        from intelligence.forms import IncidentStatusForm
        from intelligence.models import SecurityIncident
        incident = get_object_or_404(SecurityIncident, pk=pk)
        form = form_or_400(IncidentStatusForm(request.data))
        incident = service_call(
            security_service.set_incident_status, request.user, incident,
            form.cleaned_data['status'])
        return Response(incident_row(incident, include_claims=True))


class SecurityIncidentRedactView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        from intelligence import security as security_service
        from intelligence.forms import RedactForm
        from intelligence.models import SecurityIncident
        incident = get_object_or_404(SecurityIncident, pk=pk)
        form = form_or_400(RedactForm(request.data))
        count = service_call(
            security_service.redact_incident_notes, request.user, incident,
            form.cleaned_data['passage'])
        incident.refresh_from_db()
        data = incident_row(incident, include_claims=True)
        data['redacted_occurrences'] = count
        return Response(data)


# ─── B. Project management (screens 186–187) + tracking map (188) ───────────

def project_manage_row(project):
    from .public_content import ProjectDetailSerializer
    data = ProjectDetailSerializer(project).data
    return data


class ProjectManageDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'MANAGE_PROJECTS')
        from intelligence import projects as project_service
        from intelligence.models import Project
        project = get_object_or_404(
            Project.objects.select_related(
                'institution', 'lga', 'ward', 'district', 'community',
                'assigned_officer', 'source_cluster', 'source_publication'),
            pk=pk)
        data = project_manage_row(project)
        data['milestones'] = [{
            'id': m.pk, 'date': m.date, 'title': m.title, 'body': m.body,
            'status_after': m.status_after,
            'recorded_by': user_row(m.recorded_by) if m.recorded_by_id else None,
            'created_at': m.created_at,
        } for m in project.milestones.select_related('recorded_by')]
        data['evidence'] = [{
            'id': e.pk, 'kind': e.kind, 'kind_label': e.get_kind_display(),
            'title': e.title, 'url': e.url,
            'file': (e.file.url if e.file else None),
            'captured_at': e.captured_at, 'is_public': e.is_public,
            'verification_state': e.verification_state,
            'verification_state_label': e.get_verification_state_display(),
            'created_at': e.created_at,
        } for e in project.evidence.all()]
        data['qualifying_evidence_ids'] = [
            e.pk for e in project_service.qualifying_evidence(project)]
        data['can_verify_projects'] = cap(request.user, 'VERIFY_PROJECTS')
        return Response(data)


class ProjectStatusView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_PROJECTS')
        from intelligence import projects as project_service
        from intelligence.forms import ProjectStatusForm
        from intelligence.models import Project
        project = get_object_or_404(Project, pk=pk)
        form = form_or_400(ProjectStatusForm(request.data))
        project = service_call(
            project_service.set_project_status, project,
            form.cleaned_data['status'], request.user,
            note=form.cleaned_data.get('note', ''))
        return Response(project_manage_row(project))


class ProjectMilestoneView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_PROJECTS')
        from intelligence import projects as project_service
        from intelligence.forms import ProjectMilestoneForm
        from intelligence.models import Project
        project = get_object_or_404(Project, pk=pk)
        form = form_or_400(ProjectMilestoneForm(request.data))
        milestone = service_call(
            project_service.add_milestone, project, request.user,
            date=form.cleaned_data['date'], title=form.cleaned_data['title'],
            body=form.cleaned_data.get('body', ''))
        return Response({
            'id': milestone.pk, 'date': milestone.date,
            'title': milestone.title, 'body': milestone.body,
            'status_after': milestone.status_after,
            'created_at': milestone.created_at,
        }, status=status.HTTP_201_CREATED)


class ProjectEvidenceListCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_cap(request.user, 'MANAGE_PROJECTS')
        from intelligence.models import Project
        project = get_object_or_404(Project, pk=pk)
        return Response({'results': [{
            'id': e.pk, 'kind': e.kind, 'kind_label': e.get_kind_display(),
            'title': e.title, 'url': e.url,
            'file': (e.file.url if e.file else None),
            'captured_at': e.captured_at, 'is_public': e.is_public,
            'verification_state': e.verification_state,
            'verification_state_label': e.get_verification_state_display(),
            'created_at': e.created_at,
        } for e in project.evidence.all()]})

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_cap(request.user, 'MANAGE_PROJECTS')
        from intelligence import projects as project_service
        from intelligence.forms import ProjectEvidenceForm
        from intelligence.models import Project
        project = get_object_or_404(Project, pk=pk)
        form = form_or_400(ProjectEvidenceForm(request.data, request.FILES or None))
        evidence = service_call(
            project_service.add_evidence, project, request.user,
            **form.cleaned_data)
        return Response({
            'id': evidence.pk, 'kind': evidence.kind, 'title': evidence.title,
            'verification_state': evidence.verification_state,
            'is_public': evidence.is_public, 'created_at': evidence.created_at,
        }, status=status.HTTP_201_CREATED)


class IntelligenceMapView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from intelligence.views import TRACKING_CAPABILITIES
        if not any(cap(request.user, c) for c in TRACKING_CAPABILITIES):
            raise PermissionDenied('Your KPN role does not permit this action.')
        from intelligence import article_locations
        from intelligence import tracking as tracking_service
        rows = tracking_service.lga_tracking_rows()
        return Response({
            'results': [{
                'lga': row['lga'].pk, 'name': row['lga'].name,
                'slug': article_locations.lga_slug(row['lga']),
                'zone': row['lga'].zone_id, 'zone_name': row['lga'].zone.name,
                'tracked': row['tracked'], 'in_progress': row['in_progress'],
                'delayed': row['delayed'], 'verified': row['verified'],
                'pj_tracked': row['pj_tracked'],
                'pj_delayed_stalled': row['pj_delayed_stalled'],
                'pj_reported_abandoned': row['pj_reported_abandoned'],
                'pj_verified_abandoned': row['pj_verified_abandoned'],
                'pj_completed': row['pj_completed'],
                'ward_count': row['ward_count'],
                'district_count': row['district_count'],
                'community_count': row['community_count'],
                'geometry': row['geometry'], 'fill': row['fill'],
            } for row in rows],
            'totals': tracking_service.totals_for(rows),
            'project_totals': tracking_service.project_totals_for(rows),
        })


# ─── B. Story-intelligence desks (screens 189–194) ───────────────────────────

def promise_desk_row(promise):
    from .public_content import PromiseDetailSerializer
    return PromiseDetailSerializer(promise).data


class PromiseDeskListView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.models import Institution, Promise
        promises = (Promise.objects.select_related('institution', 'lga')
                    .prefetch_related('updates', 'stories'))
        response = paginate(request, self, promises, promise_desk_row)
        response.data['institutions'] = [
            {'id': i.pk, 'name': i.name, 'kind': i.kind}
            for i in Institution.objects.all()]
        response.data['can_verify'] = story_cap(request.user, 'VERIFY_PROMISES')
        return response


class PromiseDeskDetailView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.models import Promise, StoryAudit
        promise = get_object_or_404(
            Promise.objects.select_related('institution', 'lga', 'zone', 'ward')
            .prefetch_related('stories', 'updates'), pk=pk)
        data = promise_desk_row(promise)
        data['can_verify'] = story_cap(request.user, 'VERIFY_PROMISES')
        data['has_verification_evidence'] = promise.has_verification_evidence()
        data['audit_entries'] = [{
            'id': e.pk, 'action': e.action,
            'actor': user_row(e.actor) if e.actor_id else None,
            'created_at': e.created_at,
        } for e in StoryAudit.objects.filter(
            target_type='promise', target_id=promise.pk)[:50]]
        return Response(data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request, pk):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.forms import PromiseForm
        from story_intelligence.models import Promise
        from story_intelligence.services import log_audit
        promise = get_object_or_404(Promise, pk=pk)
        # Merge stored values with the patch so partial edits validate
        # through the same PromiseForm the web desk saves with.
        data = {
            'institution': promise.institution_id, 'title': promise.title,
            'description': promise.description,
            'announced_by': promise.announced_by,
            'announced_on': promise.announced_on,
            'source_name': promise.source_name, 'source_url': promise.source_url,
            'deadline': promise.deadline, 'sector': promise.sector,
            'zone': promise.zone_id, 'lga': promise.lga_id,
            'ward': promise.ward_id,
            'stories': list(promise.stories.values_list('pk', flat=True)),
            'next_check_date': promise.next_check_date,
        }
        for key, value in request.data.items():
            data[key] = value
        form = form_or_400(PromiseForm(data, request.FILES or None, instance=promise))
        form.save()
        log_audit(request.user, 'PROMISE_EDITED', 'promise', promise.pk, {})
        promise.refresh_from_db()
        return Response(promise_desk_row(promise))


class PromiseCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.forms import PromiseForm
        from story_intelligence.services import log_audit
        form = form_or_400(PromiseForm(request.data, request.FILES or None))
        promise = form.save(commit=False)
        promise.created_by = request.user
        promise.save()
        form.save_m2m()
        log_audit(request.user, 'PROMISE_CREATED', 'promise', promise.pk,
                  {'institution_id': promise.institution_id,
                   'status': promise.status})
        return Response(promise_desk_row(promise), status=status.HTTP_201_CREATED)


class PromiseUpdateCreateView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.forms import PromiseUpdateForm
        from story_intelligence.models import Promise
        from story_intelligence import services as story_services
        promise = get_object_or_404(Promise, pk=pk)
        data = dict(request.data)
        data.setdefault('update_date', timezone.localdate())
        form = form_or_400(PromiseUpdateForm(data))
        update = service_call(
            story_services.record_promise_update, promise, request.user,
            update_date=form.cleaned_data['update_date'],
            title=form.cleaned_data['title'], body=form.cleaned_data['body'],
            evidence_title=form.cleaned_data['evidence_title'],
            evidence_url=form.cleaned_data['evidence_url'],
            new_status=form.cleaned_data.get('new_status', ''))
        return Response({
            'id': update.pk, 'update_date': update.update_date,
            'title': update.title, 'body': update.body,
            'status_after': update.status_after,
            'evidence_title': update.evidence_title,
            'evidence_url': update.evidence_url,
            'promise_status': promise.status,
        }, status=status.HTTP_201_CREATED)


class PromiseStatusView(APIView):
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.forms import PromiseStatusForm
        from story_intelligence.models import Promise
        from story_intelligence import services as story_services
        promise = get_object_or_404(Promise, pk=pk)
        form = form_or_400(PromiseStatusForm(request.data))
        promise = service_call(
            story_services.set_promise_status, promise,
            form.cleaned_data['status'], request.user,
            note=form.cleaned_data.get('note', ''))
        return Response(promise_desk_row(promise))


class StoryDeskView(APIView):
    """Story verification desk (screen 192): GET the desk, POST actions."""
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        require_story_cap(request.user, 'MANAGE_STORY_RECORDS')
        from campaigns.models import Campaign
        from story_intelligence.models import StoryAudit, StoryProfile
        from story_intelligence import services as story_services
        article = get_object_or_404(Campaign, pk=pk)
        profile = StoryProfile.objects.filter(article=article).first()
        from .public_content import (
            ClaimSerializer, CorrectionSerializer, PublicEvidenceSerializer,
            StoryProfileSerializer, StoryUpdateSerializer,
        )
        context = {'request': request}
        return Response({
            'article': {
                'id': article.pk, 'slug': article.slug, 'title': article.title,
                'status': article.status, 'story_id': article.story_id,
                'category': article.category,
                'verification_status': article.verification_status,
                'verification_status_label': article.get_verification_status_display(),
            },
            'profile': (StoryProfileSerializer(profile, context=context).data
                        if profile is not None else None),
            'signal_missing_evidence': bool(
                profile and profile.kind == 'SIGNAL'
                and not profile.signal_has_evidence()),
            'consent_block_reason': (story_services.consent_block_reason(article)
                                     if profile else ''),
            'claims': ClaimSerializer(
                article.claims.all(), many=True, context=context).data,
            'evidence': PublicEvidenceSerializer(
                article.evidence_records.all(), many=True, context=context).data,
            'updates': StoryUpdateSerializer(
                article.story_updates.all(), many=True, context=context).data,
            'corrections': CorrectionSerializer(
                article.corrections.all(), many=True, context=context).data,
            'consent_records_on_file': article.consent_records.filter(
                withdrawn=False).count(),
            'verification_events': [{
                'id': e.pk, 'field': e.field, 'old_value': e.old_value,
                'new_value': e.new_value, 'reason': e.reason,
                'actor': user_row(e.actor) if e.actor_id else None,
                'created_at': e.created_at,
            } for e in article.verification_events.select_related('actor')[:50]],
            'audit_entries': [{
                'id': e.pk, 'action': e.action, 'target_type': e.target_type,
                'actor': user_row(e.actor) if e.actor_id else None,
                'created_at': e.created_at,
            } for e in StoryAudit.objects.filter(
                target_type='campaign', target_id=article.pk)[:50]],
            'can_publish_updates': story_cap(request.user, 'PUBLISH_STORY_UPDATES'),
            'can_redact': story_cap(request.user, 'PERFORM_REDACTION'),
        })

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        require_story_cap(request.user, 'MANAGE_STORY_RECORDS')
        from campaigns.models import Campaign
        from story_intelligence import services as story_services
        from story_intelligence.forms import (
            ClaimForm, ClaimStatusForm, CorrectionForm, EvidenceForm,
            StoryUpdateForm,
        )
        from story_intelligence.models import Claim
        from story_intelligence.services import log_audit
        article = get_object_or_404(Campaign, pk=pk)
        action = str(request.data.get('action', ''))
        if action == 'claim_status':
            claim = get_object_or_404(Claim, pk=request.data.get('claim_id'),
                                      article_id=article.pk)
            form = form_or_400(ClaimStatusForm(request.data))
            service_call(story_services.set_claim_status, claim,
                         form.cleaned_data['status'], request.user,
                         reason=form.cleaned_data.get('reason', ''))
            return Response({'claim': {'id': claim.pk, 'status': claim.status}})
        if action == 'verification':
            from story_intelligence.forms import ArticleVerificationForm
            form = form_or_400(ArticleVerificationForm(request.data))
            service_call(story_services.set_article_verification_status,
                         article, form.cleaned_data['verification_status'],
                         request.user,
                         reason=form.cleaned_data.get('reason', ''))
            return Response({'article': {
                'id': article.pk,
                'verification_status': article.verification_status}})
        if action == 'add_claim':
            form = form_or_400(ClaimForm(request.data))
            claim = form.save(commit=False)
            claim.article = article
            claim.noted_by = request.user
            claim.save()
            log_audit(request.user, 'CLAIM_ADDED', 'claim', claim.pk,
                      {'article_id': article.pk, 'status': claim.status})
            return Response({'claim': {'id': claim.pk, 'status': claim.status}},
                            status=status.HTTP_201_CREATED)
        if action == 'add_evidence':
            form = form_or_400(EvidenceForm(
                request.data, request.FILES or None, article=article))
            evidence = form.save(commit=False)
            evidence.article = article
            evidence.added_by = request.user
            evidence.save()
            log_audit(request.user, 'EVIDENCE_ADDED', 'evidence', evidence.pk,
                      {'article_id': article.pk, 'kind': evidence.kind,
                       'is_public': evidence.is_public})
            return Response({'evidence': {'id': evidence.pk}},
                            status=status.HTTP_201_CREATED)
        if action == 'add_correction':
            form = form_or_400(CorrectionForm(request.data, article=article))
            correction = form.save(commit=False)
            correction.article = article
            correction.created_by = request.user
            correction.save()
            log_audit(request.user, 'CORRECTION_ADDED', 'correction',
                      correction.pk,
                      {'article_id': article.pk, 'kind': correction.kind})
            return Response({'correction': {'id': correction.pk}},
                            status=status.HTTP_201_CREATED)
        if action == 'add_update':
            form = form_or_400(StoryUpdateForm(request.data))
            update = form.save(commit=False)
            update.article = article
            update.author = request.user
            if (form.cleaned_data.get('publish_now')
                    and story_cap(request.user, 'PUBLISH_STORY_UPDATES')):
                update.status = 'PUBLISHED'
                update.published_at = timezone.now()
            update.save()
            log_audit(request.user, 'STORY_UPDATE_ADDED', 'story_update',
                      update.pk,
                      {'article_id': article.pk, 'status': update.status})
            return Response({'update': {'id': update.pk, 'status': update.status}},
                            status=status.HTTP_201_CREATED)
        raise ValidationError({'action': 'Unknown story desk action.'})


class RadarView(APIView):
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        require_story_cap(request.user, 'MANAGE_STORY_RECORDS')
        from campaigns.models import Campaign
        from core.models import CommunityReport
        from story_intelligence.models import StorySourceLink

        def report_row(report):
            return {
                'id': report.pk, 'category': report.category,
                'category_label': report.get_category_display(),
                'location_details': report.location_details,
                'lga': report.lga_id,
                'lga_name': report.lga.name if report.lga_id else None,
                'zone': report.zone_id,
                'what_happened': report.what_happened,
                'status': report.status,
                'status_label': report.get_status_display(),
                'incident_date': report.incident_date,
                'created_at': report.created_at,
                'link_count': getattr(report, 'link_count', None),
                'linked_article_ids': [link.article_id
                                       for link in report.story_links.all()],
            }
        unlinked = (CommunityReport.objects.filter(status='APPROVED')
                    .annotate(link_count=Count('story_links'))
                    .filter(link_count=0)
                    .select_related('lga', 'zone').order_by('-created_at')[:50])
        reports = (CommunityReport.objects.select_related('lga', 'zone')
                   .prefetch_related('story_links__article')
                   .order_by('-created_at')[:50])
        return Response({
            'unlinked_approved': [report_row(r) for r in unlinked],
            'reports': [report_row(r) for r in reports],
            'published_articles': [{
                'id': a.pk, 'slug': a.slug, 'title': a.title,
                'story_id': a.story_id,
            } for a in Campaign.objects.filter(status='PUBLISHED')
                .order_by('-published_at')[:100]],
            'link_kinds': StorySourceLink.KIND_CHOICES,
        })


class StoryRedactView(APIView):
    """Emergency redaction (screen 194) — the web service, unchanged."""
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        require_story_cap(request.user, 'PERFORM_REDACTION')
        from story_intelligence import services as story_services
        target_type = request.data.get('target_type') or 'article'
        target_id = request.data.get('target_id')
        if target_id is None:
            target_id = (request.data.get('article_id')
                         or request.data.get('story_id')
                         or request.data.get('id'))
        if isinstance(target_id, str) and target_id.startswith('KPN-SI-'):
            from campaigns.models import Campaign
            article = Campaign.objects.filter(story_id=target_id).first()
            if article is None:
                raise NotFound('No story with that Story ID.')
            target_id = article.pk
        reason_category = (request.data.get('reason_category')
                           or request.data.get('reason'))
        valid = dict(story_services.REDACTION_REASON_CATEGORIES)
        if reason_category not in valid:
            raise ValidationError({
                'reason_category': f'Choose one of: {", ".join(valid)}.'})
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            raise ValidationError({'target_id': 'A record id is required.'})
        from campaigns.models import Campaign
        from story_intelligence.models import Claim, EvidenceRecord, StoryUpdate
        try:
            result = service_call(
                story_services.perform_redaction, actor=request.user,
                target_type=target_type, target_id=target_id,
                reason_category=reason_category)
        except (Campaign.DoesNotExist, Claim.DoesNotExist,
                StoryUpdate.DoesNotExist, EvidenceRecord.DoesNotExist):
            raise NotFound('That record could not be found.')
        return Response(result)


# ─── B. Editorial brain workspace (screens 195–197) ──────────────────────────

def editorial_item_row(item):
    return {
        'id': item.pk, 'key': item.key, 'kind': item.kind,
        'kind_label': item.get_kind_display(),
        'state': item.state, 'state_label': item.get_state_display(),
        'title': item.title,
        'source': ({'id': item.source.pk, 'name': item.source.name}
                   if item.source_id else None),
        'source_url': item.source_url,
        'article': item.article_id, 'opportunity': item.opportunity_id,
        'report': item.report_id, 'community_report': item.community_report_id,
        'version': item.version,
        'reviewed_by': user_row(item.reviewed_by) if item.reviewed_by_id else None,
        'created_at': item.created_at, 'updated_at': item.updated_at,
    }


class EditorialOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from editorial import access as editorial_access
        if not editorial_access.active(request.user):
            raise PermissionDenied('Your KPN role does not permit this action.')
        from django.conf import settings as django_settings
        from editorial.models import Control, Item, Job, LinkCheck, Source
        rows = editorial_access.items_for(request.user)
        scoped = editorial_access.items_for(request.user)
        by_state = {value: scoped.filter(state=value).count()
                    for value, _label in Item.STATE}
        by_kind = {value: scoped.filter(kind=value).count()
                   for value, _label in Item.KIND}
        is_manager = editorial_access.manager(request.user)
        control, _created = Control.objects.get_or_create(pk=1)
        data = {
            'items_by_state': by_state, 'items_by_kind': by_kind,
            'total_items': scoped.count(),
            'brain_waiting': Item.objects.filter(state='WAITING').count(),
            'brain_queued': Job.objects.filter(kind='GENERATE', state='QUEUED').count(),
            'control': {'enabled': control.enabled},
            'feature_enabled': django_settings.KPN_EDITORIAL_ENABLED,
            'can_manage': is_manager,
            'can_edit': editorial_access.editor(request.user),
            'recent_items': [editorial_item_row(i) for i in rows[:20]],
        }
        if is_manager:
            data['sources'] = [{
                'id': s.pk, 'name': s.name, 'kind': s.kind, 'url': s.url,
                'enabled': s.enabled,
                'consecutive_failures': s.consecutive_failures,
            } for s in Source.objects.all()]
            data['links'] = [{
                'id': link.pk, 'opportunity': link.opportunity_id,
                'url': link.url, 'day': link.day, 'state': link.state,
                'http_status': link.http_status,
            } for link in LinkCheck.objects.select_related('opportunity')
                .order_by('-day', 'pk')[:20]]
        return Response(data)


class EditorialItemDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        from editorial import access as editorial_access
        from editorial.services import source_current
        item = get_object_or_404(editorial_access.items_for(request.user), pk=pk)
        data = editorial_item_row(item)
        data.update({
            'original': item.original, 'draft': item.draft,
            'source_current': source_current(item),
            'audit': [{
                'id': a.pk, 'action': a.action, 'detail': a.detail,
                'actor': user_row(a.actor) if a.actor_id else None,
                'created_at': a.created_at,
            } for a in item.audit.select_related('actor')[:30]],
        })
        return Response(data)


def editorial_source_row(source):
    return {
        'id': source.pk, 'name': source.name, 'kind': source.kind,
        'kind_label': source.get_kind_display(), 'url': source.url,
        'feed': source.feed, 'allowed_hosts': source.allowed_hosts,
        'keywords': source.keywords, 'max_items': source.max_items,
        'enabled': source.enabled,
        'connector_kind': source.connector_kind,
        'poll_interval_minutes': source.poll_interval_minutes,
        'consecutive_failures': source.consecutive_failures,
        'last_success_at': source.last_success_at, 'last_error': source.last_error,
        'created_at': source.created_at,
    }


class EditorialSourceListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from editorial import access as editorial_access
        if not editorial_access.manager(request.user):
            raise PermissionDenied('Your KPN role does not permit this action.')
        from editorial.models import Source
        return Response({'results': [editorial_source_row(s)
                                     for s in Source.objects.all()]})

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        # Part A: source create, mirroring the web source_edit view
        # (editorial/views.py) — manager-only, the same SourceForm,
        # saved on a fresh Source() and audited as SOURCE_SAVED.
        from editorial import access as editorial_access
        if not editorial_access.manager(request.user):
            raise PermissionDenied('Your KPN role does not permit this action.')
        from editorial.forms import SourceForm
        from editorial.models import Audit, Source
        form = form_or_400(SourceForm(request.data, instance=Source()))
        source = form.save()
        Audit.objects.create(actor=request.user, action='SOURCE_SAVED',
                             detail={'source_id': source.pk})
        return Response(editorial_source_row(source),
                        status=status.HTTP_201_CREATED)


class EditorialSourceEditView(APIView):
    """Part A: source edit (PUT), mirroring web source_edit with a pk —
    manager-only, the same SourceForm on the existing instance, and
    the same SOURCE_SAVED audit row."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def put(self, request, pk):
        from editorial import access as editorial_access
        if not editorial_access.manager(request.user):
            raise PermissionDenied('Your KPN role does not permit this action.')
        from editorial.forms import SourceForm
        from editorial.models import Audit, Source
        source = get_object_or_404(Source, pk=pk)
        form = form_or_400(SourceForm(request.data, instance=source))
        source = form.save()
        Audit.objects.create(actor=request.user, action='SOURCE_SAVED',
                             detail={'source_id': source.pk})
        return Response(editorial_source_row(source))


class EditorialSourceApproveView(APIView):
    """Approve an editorial source (screen 197).

    FLAG: the web editorial workspace has no separate "approve" action —
    a source is approved by saving it with ``enabled=True`` through
    source_edit (manager-only, audited as SOURCE_SAVED). This endpoint
    performs exactly that state change with the same gate and audit.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        from editorial import access as editorial_access
        if not editorial_access.manager(request.user):
            raise PermissionDenied('Your KPN role does not permit this action.')
        from editorial.models import Audit, Source
        source = get_object_or_404(Source, pk=pk)
        source.enabled = True
        source.save(update_fields=['enabled'])
        Audit.objects.create(actor=request.user, action='SOURCE_SAVED',
                             detail={'source_id': source.pk, 'approved': True})
        return Response(editorial_source_row(source))


# ─── B. ICT Admin console (screens 198–202) — holder or superuser only ──────

def ict_gate(user):
    from core.ict_admin import is_ict_admin
    if not is_ict_admin(user):
        raise PermissionDenied(
            'The ICT Admin console is restricted to the ICT Admin holder.')


def ict_member_row(user):
    from leadership.access import role_title
    return {
        'id': user.pk, 'username': user.get_username(),
        'name': user.get_full_name(), 'status': user.status,
        'role_title': role_title(user),
        'zone': user.zone.name if user.zone_id else None,
        'lga': user.lga.name if user.lga_id else None,
        'created_at': user.created_at,
    }


class IctOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ict_gate(request.user)
        from campaigns.models import Campaign
        from core.dashboard_charts import count_by
        from core.ict_admin import current_assignment
        from core.ict_views import _change_history, _member_base
        from core.models import (
            CommunityReport, Opportunity, OpportunityReport,
        )
        from intelligence.models import Project
        from leadership.access import role_title
        from staff.models import User
        from story_intelligence.models import Promise
        members = _member_base()
        verified = members.filter(status='VERIFIED')
        assignment = current_assignment()
        holder = assignment.user
        return Response({
            'stats': {
                'total_members': members.count(),
                'verified_members': verified.count(),
                'pending_verification': members.filter(
                    status__in=('PENDING', 'UNDER_REVIEW')).count(),
                'position_holders': verified.filter(
                    role_definition__isnull=False).count(),
                'published_articles': Campaign.objects.filter(
                    status='PUBLISHED').count(),
                'open_opportunities': Opportunity.objects.filter(
                    status='OPEN').count(),
                'pending_community_reports': CommunityReport.objects.filter(
                    status='PENDING').count(),
                'new_listing_reports': OpportunityReport.objects.filter(
                    status='NEW').count(),
            },
            'campaign_status_counts': [
                {'label': label, 'value': value} for label, value in
                count_by(Campaign.objects.all(), 'status', Campaign.STATUS_CHOICES)],
            'opportunity_status_counts': [
                {'label': label, 'value': value} for label, value in
                count_by(Opportunity.objects.all(), 'status',
                         Opportunity.STATUS_CHOICES)],
            'promises_total': Promise.objects.count(),
            'projects_total': Project.objects.count(),
            'assignment': {
                'holder': ict_member_row(holder) if holder else None,
                'holder_title': role_title(holder) if holder else None,
                'managed_by': ('The Super Admin, in the Django admin panel '
                               'only.'),
            },
            'change_history': [{
                'id': change.pk,
                'previous_holder': (change.previous_holder.get_username()
                                    if change.previous_holder_id else None),
                'new_holder': (change.new_holder.get_username()
                               if change.new_holder_id else None),
                'changed_by': (change.changed_by.get_username()
                               if change.changed_by_id else None),
                'created_at': change.created_at,
            } for change in _change_history()],
        })


class IctMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ict_gate(request.user)
        from core.dashboard_charts import bar_rows, count_by
        from core.ict_views import _member_base
        from staff.models import User
        members = _member_base()
        verified = members.filter(status='VERIFIED')
        recent = (members.select_related('lga', 'zone', 'role_definition')
                  .order_by('-created_at')[:10])
        return Response({
            'member_status_bars': bar_rows(count_by(
                members, 'status', User.STATUS_CHOICES)),
            'member_zone_bars': bar_rows(count_by(
                verified.filter(zone__isnull=False), 'zone__name')),
            'recent_members': [ict_member_row(u) for u in recent],
            'total_members': members.count(),
        })


class IctLeadershipView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ict_gate(request.user)
        from core.ict_views import _leadership_rows
        return Response({'results': [{
            'definition': {
                'id': row['definition'].pk, 'title': row['definition'].title,
                'tier': row['definition'].tier,
            },
            'holders': [ict_member_row(u) for u in row['holders']],
        } for row in _leadership_rows()]})


class IctIntelligenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ict_gate(request.user)
        from core.dashboard_charts import count_by
        from core.ict_views import _source_health_summary
        from editorial.models import Item as EditorialItem
        from editorial.models import Source as EditorialSource
        from intelligence.models import AlertDelivery, CollectionRun
        return Response({
            'editorial_item_states': [
                {'label': label, 'value': value} for label, value in
                count_by(EditorialItem.objects.all(), 'state',
                         EditorialItem.STATE)],
            'sources_total': EditorialSource.objects.count(),
            'sources_enabled': EditorialSource.objects.filter(
                enabled=True).count(),
            'sources_failing': EditorialSource.objects.filter(
                consecutive_failures__gt=0).count(),
            'source_health_summary': _source_health_summary(),
            'collection_runs': [{
                'id': run.pk, 'status': run.status, 'trigger': run.trigger,
                'started_at': run.started_at, 'finished_at': run.finished_at,
                'items_new': run.items_new, 'error': run.error,
            } for run in CollectionRun.objects.all()[:8]],
            'alert_failures': AlertDelivery.objects.filter(
                status='FAILED').count(),
            'alerts_total': AlertDelivery.objects.count(),
        })


class IctTelegramView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ict_gate(request.user)
        from django.conf import settings as django_settings

        from staff.models import User
        from telegram_integration.models import BotOutbox, TelegramMembership
        # Round 2 (screen 202): bot/channel identity the site actually
        # holds — the configured bot username and channel chat id from
        # settings (telegram_integration reads the same values). No
        # channel handle is stored anywhere, so none is returned.
        # "Leaders not linked" is computed server-side from real
        # counts: verified leadership holders (a RoleDefinition seat,
        # superusers excluded as everywhere on this console) without a
        # verified Telegram membership.
        leaders = User.objects.filter(
            status='VERIFIED', is_superuser=False,
            role_definition__isnull=False)
        leaders_linked = leaders.filter(
            telegram_membership__is_verified=True).count()
        bot_username = str(
            getattr(django_settings, 'TELEGRAM_BOT_USERNAME', '') or '').lstrip('@')
        return Response({
            'telegram_connected': TelegramMembership.objects.count(),
            'telegram_verified': TelegramMembership.objects.filter(
                is_verified=True).count(),
            'bot_username': f'@{bot_username}' if bot_username else None,
            'channel_id': str(
                getattr(django_settings, 'TELEGRAM_CHANNEL_ID', '') or '') or None,
            'leaders_total': leaders.count(),
            'leaders_linked': leaders_linked,
            'leaders_not_linked': leaders.count() - leaders_linked,
            'outbox_queued': BotOutbox.objects.filter(state='QUEUED').count(),
            'outbox_sent': BotOutbox.objects.filter(state='SENT').count(),
            'outbox_failed': BotOutbox.objects.filter(state='FAILED').count(),
        })


# ─── Part A: endpoints added for the next Android screens ───────────────────
# Each view wraps the corresponding WEB view's logic: the same gate,
# the same form and the same service functions, so web and mobile
# behaviour (state, audit rows, validation) cannot drift apart.

def _security_unit_or_404(kind, pk):
    """intelligence.views._security_unit, with the web URL converter's
    cluster|item restriction applied."""
    if kind not in ('cluster', 'item'):
        raise NotFound('Unknown desk unit.')
    from intelligence.views import _security_unit
    return _security_unit(kind, pk)


def working_copy_row(kind, unit):
    text = unit.working_text or ''
    data = unit_row(kind, unit)
    data.update({
        'working_text': text,
        'has_working_copy': bool(text.strip()),
        # The web security page renders the working copy as one block
        # built from member reports joined by blank lines; the passage
        # list is that same text split on those joins — nothing is
        # derived from the underlying evidence records here.
        'passages': text.split('\n\n') if text.strip() else [],
        'working_copy_characters': len(text),
    })
    return data


class SecurityWorkingCopyView(APIView):
    """Security Desk working copy (web: intelligence.views
    .security_working_copy + the working-copy section of the web
    security unit page).

    Holders only — VIEW_SECURITY_DESK, held by exactly the Director
    of Media & Communications and the President (D6). GET mirrors the
    web unit page's working-copy section and writes the same
    SECURITY_VIEW audit row that page writes. POST performs the web
    form's two actions through intelligence.security: ``prepare``
    (re)builds the copy from member reports and ``redact`` blanks one
    exact passage via RedactForm. Redaction touches only the working
    copy; the service's audit rows record occurrence counts and
    passage lengths only, never passage text.
    """
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, kind, pk):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        unit = _security_unit_or_404(kind, pk)
        from intelligence import security as security_service
        if not security_service.unit_is_restricted(unit):
            raise NotFound('This unit is not on the security desk.')
        from intelligence.views import _audit
        _audit(request.user, 'SECURITY_VIEW',
               'EventCluster' if kind == 'cluster' else 'RawPublication',
               unit.pk, {})
        return Response(working_copy_row(kind, unit))

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, kind, pk):
        require_cap(request.user, 'VIEW_SECURITY_DESK')
        unit = _security_unit_or_404(kind, pk)
        from intelligence import security as security_service
        if not security_service.unit_is_restricted(unit):
            raise NotFound('This unit is not on the security desk.')
        action = str(request.data.get('action', ''))
        extra = {'action': action}
        if action == 'prepare':
            service_call(security_service.prepare_working_copy,
                         unit, request.user)
        elif action == 'redact':
            from intelligence.forms import RedactForm
            form = form_or_400(RedactForm(request.data))
            extra['redacted_occurrences'] = service_call(
                security_service.redact_passage, unit, request.user,
                form.cleaned_data['passage'])
        else:
            raise ValidationError({'action': 'Unknown working-copy action.'})
        unit.refresh_from_db()
        data = working_copy_row(kind, unit)
        data.update(extra)
        return Response(data)


class IdTagView(APIView):
    """Printable ID tag (web: staff.views.generate_id_tag at
    account/generate-id-tag/).

    The web view IS the generation code path: this view hands it the
    API request's underlying Django request with the authenticated
    member attached, and returns its PDF response untouched (2 pages,
    content-type application/pdf, the web's attachment filename).
    The web gate is login-only plus its own block on GENERAL members,
    mirrored here exactly — no other member may be named, so a member
    can only ever receive their own tag.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        if getattr(request.user, 'role', None) == 'GENERAL':
            raise PermissionDenied(
                'General members are not authorized to generate ID cards.')
        from staff.id_tags import id_tag_limit_reached, limit_message
        if id_tag_limit_reached(request.user):
            return Response({'detail': limit_message()}, status=429)
        from django.http import HttpResponse
        from staff.views import generate_id_tag
        django_request = request._request
        django_request.user = request.user
        response = generate_id_tag(django_request)
        if isinstance(response, HttpResponse) \
                and response.get('Content-Type', '') == 'application/pdf':
            return response
        # The web view redirects to the dashboard with an error message
        # when the card templates/fonts are unavailable; the API
        # surfaces that as an error envelope instead of a redirect.
        detail = 'ID tag could not be generated.'
        storage = getattr(django_request, '_messages', None)
        if storage is not None:
            messages = [str(message) for message in storage]
            if messages:
                detail = messages[-1]
        raise ValidationError(detail)


class ProjectFromUnitView(APIView):
    """Create a tracked project from a desk unit (web:
    intelligence.views.project_from_unit).

    Same gate (MANAGE_PROJECTS), same unit resolution and restricted-
    unit visibility (intelligence.views._desk_unit_or_404), same
    proposal service (propose_from_unit — VERIFIED / APPROVED /
    PUBLISHED units only), the proposal prefill standing in for the
    web form's initial values under any fields the caller supplies,
    the same ProjectForm, and the same create_project service call
    with the unit stored as the project's provenance link.
    """
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, kind, pk):
        require_cap(request.user, 'MANAGE_PROJECTS')
        if kind not in ('cluster', 'item'):
            raise NotFound('Unknown desk unit.')
        from intelligence import projects as project_service
        from intelligence.forms import ProjectForm
        from intelligence.views import _desk_unit_or_404
        unit = _desk_unit_or_404(kind, pk, request.user)
        initial = service_call(
            project_service.propose_from_unit, request.user, unit)
        data = dict(initial)
        for key, value in request.data.items():
            data[key] = value
        form = form_or_400(ProjectForm(data, initial=initial))
        links = ({'source_cluster': unit} if kind == 'cluster'
                 else {'source_publication': unit})
        project = service_call(
            project_service.create_project, request.user, **links,
            **form.cleaned_data)
        return Response(project_manage_row(project),
                        status=status.HTTP_201_CREATED)


class AttendanceLogsView(APIView):
    """Cross-event attendance logs (web: events.views
    .view_attendance_logs) — present attendances across all events,
    most recent first, the web page's 50 most recent, in the standard
    pagination envelope. The web page is login-only; the API keeps
    the staff API's verified-member gate (AUTH)."""
    permission_classes = AUTH

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from events.models import EventAttendance
        rows = list(
            EventAttendance.objects.filter(present=True)
            .select_related('event', 'attendee', 'recorded_by')
            .order_by('-recorded_at', '-pk')[:50])

        def row(attendance):
            return {
                'id': attendance.pk,
                'event': {'id': attendance.event_id,
                          'title': attendance.event.title},
                'attendee': user_row(attendance.attendee),
                'present': attendance.present,
                'notes': attendance.notes,
                'recorded_by': (user_row(attendance.recorded_by)
                                if attendance.recorded_by_id else None),
                'recorded_at': attendance.recorded_at,
            }
        return paginate(request, self, rows, row)


class IntelligenceDistrictCreateView(APIView):
    """District create (web: intelligence.views.district_add) — same
    MANAGE_SOURCES gate, DistrictForm, LGA assignment and
    DISTRICT_CREATED audit."""
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, slug):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence import article_locations
        from intelligence.forms import DistrictForm
        from intelligence.views import _audit
        lga = article_locations.lga_for_slug(slug)
        if lga is None:
            raise NotFound('Unknown LGA.')
        form = form_or_400(DistrictForm(request.data))
        district = form.save(commit=False)
        district.lga = lga
        district.save()
        _audit(request.user, 'DISTRICT_CREATED', 'District', district.pk,
               {'lga_id': lga.pk})
        return Response({
            'id': district.pk, 'name': district.name, 'lga': lga.pk,
            'lga_name': lga.name, 'created_at': district.created_at,
        }, status=status.HTTP_201_CREATED)


class IntelligenceCommunityCreateView(APIView):
    """Community create (web: intelligence.views.community_add) —
    same MANAGE_SOURCES gate, CommunityForm scoped to the LGA (its
    ward/district querysets are the LGA's own, and the model's
    full_clean LGA-consistency check runs exactly as the web view
    runs it), and COMMUNITY_CREATED audit."""
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, slug):
        require_cap(request.user, 'MANAGE_SOURCES')
        from intelligence import article_locations
        from intelligence.forms import CommunityForm
        from intelligence.views import _audit
        lga = article_locations.lga_for_slug(slug)
        if lga is None:
            raise NotFound('Unknown LGA.')
        form = form_or_400(CommunityForm(request.data, lga=lga))
        community = form.save(commit=False)
        community.lga = lga
        try:
            community.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        community.save()
        _audit(request.user, 'COMMUNITY_CREATED', 'Community', community.pk,
               {'lga_id': lga.pk})
        return Response({
            'id': community.pk, 'name': community.name, 'lga': lga.pk,
            'lga_name': lga.name, 'ward': community.ward_id,
            'district': community.district_id,
            'created_at': community.created_at,
        }, status=status.HTTP_201_CREATED)


class InstitutionCreateView(APIView):
    """Institution create (web: story_intelligence.views
    .add_institution) — same story-desk gate (MANAGE_PROMISES,
    capability only, no superuser bypass, as story_capability_required
    applies it), the same InstitutionForm, and the same
    INSTITUTION_ADDED story audit entry."""
    permission_classes = AUTH

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        require_story_cap(request.user, 'MANAGE_PROMISES')
        from story_intelligence.forms import InstitutionForm
        from story_intelligence.services import log_audit
        form = form_or_400(InstitutionForm(request.data))
        institution = form.save()
        log_audit(request.user, 'INSTITUTION_ADDED', 'institution',
                  institution.pk, {'name': institution.name})
        return Response({
            'id': institution.pk, 'name': institution.name,
            'kind': institution.kind,
            'kind_label': institution.get_kind_display(),
            'contact_note': institution.contact_note,
            'notes': institution.notes,
            'created_at': institution.created_at,
        }, status=status.HTTP_201_CREATED)
