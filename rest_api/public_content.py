"""Public content API completion (2026-11-24).

Read-only endpoints that bring the REST API in line with the current
public website: Promise Tracker, Project Tracker, Future Signal,
Human Impact Files, Story Archive, LGA News, the article Story File,
the expired-opportunities archive, and a health/root endpoint for app
feature detection.

Privacy rules mirror the web exactly:
- only PUBLISHED articles, PUBLISHED story updates and PUBLISHED
  corrections are ever returned;
- evidence is returned only where the record itself is public
  (``EvidenceRecord.is_public`` / ``ProjectEvidence.is_public``);
- reporter names/phones, ``captured_by``, internal notes, consent
  records and audit data are never serialised;
- the intelligence desk/security internals stay out of this API —
  only the two public trackers and the recorded ArticleLocation
  links behind the public LGA pages are read.
"""
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import generics, permissions, serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from campaigns.models import Campaign
from core.models import Opportunity
from intelligence import article_locations
from intelligence import tracking as tracking_service
from intelligence.models import Project, ProjectEvidence, ProjectMilestone
from leadership.models import LGA
from story_intelligence import archive as archive_service
from story_intelligence.models import (
    Claim, Correction, EvidenceRecord, Institution, Promise, PromiseUpdate,
    StoryProfile, StoryUpdate,
)
from story_intelligence.services import story_panel_context

from .pagination import StandardPagination
from .serializers import CampaignSerializer

API_VERSION = '1.1.0'

RESOURCE_GROUPS = {
    'public_content': ['home', 'newsroom', 'opportunities', 'community',
                       'civic', 'advocacy', 'leadership', 'patrons',
                       'impact', 'content', 'gallery'],
    'trackers': ['promises', 'projects', 'signals', 'impact-files',
                 'archive', 'lgas'],
    'member': ['auth', 'profile', 'members', 'reports', 'articles',
               'media', 'notifications', 'devices', 'telegram'],
    'staff_workflows': ['events', 'programs', 'finance', 'discipline',
                        'announcements', 'outreach', 'audit-reports',
                        'community-reports', 'reporters', 'management'],
    'dashboards': ['dashboards', 'media-pipeline', 'operations'],
    'system': ['health', 'schema', 'docs'],
}


# ─── Shared story-file pieces ────────────────────────────────────────────────

class ClaimSerializer(serializers.ModelSerializer):
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = ['id', 'text', 'status', 'status_label', 'source_name',
                  'source_url', 'created_at', 'updated_at']

    def get_status_label(self, obj) -> str:
        return obj.status_label()


class PublicEvidenceSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    file = serializers.FileField(read_only=True, allow_null=True)

    class Meta:
        model = EvidenceRecord
        fields = ['id', 'kind', 'kind_label', 'title', 'url', 'file',
                  'description', 'created_at']


class StoryUpdateSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = StoryUpdate
        fields = ['id', 'kind', 'kind_label', 'title', 'body',
                  'published_at', 'created_at']


class CorrectionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = Correction
        fields = ['id', 'kind', 'kind_label', 'text', 'created_at']


class LinkedStorySerializer(serializers.ModelSerializer):
    image = serializers.ImageField(source='featured_image', read_only=True,
                                   allow_null=True)

    class Meta:
        model = Campaign
        fields = ['id', 'slug', 'title', 'category', 'image', 'published_at',
                  'story_id']


class StoryProfileSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    signal_confidence_label = serializers.CharField(
        source='get_signal_confidence_display', read_only=True)
    signal_category_label = serializers.CharField(
        source='get_signal_category_display', read_only=True)
    impact_category = serializers.SerializerMethodField()
    impact_category_label = serializers.SerializerMethodField()

    class Meta:
        model = StoryProfile
        fields = ['kind', 'kind_label', 'why_it_matters', 'who_is_affected',
                  'what_is_unknown', 'what_to_watch', 'who_contributed',
                  'impact_category', 'impact_category_label',
                  'signal_observation', 'signal_confidence',
                  'signal_confidence_label', 'signal_horizon',
                  'signal_change_condition', 'signal_category',
                  'signal_category_label']

    def get_impact_category(self, obj) -> str:
        return obj.effective_impact_category

    def get_impact_category_label(self, obj) -> str:
        return obj.impact_category_label


