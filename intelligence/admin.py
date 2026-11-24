from django.contrib import admin

from .models import (
    Alert, AlertDelivery, AlertRule, ArticleLocation, Briefing,
    BriefingDelivery, ClusterExclusion,
    CollectionControl, CollectionRun, Community, District, EventCluster,
    FieldReport, GeoAlias, GeoEntity, IncidentClaim, IntelligenceAudit,
    IntelligenceCategory, Project, ProjectEvidence, ProjectMilestone,
    ProjectSequence, PromiseCandidate, PublicationCategory,
    PublicationLocation, RawPublication, ReviewDecision, SecurityIncident,
    SourceHealth,
)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name', 'lga')
    list_filter = ('lga',)
    search_fields = ('name',)


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'lga', 'ward', 'district')
    list_filter = ('lga',)
    search_fields = ('name',)


@admin.register(GeoEntity)
class GeoEntityAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'lga', 'ward')
    list_filter = ('kind', 'lga')
    search_fields = ('name',)


@admin.register(GeoAlias)
class GeoAliasAdmin(admin.ModelAdmin):
    list_display = ('alias', 'target_kind', 'status')
    list_filter = ('target_kind', 'status')
    search_fields = ('alias',)


@admin.register(IntelligenceCategory)
class IntelligenceCategoryAdmin(admin.ModelAdmin):
    list_display = ('label', 'slug', 'is_sensitive')


@admin.register(SourceHealth)
class SourceHealthAdmin(admin.ModelAdmin):
    list_display = ('source', 'last_cycle_at', 'last_success_at', 'consecutive_failures')


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = ('pk', 'trigger', 'status', 'started_at', 'finished_at',
                    'sources_due', 'sources_ok', 'sources_failed', 'items_new')
    list_filter = ('status', 'trigger')


@admin.register(CollectionControl)
class CollectionControlAdmin(admin.ModelAdmin):
    list_display = ('id', 'enabled', 'lease_until', 'updated_at')


@admin.register(RawPublication)
class RawPublicationAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'fetch_status', 'relevance',
                    'published_at', 'discovered_at')
    list_filter = ('fetch_status', 'relevance', 'source')
    search_fields = ('title', 'canonical_url')
    readonly_fields = ('source', 'canonical_url', 'original_url', 'title',
                       'summary', 'text', 'published_at', 'discovered_at',
                       'fetch_status', 'content_fingerprint', 'raw_metadata')


@admin.register(PublicationLocation)
class PublicationLocationAdmin(admin.ModelAdmin):
    list_display = ('publication', 'target_name', 'match_kind', 'matched_text')
    list_filter = ('match_kind', 'lga')


@admin.register(PublicationCategory)
class PublicationCategoryAdmin(admin.ModelAdmin):
    list_display = ('publication', 'category', 'is_primary')
    list_filter = ('category', 'is_primary')


@admin.register(EventCluster)
class EventClusterAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'primary_lga', 'state', 'created_from', 'updated_at')
    list_filter = ('state', 'category', 'primary_lga')
    search_fields = ('title',)


@admin.register(IntelligenceAudit)
class IntelligenceAuditAdmin(admin.ModelAdmin):
    list_display = ('action', 'target_type', 'target_id', 'actor', 'created_at')
    list_filter = ('action',)


@admin.register(ReviewDecision)
class ReviewDecisionAdmin(admin.ModelAdmin):
    list_display = ('action', 'from_state', 'to_state', 'actor', 'created_at')
    list_filter = ('action',)
    readonly_fields = ('publication', 'cluster', 'actor', 'action',
                       'from_state', 'to_state', 'note', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClusterExclusion)
class ClusterExclusionAdmin(admin.ModelAdmin):
    list_display = ('publication', 'other_publication', 'cluster',
                    'created_by', 'created_at')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_code', 'title', 'status', 'category', 'lga',
                    'institution', 'updated_at')
    list_filter = ('status', 'category', 'sector', 'lga')
    search_fields = ('title', 'project_code', 'contractor_name')
    readonly_fields = ('project_code', 'created_at', 'updated_at')