def story_file_data(article, request=None):
    """The article's public Story File, built from the same
    ``story_panel_context`` the web article page renders — so the API
    can never show more (or less) than the website. Returns None when
    the article has no story data at all (the web shows no panel)."""
    panel = story_panel_context(article)
    if panel is None:
        return None
    context = {'request': request}
    profile = panel['profile']
    return {
        'story_id': panel['story_id'],
        'profile': (StoryProfileSerializer(profile, context=context).data
                    if profile is not None else None),
        'claims': ClaimSerializer(panel['claims'], many=True,
                                  context=context).data,
        'evidence': PublicEvidenceSerializer(panel['evidence'], many=True,
                                             context=context).data,
        'updates': StoryUpdateSerializer(panel['updates'], many=True,
                                         context=context).data,
        'corrections': CorrectionSerializer(panel['corrections'], many=True,
                                            context=context).data,
        'community_sources': list(panel['community_sources']),
        'related_stories': LinkedStorySerializer(
            panel['related_stories'], many=True, context=context).data,
        'affected_lgas': [
            {'id': lga.pk, 'name': lga.name} for lga in panel['signal_lgas']],
        'impact_related': LinkedStorySerializer(
            panel['impact_related'], many=True, context=context).data,
        'article_locations': [
            {'lga': link.lga_id, 'lga_name': link.lga.name, 'kind': link.kind}
            for link in article.lga_links.select_related('lga').all()],
    }


class CampaignDetailSerializer(CampaignSerializer):
    """Newsroom detail: the campaign fields plus the Story File."""
    story_file = serializers.SerializerMethodField()

    class Meta(CampaignSerializer.Meta):
        fields = CampaignSerializer.Meta.fields + ['story_file']

    def get_story_file(self, obj) -> dict:
        return story_file_data(obj, self.context.get('request'))


# ─── Health / root ───────────────────────────────────────────────────────────

class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({
            'status': 'ok',
            'service': 'kpn-api',
            'api_version': API_VERSION,
            'resources': RESOURCE_GROUPS,
        })


class ApiRootView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({
            'name': 'KPN API',
            'organization': 'Kebbi Progressive Youth Network',
            'api_version': API_VERSION,
            'base_path': '/api/v1/',
            'health': request.build_absolute_uri('health/'),
            'schema': request.build_absolute_uri('schema/'),
            'docs': request.build_absolute_uri('docs/'),
            'resources': RESOURCE_GROUPS,
        })


# ─── Promise Tracker ─────────────────────────────────────────────────────────

class PromiseUpdateSerializer(serializers.ModelSerializer):
    status_after_label = serializers.SerializerMethodField()

    class Meta:
        model = PromiseUpdate
        fields = ['id', 'update_date', 'title', 'body', 'status_after',
                  'status_after_label', 'evidence_title', 'evidence_url',
                  'created_at']

    def get_status_after_label(self, obj) -> str:
        if not obj.status_after:
            return ''
        return Promise.STATUS_LABELS.get(
            obj.status_after, obj.get_status_after_display())


class PromiseSerializer(serializers.ModelSerializer):
    public_code = serializers.CharField(read_only=True)
    status_label = serializers.SerializerMethodField()
    sector_label = serializers.CharField(source='get_sector_display',
                                         read_only=True)
    institution_name = serializers.CharField(source='institution.name',
                                             read_only=True)
    institution_kind = serializers.CharField(source='institution.kind',
                                             read_only=True)
    zone_name = serializers.CharField(source='zone.name', allow_null=True,
                                      read_only=True)
    lga_name = serializers.CharField(source='lga.name', allow_null=True,
                                     read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True,
                                      read_only=True)
    location_label = serializers.SerializerMethodField()
    is_delayed = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    stories = serializers.SerializerMethodField()

    class Meta:
        model = Promise
        fields = ['id', 'public_code', 'title', 'description', 'institution',
                  'institution_name', 'institution_kind', 'announced_by',
                  'announced_on', 'source_name', 'source_url', 'deadline',
                  'status', 'status_label', 'sector', 'sector_label', 'image',
                  'zone', 'zone_name', 'lga', 'lga_name', 'ward', 'ward_name',
                  'location_label', 'is_delayed', 'stories',
                  'created_at', 'updated_at']

    def get_status_label(self, obj) -> str:
        return obj.status_label()

    def get_location_label(self, obj) -> str:
        return obj.location_label()

    def get_is_delayed(self, obj) -> bool:
        return obj.is_delayed()

    def get_image(self, obj) -> str:
        image = obj.display_image
        if not image:
            return None
        try:
            url = image.url
        except ValueError:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url

    def get_stories(self, obj) -> list:
        published = [s for s in obj.stories.all() if s.status == 'PUBLISHED']
        return LinkedStorySerializer(
            published, many=True, context=self.context).data


class PromiseDetailSerializer(PromiseSerializer):
    updates = PromiseUpdateSerializer(many=True, read_only=True)

    class Meta(PromiseSerializer.Meta):
        fields = PromiseSerializer.Meta.fields + ['updates']


def _validated_id(request, name):
    value = request.query_params.get(name)
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class PromiseListView(generics.ListAPIView):
    serializer_class = PromiseSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], parameters=[
        OpenApiParameter(name='q', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='sector', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='status', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='lga', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='institution', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (Promise.objects
                    .select_related('institution', 'zone', 'lga', 'ward')
                    .prefetch_related('stories'))
        params = self.request.query_params
        q = params.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q) |
                Q(institution__name__icontains=q))
        sector = params.get('sector', '')
        if sector in dict(Promise.SECTOR_CHOICES):
            queryset = queryset.filter(sector=sector)
        status = params.get('status', '')
        if status in dict(Promise.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        lga = _validated_id(self.request, 'lga')
        if lga:
            queryset = queryset.filter(lga_id=lga)
        institution = _validated_id(self.request, 'institution')
        if institution:
            queryset = queryset.filter(institution_id=institution)
        return queryset


class PromiseDetailView(generics.RetrieveAPIView):
    serializer_class = PromiseDetailSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (Promise.objects
                .select_related('institution', 'zone', 'lga', 'ward')
                .prefetch_related('stories', 'updates'))


# ─── Project Tracker ─────────────────────────────────────────────────────────

class ProjectMilestoneSerializer(serializers.ModelSerializer):
    status_after_label = serializers.SerializerMethodField()

    class Meta:
        model = ProjectMilestone
        fields = ['id', 'date', 'title', 'body', 'status_after',
                  'status_after_label', 'created_at']

    def get_status_after_label(self, obj) -> str:
        return obj.get_status_after_display() if obj.status_after else ''


class ProjectPublicEvidenceSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    verification_state_label = serializers.CharField(
        source='get_verification_state_display', read_only=True)
    file = serializers.FileField(read_only=True, allow_null=True)

    class Meta:
        model = ProjectEvidence
        # captured_by is internal and never serialised.
        fields = ['id', 'kind', 'kind_label', 'title', 'url', 'file',
                  'captured_at', 'verification_state',
                  'verification_state_label', 'created_at']


class ProjectSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display',
                                         read_only=True)
    category_label = serializers.CharField(source='get_category_display',
                                           read_only=True)
    sector_label = serializers.SerializerMethodField()
    institution_name = serializers.CharField(source='institution.name',
                                             allow_null=True, read_only=True)
    lga_name = serializers.CharField(source='lga.name', allow_null=True,
                                     read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True,
                                      read_only=True)
    district_name = serializers.CharField(source='district.name',
                                          allow_null=True, read_only=True)
    community_name = serializers.CharField(source='community.name',
                                           allow_null=True, read_only=True)
    location_label = serializers.SerializerMethodField()
    contract_amount_display = serializers.CharField(read_only=True)
    stories = serializers.SerializerMethodField()

    class Meta:
        model = Project
        # assigned_officer, created_by and the desk provenance FKs are
        # internal and never serialised. Documented-fact fields render
        # only when a source states them (blank/null otherwise).
        fields = ['id', 'project_code', 'title', 'description', 'sector',
                  'sector_label', 'category', 'category_label', 'institution',
                  'institution_name', 'lga', 'lga_name', 'ward', 'ward_name',
                  'district', 'district_name', 'community', 'community_name',
                  'location_label', 'contractor_name', 'contract_amount',
                  'contract_amount_display', 'award_date',
                  'commencement_date', 'expected_completion_date', 'status',
                  'status_label', 'source_url', 'stories',
                  'created_at', 'updated_at']

    def get_sector_label(self, obj) -> str:
        return obj.get_sector_display()

    def get_location_label(self, obj) -> str:
        return obj.location_label()

    def get_stories(self, obj) -> list:
        published = [s for s in obj.stories.all() if s.status == 'PUBLISHED']
        return LinkedStorySerializer(
            published, many=True, context=self.context).data