@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = ('project', 'date', 'title', 'status_after', 'recorded_by')
    list_filter = ('status_after',)


@admin.register(ProjectEvidence)
class ProjectEvidenceAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'kind', 'verification_state',
                    'is_public', 'captured_by')
    list_filter = ('kind', 'verification_state', 'is_public')


@admin.register(ProjectSequence)
class ProjectSequenceAdmin(admin.ModelAdmin):
    list_display = ('year', 'last_number')
    readonly_fields = ('year', 'last_number')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PromiseCandidate)
class PromiseCandidateAdmin(admin.ModelAdmin):
    list_display = ('pk', 'publication', 'institution_name', 'status',
                    'created_at', 'decided_by')
    list_filter = ('status',)
    readonly_fields = ('publication', 'cluster', 'quote', 'matched_pattern',
                       'institution_name', 'lga', 'deadline_text',
                       'dedupe_key', 'created_at')

    def has_add_permission(self, request):
        return False


# ---------------------------------------------------------------------------
# Phase 6 — security desk, alerts, briefings. Incidents and claims are
# managed on the security desk (capability-gated); admin access here
# is a break-glass surface only. Alerts, deliveries and briefings are
# system records: read-only in admin.
# ---------------------------------------------------------------------------

@admin.register(SecurityIncident)
class SecurityIncidentAdmin(admin.ModelAdmin):
    list_display = ('pk', 'title', 'status', 'lga', 'reported_at', 'created_by')
    list_filter = ('status',)


@admin.register(IncidentClaim)
class IncidentClaimAdmin(admin.ModelAdmin):
    list_display = ('pk', 'incident', 'label', 'count', 'source_name', 'created_at')
    readonly_fields = ('incident', 'label', 'count', 'source_name',
                       'source_url', 'created_by', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ('key', 'enabled', 'recipient_capability', 'updated_at')


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('pk', 'kind', 'title', 'created_at')
    readonly_fields = ('rule', 'kind', 'title', 'message', 'target_type',
                       'target_id', 'link', 'dedupe_key', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(AlertDelivery)
class AlertDeliveryAdmin(admin.ModelAdmin):
    list_display = ('pk', 'alert', 'channel', 'recipient', 'status', 'created_at')
    list_filter = ('channel', 'status')
    readonly_fields = ('alert', 'channel', 'recipient', 'status', 'error',
                       'is_read', 'read_at', 'sent_at', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(Briefing)
class BriefingAdmin(admin.ModelAdmin):
    list_display = ('pk', 'period_kind', 'period_start', 'period_end',
                    'title', 'created_at')
    readonly_fields = ('period_kind', 'period_start', 'period_end', 'title',
                       'body', 'data', 'telegram_text', 'generated_by',
                       'email_status', 'emailed_at',
                       'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False


@admin.register(ArticleLocation)
class ArticleLocationAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'lga', 'kind', 'created_by',
                    'created_at')
    list_filter = ('kind', 'lga')
    readonly_fields = ('created_at',)


@admin.register(FieldReport)
class FieldReportAdmin(admin.ModelAdmin):
    list_display = ('pk', 'headline', 'reporter', 'lga', 'category',
                    'occurred_at', 'created_at')
    list_filter = ('lga', 'category')
    readonly_fields = ('publication', 'created_at')


@admin.register(BriefingDelivery)
class BriefingDeliveryAdmin(admin.ModelAdmin):
    list_display = ('pk', 'briefing', 'channel', 'recipient', 'status',
                    'created_at')
    list_filter = ('channel', 'status')
    readonly_fields = ('briefing', 'channel', 'recipient', 'status',
                       'error', 'sent_at', 'created_at')

    def has_add_permission(self, request):
        return False