class ProjectDetailSerializer(ProjectSerializer):
    milestones = ProjectMilestoneSerializer(many=True, read_only=True)
    evidence = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ['milestones', 'evidence']

    def get_evidence(self, obj) -> list:
        public = obj.evidence.filter(is_public=True)
        return ProjectPublicEvidenceSerializer(
            public, many=True, context=self.context).data


class ProjectListView(generics.ListAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], parameters=[
        OpenApiParameter(name='q', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='status', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='sector', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='lga', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='institution', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (Project.objects
                    .select_related('institution', 'lga', 'ward', 'district',
                                    'community')
                    .prefetch_related('stories'))
        params = self.request.query_params
        q = params.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q) |
                Q(project_code__icontains=q))
        status = params.get('status', '')
        from intelligence.models import PROJECT_STATUSES
        if status in dict(PROJECT_STATUSES):
            queryset = queryset.filter(status=status)
        sector = params.get('sector', '')
        if sector in dict(Promise.SECTOR_CHOICES):
            queryset = queryset.filter(sector=sector)
        lga = _validated_id(self.request, 'lga')
        if lga:
            queryset = queryset.filter(lga_id=lga)
        institution = _validated_id(self.request, 'institution')
        if institution:
            queryset = queryset.filter(institution_id=institution)
        return queryset


class ProjectDetailView(generics.RetrieveAPIView):
    serializer_class = ProjectDetailSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (Project.objects
                .select_related('institution', 'lga', 'ward', 'district',
                                'community')
                .prefetch_related('stories', 'milestones', 'evidence'))


# ─── Future Signal ───────────────────────────────────────────────────────────

def claim_groups_for(article):
    """The web's epistemic separation, as data: claims grouped by
    status into three never-blended groups. Analyst judgment and
    projections are the editor's framed texts, returned separately."""
    claims = list(article.claims.all())
    by_status = {}
    for claim in claims:
        by_status.setdefault(claim.status, []).append(claim)
    return {
        'confirmed_facts': ClaimSerializer(
            by_status.get('CONFIRMED', []), many=True).data,
        'estimates_and_official_statements': ClaimSerializer(
            by_status.get('OFFICIAL_STATEMENT', []), many=True).data,
        'still_being_established': ClaimSerializer(
            [c for status in ('DEVELOPING', 'DISPUTED', 'NOT_ESTABLISHED')
             for c in by_status.get(status, [])], many=True).data,
    }


class SignalSerializer(CampaignSerializer):
    story_kind = serializers.CharField(source='story_profile.kind',
                                       read_only=True)
    signal_category = serializers.CharField(
        source='story_profile.signal_category', read_only=True)
    signal_category_label = serializers.CharField(
        source='story_profile.get_signal_category_display', read_only=True)
    signal_confidence = serializers.CharField(
        source='story_profile.signal_confidence', read_only=True)
    signal_confidence_label = serializers.CharField(
        source='story_profile.get_signal_confidence_display', read_only=True)
    signal_observation = serializers.CharField(
        source='story_profile.signal_observation', read_only=True)
    signal_horizon = serializers.CharField(
        source='story_profile.signal_horizon', read_only=True)

    class Meta(CampaignSerializer.Meta):
        fields = CampaignSerializer.Meta.fields + [
            'story_kind', 'signal_category', 'signal_category_label',
            'signal_confidence', 'signal_confidence_label',
            'signal_observation', 'signal_horizon']


class SignalDetailSerializer(SignalSerializer):
    story_file = serializers.SerializerMethodField()
    claim_groups = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta(SignalSerializer.Meta):
        fields = SignalSerializer.Meta.fields + [
            'story_file', 'claim_groups', 'questions']

    def get_story_file(self, obj) -> dict:
        return story_file_data(obj, self.context.get('request'))

    def get_claim_groups(self, obj) -> dict:
        return claim_groups_for(obj)

    def get_questions(self, obj) -> dict:
        profile = obj.story_profile
        return {
            'what_we_are_seeing': profile.signal_observation,
            'what_evidence_is_available': (
                'See claim_groups and story_file.evidence.'),
            'who_could_be_affected': profile.who_is_affected,
            'why_it_matters_to_kebbi': profile.why_it_matters,
            'analyst_judgment': profile.why_it_matters,
            'what_remains_uncertain': profile.what_is_unknown,
            'what_would_change_this_assessment':
                profile.signal_change_condition,
            'what_kpn_is_watching_next': profile.what_to_watch,
            'projections': {
                'forward_looking': profile.what_to_watch,
                'horizon': profile.signal_horizon,
            },
        }


def _signal_queryset():
    return (Campaign.objects
            .filter(status='PUBLISHED', story_profile__kind='SIGNAL')
            .select_related('author', 'lga', 'ward', 'story_profile')
            .order_by('-published_at', '-created_at'))


class SignalListView(generics.ListAPIView):
    serializer_class = SignalSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], parameters=[
        OpenApiParameter(name='theme', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='confidence', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = _signal_queryset()
        theme = self.request.query_params.get('theme', '')
        if theme in dict(StoryProfile.SIGNAL_CATEGORY_CHOICES):
            queryset = queryset.filter(story_profile__signal_category=theme)
        confidence = self.request.query_params.get('confidence', '')
        if confidence in dict(StoryProfile.SIGNAL_CONFIDENCE_CHOICES):
            queryset = queryset.filter(
                story_profile__signal_confidence=confidence)
        return queryset


class SignalDetailView(generics.RetrieveAPIView):
    serializer_class = SignalDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return _signal_queryset()


# ─── Human Impact Files ──────────────────────────────────────────────────────

class ImpactFileSerializer(CampaignSerializer):
    story_kind = serializers.CharField(source='story_profile.kind',
                                       read_only=True)
    impact_category = serializers.SerializerMethodField()
    impact_category_label = serializers.SerializerMethodField()
    update_count = serializers.SerializerMethodField()

    class Meta(CampaignSerializer.Meta):
        fields = CampaignSerializer.Meta.fields + [
            'story_kind', 'impact_category', 'impact_category_label',
            'update_count']

    def get_impact_category(self, obj) -> str:
        return obj.story_profile.effective_impact_category

    def get_impact_category_label(self, obj) -> str:
        return obj.story_profile.impact_category_label

    def get_update_count(self, obj) -> int:
        return obj.story_updates.filter(status='PUBLISHED').count()


class ImpactFileDetailSerializer(ImpactFileSerializer):
    story_file = serializers.SerializerMethodField()
    six_parts = serializers.SerializerMethodField()

    class Meta(ImpactFileSerializer.Meta):
        fields = ImpactFileSerializer.Meta.fields + ['story_file', 'six_parts']

    def get_story_file(self, obj) -> dict:
        return story_file_data(obj, self.context.get('request'))

    def get_six_parts(self, obj) -> dict:
        profile = obj.story_profile
        panel = story_panel_context(obj) or {}
        context = {'request': self.context.get('request')}
        return {
            'who_is_affected': profile.who_is_affected,
            'their_situation': profile.why_it_matters,
            'who_contributed_to_the_change': profile.who_contributed,
            'what_the_evidence_shows': {
                'claims': ClaimSerializer(
                    panel.get('claims', []), many=True,
                    context=context).data,
                'evidence': PublicEvidenceSerializer(
                    panel.get('evidence', []), many=True,
                    context=context).data,
            },
            'how_the_story_developed': StoryUpdateSerializer(
                panel.get('updates', []), many=True, context=context).data,
            'what_remains': {
                'what_is_unknown': profile.what_is_unknown,
                'what_to_watch': profile.what_to_watch,
            },
        }


def _impact_queryset():
    return (Campaign.objects
            .filter(status='PUBLISHED', story_profile__kind='IMPACT')
            .select_related('author', 'lga', 'ward', 'story_profile')
            .order_by('-published_at', '-created_at'))


class ImpactFileListView(generics.ListAPIView):
    serializer_class = ImpactFileSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], parameters=[
        OpenApiParameter(name='category', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = _impact_queryset()
        category = self.request.query_params.get('category', '')
        if category in dict(StoryProfile.IMPACT_CATEGORY_CHOICES):
            # D-10: the effective theme (editor label, else the news
            # category mapping) decides browsing — filter in Python,
            # exactly like the web hub.
            ids = [s.pk for s in queryset
                   if s.story_profile.effective_impact_category == category]
            queryset = queryset.filter(pk__in=ids)
        return queryset


class ImpactFileDetailView(generics.RetrieveAPIView):
    serializer_class = ImpactFileDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return _impact_queryset()


# ─── Story Archive ───────────────────────────────────────────────────────────

class ArchiveView(APIView):
    """The public Story Archive as data: the same query layer the web
    archive uses (``story_intelligence.archive``), so results, filters
    and privacy boundaries are identical. An exact Story ID query
    returns the matching record directly (the web 302-redirects)."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], responses={200: OpenApiTypes.OBJECT}, parameters=[
        OpenApiParameter(name='q', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='type', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='topic', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='category', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='date_from', type=OpenApiTypes.DATE,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='date_to', type=OpenApiTypes.DATE,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='lga', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='zone', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='ward', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name='institution', type=OpenApiTypes.INT,
                         location=OpenApiParameter.QUERY, required=False),
    ])
    def get(self, request):
        params = archive_service.parse_archive_params(request)
        q = params['q']

        if q and archive_service.STORY_ID_RE.match(q.upper()):
            article = Campaign.objects.filter(
                status='PUBLISHED', story_id=q.upper()).first()
            if article is not None:
                archive_service._enrich_stories([article])
                return Response({
                    'match_type': 'story_id',
                    'story': self._story_row(article, request),
                })

        browsing = (not q and params['type'] == 'all'
                    and not archive_service.has_active_filters(params))
        show_updates = params['type'] in ('all', 'update') and not browsing
        show_promises = params['type'] in ('all', 'promise') and not browsing
        show_stories = params['type'] in ('all', 'story')

        paginator = StandardPagination()
        data = {
            'match_type': 'search',
            'params': {
                'q': q, 'type': params['type'], 'topic': params['topic'],
                'category': params['category'],
                'date_from': (params['date_from'].isoformat()
                              if params['date_from'] else None),
                'date_to': (params['date_to'].isoformat()
                            if params['date_to'] else None),
                'zone': params['zone'], 'lga': params['lga'],
                'ward': params['ward'], 'institution': params['institution'],
            },
            'counts': archive_service._record_counts(),
            'stories': [], 'stories_total': 0,
            'updates': [], 'updates_total': 0,
            'promises': [], 'promises_total': 0,
        }
        if show_stories:
            queryset = archive_service.story_queryset(params)
            page = paginator.paginate_queryset(queryset, request, view=self)
            archive_service._enrich_stories(list(page))
            data['stories'] = [self._story_row(a, request) for a in page]
            data['stories_total'] = queryset.count()
        if show_updates:
            queryset = archive_service.update_queryset(params)
            page = paginator.paginate_queryset(queryset, request, view=self)
            archive_service._enrich_updates(list(page))
            data['updates'] = [self._update_row(u, request) for u in page]
            data['updates_total'] = queryset.count()
        if show_promises:
            queryset = archive_service.promise_queryset(params)
            page = paginator.paginate_queryset(queryset, request, view=self)
            archive_service._enrich_promises(list(page))
            data['promises'] = PromiseSerializer(
                page, many=True, context={'request': request}).data
            data['promises_total'] = queryset.count()
        return Response(data)

    def _story_row(self, article, request):
        row = CampaignSerializer(article, context={'request': request}).data
        if article.correction_count:
            record_status = 'Corrected'
        elif article.update_count:
            record_status = 'Updated'
        else:
            record_status = 'Published'
        row['section'] = {'kind': article.section_kind,
                          'label': article.section_label}
        row['record_status'] = record_status
        row['update_count'] = article.update_count
        row['correction_count'] = article.correction_count
        row['linked_promises'] = [
            {'id': p.pk, 'public_code': p.public_code, 'title': p.title}
            for p in article.linked_promises]
        row['related_stories'] = LinkedStorySerializer(
            article.related_stories, many=True,
            context={'request': request}).data
        return row

    def _update_row(self, update, request):
        row = StoryUpdateSerializer(update, context={'request': request}).data
        row['article'] = {'id': update.article_id,
                          'slug': update.article.slug,
                          'title': update.article.title,
                          'story_id': update.article.story_id}
        row['section'] = {'kind': update.section_kind,
                          'label': update.section_label}
        row['record_status'] = ('Corrected' if update.correction_count
                                else 'Published')
        row['correction_count'] = update.correction_count
        return row


# ─── LGA News ────────────────────────────────────────────────────────────────

class LgaNewsIndexView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], operation_id='lga_news_index',
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        story_counts = article_locations.story_counts_by_lga()
        promise_counts = tracking_service.promise_counts_by_lga()
        project_counts = tracking_service.project_counts_by_lga()
        rows = []
        for lga in LGA.objects.select_related('zone').order_by(
                'zone__name', 'name'):
            promises = promise_counts.get(
                lga.pk, tracking_service.empty_counts())
            projects = project_counts.get(
                lga.pk, tracking_service.empty_project_counts())
            rows.append({
                'lga': lga.pk,
                'name': lga.name,
                'zone': lga.zone_id,
                'zone_name': lga.zone.name,
                'slug': article_locations.lga_slug(lga),
                'stories': story_counts.get(lga.pk, 0),
                'promises': promises['tracked'],
                'projects': projects['pj_tracked'],
            })
        return Response({
            'results': rows,
            'totals': {
                'lgas': len(rows),
                'stories': sum(r['stories'] for r in rows),
                'promises': sum(r['promises'] for r in rows),
                'projects': sum(r['projects'] for r in rows),
            },
        })


class LgaNewsDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], operation_id='lga_news_detail',
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request, slug):
        lga = article_locations.lga_for_slug(slug)
        if lga is None:
            raise NotFound('Unknown LGA.')
        from intelligence.models import Community, District
        from leadership.models import Ward
        promise_counts = tracking_service.promise_counts_by_lga().get(
            lga.pk, tracking_service.empty_counts())
        project_counts = tracking_service.project_counts_by_lga().get(
            lga.pk, tracking_service.empty_project_counts())
        stories_qs = article_locations.published_stories(lga)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(stories_qs, request, view=self)
        promises = (Promise.objects.filter(lga=lga)
                    .select_related('institution', 'zone', 'lga', 'ward')
                    .prefetch_related('stories')
                    .order_by('-created_at', '-pk')[:4])
        projects = (Project.objects.filter(lga=lga)
                    .select_related('institution', 'lga', 'ward', 'district',
                                    'community')
                    .prefetch_related('stories')
                    .order_by('-updated_at', '-pk')[:4])
        return Response({
            'lga': {
                'id': lga.pk, 'name': lga.name, 'zone': lga.zone_id,
                'zone_name': lga.zone.name, 'slug': slug,
                'district_count': District.objects.filter(lga=lga).count(),
                'community_count': Community.objects.filter(lga=lga).count(),
                'ward_count': Ward.objects.filter(lga=lga).count(),
            },
            'story_total': stories_qs.count(),
            'stories': CampaignSerializer(
                page, many=True, context={'request': request}).data,
            'promise_counts': promise_counts,
            'project_counts': project_counts,
            'recent_promises': PromiseSerializer(
                promises, many=True, context={'request': request}).data,
            'recent_projects': ProjectSerializer(
                projects, many=True, context={'request': request}).data,
        })


# ─── Expired opportunities archive ───────────────────────────────────────────

class OpportunityArchiveListView(generics.ListAPIView):
    """The public expired-opportunities archive: CLOSED listings only,
    mirroring the web archive page."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], parameters=[
        OpenApiParameter(name='category', type=OpenApiTypes.STR,
                         location=OpenApiParameter.QUERY, required=False),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_serializer_class(self):
        from .serializers import OpportunitySerializer
        return OpportunitySerializer

    def get_queryset(self):
        queryset = Opportunity.objects.filter(status='CLOSED')
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        return queryset.order_by('-deadline', '-created_at')
