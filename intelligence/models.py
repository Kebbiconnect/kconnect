"""Statewide intelligence foundation (Phases 1–5).

Owns the geographic directory extensions, collection-cycle bookkeeping,
source health, the intelligence audit log, the raw-publication intake
written by the collection engine, and — Phase 3 — the relevance /
location / category / cluster records the processing engines attach to
each raw publication. Phase 4 adds the verification desk: the Lane 2
workflow state machine (``desk_state`` on clusters and standalone
items), the append-only ``ReviewDecision`` record of every desk
action, and the manual cluster merge/split exclusions the engines
respect. Phase 5 adds the public project tracker (``Project`` +
milestones + evidence, with the blueprint's integrity rules) and the
promise-candidate queue the commitment detector feeds. Phase 6 adds
the security desk (restricted handling for sensitive-category units,
``SecurityIncident`` records whose casualty figures exist only as
attributed claims, and a redaction-capable working copy on every
unit), the alert engine (``AlertRule`` / ``Alert`` / ``AlertDelivery``
— one record per event, delivered over the site's existing
transports) and template-composed ``Briefing`` records. Phase 7 adds
the public LGA news pages' grounding link (``ArticleLocation`` — the
explicit article↔LGA association the public pages read, never a
render-time guess) and ``FieldReport``, the staff field-reporting
record whose intake is a ``RawPublication`` under the MANUAL field
source, so field material flows through the same processing, desk
and restriction rules as monitored material.
Nothing in this app publishes content directly; the intelligence lane
is human-gated end to end — the desk can only create a newsroom DRAFT,
and publication happens solely through the normal newsroom flow.
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def normalize_alias(text):
    """Case/space/punctuation-insensitive key used for alias matching."""
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


# Lane 2 verification-desk workflow states (Doc 03 §2.5). The engine
# milestones in that chain — COLLECTED (stored at intake) and
# CLASSIFIED (the Phase 3 engines have run: ``processed_at`` is set) —
# are facts about the record, so the desk chain itself starts at
# DISCOVERED and runs through the human states. PUBLISHED is reached
# only when the linked newsroom article actually publishes through the
# normal newsroom flow; the desk never sets it directly.
DESK_STATES = [
    ('DISCOVERED', 'Discovered'),
    ('UNDER_REVIEW', 'Under review'),
    ('VERIFICATION_IN_PROGRESS', 'Verification in progress'),
    ('NEEDS_INFO', 'Needs more evidence'),
    ('VERIFIED', 'Verified'),
    ('DISPUTED', 'Disputed'),
    ('UNVERIFIED', 'Unverified'),
    ('APPROVED', 'Approved — ready'),
    ('PUBLISHED', 'Published'),
    ('REJECTED', 'Rejected'),
    ('DUPLICATE', 'Duplicate'),
    ('ARCHIVED', 'Archived'),
    ('RESTRICTED', 'Restricted — security desk'),
]

DESK_TERMINAL_STATES = ('PUBLISHED', 'ARCHIVED')


class District(models.Model):
    name = models.CharField(max_length=120)
    lga = models.ForeignKey('leadership.LGA', on_delete=models.CASCADE, related_name='districts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['lga__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['lga', 'name'], name='intel_district_lga_name'),
        ]

    def __str__(self):
        return f'{self.name} ({self.lga.name})'


class Community(models.Model):
    name = models.CharField(max_length=160)
    lga = models.ForeignKey('leadership.LGA', on_delete=models.CASCADE, related_name='communities')
    ward = models.ForeignKey('leadership.Ward', null=True, blank=True, on_delete=models.SET_NULL, related_name='communities')
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.SET_NULL, related_name='communities')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['lga__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['lga', 'name'], name='intel_community_lga_name'),
        ]

    def clean(self):
        super().clean()
        if self.district_id and self.lga_id and self.district.lga_id != self.lga_id:
            raise ValidationError('The district belongs to a different LGA.')
        if self.ward_id and self.lga_id and self.ward.lga_id != self.lga_id:
            raise ValidationError('The ward belongs to a different LGA.')

    def __str__(self):
        return f'{self.name} ({self.lga.name})'


class GeoEntity(models.Model):
    """A place-thing that implies a location (institution, school, road...).

    Deliberately separate from story_intelligence.Institution, which is the
    authority record for promises. GeoEntity exists only for geographic
    matching (Doc 03 §2.3).
    """
    KIND = [
        ('INSTITUTION', 'Institution'),
        ('SCHOOL', 'School'),
        ('FACILITY', 'Health facility'),
        ('ROAD', 'Road'),
        ('LANDMARK', 'Landmark'),
        ('ORGANISATION', 'Organisation'),
        ('OTHER', 'Other'),
    ]
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=KIND, default='INSTITUTION')
    lga = models.ForeignKey('leadership.LGA', null=True, blank=True, on_delete=models.SET_NULL, related_name='geo_entities')
    ward = models.ForeignKey('leadership.Ward', null=True, blank=True, on_delete=models.SET_NULL, related_name='geo_entities')
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'geographic entity'
        verbose_name_plural = 'geographic entities'

    def clean(self):
        super().clean()
        if self.ward_id and self.lga_id and self.ward.lga_id != self.lga_id:
            raise ValidationError('The ward belongs to a different LGA.')

    def __str__(self):
        return self.name


class GeoAlias(models.Model):
    """An alternative name/spelling for a directory record.

    Aliases are reviewed before use: only APPROVED aliases resolve. The
    normalised alias text is unique across the directory so one written name
    can never silently point at two different places.
    """
    TARGET_KIND = [
        ('LGA', 'LGA'),
        ('DISTRICT', 'District'),
        ('WARD', 'Ward'),
        ('COMMUNITY', 'Community'),
        ('GEO_ENTITY', 'Geographic entity'),
    ]
    STATUS = [
        ('PENDING', 'Pending review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    alias = models.CharField(max_length=160)
    normalized_alias = models.CharField(max_length=160, unique=True, db_index=True, editable=False)
    target_kind = models.CharField(max_length=20, choices=TARGET_KIND)
    lga = models.ForeignKey('leadership.LGA', null=True, blank=True, on_delete=models.CASCADE, related_name='aliases')
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.CASCADE, related_name='aliases')
    ward = models.ForeignKey('leadership.Ward', null=True, blank=True, on_delete=models.CASCADE, related_name='aliases')
    community = models.ForeignKey(Community, null=True, blank=True, on_delete=models.CASCADE, related_name='aliases')
    geo_entity = models.ForeignKey(GeoEntity, null=True, blank=True, on_delete=models.CASCADE, related_name='aliases')
    status = models.CharField(max_length=12, choices=STATUS, default='PENDING')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['alias']
        verbose_name = 'geographic alias'
        verbose_name_plural = 'geographic aliases'

    _TARGET_FIELDS = {
        'LGA': 'lga', 'DISTRICT': 'district', 'WARD': 'ward',
        'COMMUNITY': 'community', 'GEO_ENTITY': 'geo_entity',
    }

    @property
    def target(self):
        field = self._TARGET_FIELDS.get(self.target_kind)
        return getattr(self, field) if field else None

    def clean(self):
        super().clean()
        chosen = [name for name in self._TARGET_FIELDS.values() if getattr(self, f'{name}_id')]
        expected = self._TARGET_FIELDS.get(self.target_kind)
        if chosen != [expected]:
            raise ValidationError('Set exactly one target, matching the target kind.')

    def save(self, *args, **kwargs):
        self.normalized_alias = normalize_alias(self.alias)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.alias} → {self.target}'


class IntelligenceCategory(models.Model):
    """The blueprint's 22 intelligence categories (seeded by migration).

    Separate from campaigns' newsroom category list, which stays untouched;
    a mapping is applied at publish time in a later phase.
    """
    slug = models.SlugField(max_length=60, unique=True)
    label = models.CharField(max_length=80)
    is_sensitive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['label']
        verbose_name = 'intelligence category'
        verbose_name_plural = 'intelligence categories'

    def __str__(self):
        return self.label


class CollectionControl(models.Model):
    """Singleton pause switch + lease for the collection cycle.

    Mirrors editorial.Control: the lease stops two scheduler invocations
    from running a cycle at the same time.
    """
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=True)
    lease_token = models.CharField(max_length=40, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class CollectionRun(models.Model):
    """One record per collection-cycle invocation — the missed-cycle evidence."""
    TRIGGER = [('SCHEDULED', 'Scheduled'), ('MANUAL', 'Manual')]
    STATUS = [
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('SKIPPED_LEASED', 'Skipped — another cycle holds the lease'),
        ('PAUSED', 'Skipped — collection paused'),
    ]
    trigger = models.CharField(max_length=12, choices=TRIGGER, default='SCHEDULED')
    status = models.CharField(max_length=16, choices=STATUS, default='RUNNING')
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    sources_due = models.PositiveIntegerField(default=0)
    sources_ok = models.PositiveIntegerField(default=0)
    sources_failed = models.PositiveIntegerField(default=0)
    items_new = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-started_at', '-pk']
        indexes = [models.Index(fields=['started_at'], name='intel_run_started_idx')]

    def __str__(self):
        return f'Collection run {self.pk} ({self.status})'


class SourceHealth(models.Model):
    """Per-source collection health for editorial.Source (Doc 04 entity 10)."""
    source = models.OneToOneField('editorial.Source', on_delete=models.CASCADE, related_name='intelligence_health')
    last_cycle_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'source health'
        verbose_name_plural = 'source health'

    def state(self, now=None):
        from datetime import timedelta
        now = now or timezone.now()
        if not self.source.enabled:
            return 'DISABLED'
        if self.consecutive_failures:
            return 'FAILING'
        if self.last_success_at is None:
            return 'NEVER_RUN'
        interval = timedelta(minutes=max(1, self.source.poll_interval_minutes))
        if self.last_success_at + 2 * interval < now:
            return 'STALE'
        return 'OK'

    def __str__(self):
        return f'Health: {self.source.name}'


class EventCluster(models.Model):
    """A group of raw publications reporting the same event (Phase 3).

    Clustering links records; it never deletes or merges the source
    records themselves (Doc 03 §2.4). Clusters are proposed by the
    rule-based clustering engine; the Phase 4 verification desk works
    them through the Lane 2 state machine (``desk_state``), and human
    merges retire a cluster via ``merged_into`` without destroying it.
    """
    STATE = [
        ('OPEN', 'Open'),
        ('MERGED', 'Merged'),
    ]
    CREATED_FROM = [
        ('RULE', 'Rule-based'),
        ('MANUAL', 'Manually'),
    ]
    title = models.CharField(max_length=300)
    category = models.ForeignKey(
        IntelligenceCategory, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='clusters')
    primary_lga = models.ForeignKey(
        'leadership.LGA', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='clusters')
    primary_ward = models.ForeignKey(
        'leadership.Ward', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='clusters')
    primary_district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='clusters')
    primary_community = models.ForeignKey(
        Community, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='clusters')
    primary_geo_entity = models.ForeignKey(
        GeoEntity, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='clusters')
    state = models.CharField(max_length=8, choices=STATE, default='OPEN')
    created_from = models.CharField(max_length=8, choices=CREATED_FROM, default='RULE')
    merged_into = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='merged_from')
    # Phase 4 verification desk (Lane 2): clusters are the natural
    # review unit. ``article`` records what the unit became when a
    # publisher converted it to a newsroom draft; it stays a draft
    # until the normal newsroom flow publishes it.
    desk_state = models.CharField(
        max_length=24, choices=DESK_STATES, default='DISCOVERED', db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    article = models.ForeignKey(
        'campaigns.Campaign', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='intelligence_clusters')
    # Phase 6: the desk's working copy. Prepared from the member
    # reports by a security-desk holder, passages can be redacted out
    # of it, and conversion to a newsroom draft uses it when present.
    # The original member records are never altered by redaction.
    working_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']

    def member_times(self):
        """(earliest, latest) event times across member publications.

        An item's event time is its own published time where it declared
        one, else the time it was discovered.
        """
        times = [
            pub.published_at or pub.discovered_at
            for pub in self.publications.all()
        ]
        if not times:
            return None, None
        return min(times), max(times)

    def __str__(self):
        return self.title


class RawPublication(models.Model):
    """One collected item, stored as found (Phase 2 intake).

    The collection layer's evidence record (Doc 03 §1: evidence before
    narrative): the item keeps its original URL, its source, its own
    publication time and the discovery time in its own row, separate
    from any KPN draft. Connectors write these rows; the Phase 3
    engines then attach a relevance classification, matched locations,
    category suggestions, a near-duplicate link and a cluster — the
    verification workflow is Phase 4, and the collection layer never
    writes a campaigns.Campaign.
    """
    FETCH_STATUS = [
        ('CONTENT', 'Full content fetched'),
        ('FEED_ONLY', 'Feed summary only'),
    ]
    # Blueprint Part C §6 / Doc 03 §2.3 classification vocabulary.
    RELEVANCE = [
        ('CONFIRMED', 'Confirmed Kebbi relevance'),
        ('STRONG_POSSIBLE', 'Strong possible Kebbi relevance'),
        ('UNCERTAIN', 'Uncertain relevance'),
        ('NOT_RELEVANT', 'Not relevant'),
    ]
    source = models.ForeignKey(
        'editorial.Source', on_delete=models.CASCADE, related_name='raw_publications')
    canonical_url = models.URLField(max_length=1000)
    original_url = models.URLField(max_length=1000)
    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True)
    text = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    discovered_at = models.DateTimeField(default=timezone.now)
    fetch_status = models.CharField(max_length=12, choices=FETCH_STATUS, default='CONTENT')
    content_fingerprint = models.CharField(max_length=64, db_index=True)
    raw_metadata = models.JSONField(default=dict, blank=True)
    # Phase 3 processing results (all additive; NULL relevance = the
    # engines have not processed this item yet).
    relevance = models.CharField(
        max_length=16, choices=RELEVANCE, null=True, blank=True, db_index=True)
    relevance_reasons = models.JSONField(default=list, blank=True)
    relevance_manual = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    duplicate_of = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='near_duplicates')
    cluster = models.ForeignKey(
        EventCluster, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='publications')
    # Phase 4 verification desk (Lane 2): an item that belongs to a
    # cluster is reviewed through the cluster; these fields carry the
    # workflow for standalone items only.
    desk_state = models.CharField(
        max_length=24, choices=DESK_STATES, default='DISCOVERED', db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    article = models.ForeignKey(
        'campaigns.Campaign', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='intelligence_publications')
    # Phase 6 working copy (see EventCluster.working_text).
    working_text = models.TextField(blank=True)

    class Meta:
        ordering = ['-discovered_at', '-pk']
        constraints = [
            # URL-level dedupe at ingest (Doc 04 §3.5): the same canonical
            # URL from the same source is stored exactly once; the same
            # URL arriving via two sources is two records, linked later
            # by clustering (Phase 3).
            models.UniqueConstraint(
                fields=['source', 'canonical_url'], name='intel_raw_source_url'),
        ]
        indexes = [
            models.Index(fields=['source', 'published_at'], name='intel_raw_src_pub_idx'),
            models.Index(fields=['fetch_status', '-discovered_at'], name='intel_raw_status_idx'),
            models.Index(fields=['relevance', '-discovered_at'], name='intel_raw_relevance_idx'),
        ]

    @property
    def event_time(self):
        """The item's own publication time, else its discovery time."""
        return self.published_at or self.discovered_at

    def __str__(self):
        return self.title


class PublicationLocation(models.Model):
    """One matched location on a raw publication (Doc 04 entity 15).

    A publication can carry several locations. EXPLICIT rows come from
    a direct name match (Engine A); CONTEXTUAL rows from a secondary
    signal (Engine B — a GeoEntity hit, an ambiguous name, a source's
    home LGA); MANUAL rows are set by staff and are never overwritten
    by the engines. The owning LGA is denormalised onto every row so
    location queries stay simple.
    """
    MATCH_KIND = [
        ('EXPLICIT', 'Explicit mention'),
        ('CONTEXTUAL', 'Contextual signal'),
        ('MEDIA_HINT', 'Media hint'),
        ('MANUAL', 'Manually set'),
    ]
    publication = models.ForeignKey(
        RawPublication, on_delete=models.CASCADE, related_name='locations')
    lga = models.ForeignKey(
        'leadership.LGA', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='publication_locations')
    ward = models.ForeignKey(
        'leadership.Ward', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='publication_locations')
    district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='publication_locations')
    community = models.ForeignKey(
        Community, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='publication_locations')
    geo_entity = models.ForeignKey(
        GeoEntity, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='publication_locations')
    match_kind = models.CharField(max_length=12, choices=MATCH_KIND, default='EXPLICIT')
    matched_text = models.CharField(max_length=160, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        indexes = [
            models.Index(fields=['lga', 'match_kind'], name='intel_loc_lga_kind_idx'),
        ]

    @property
    def target(self):
        for record in (self.community, self.district, self.ward,
                       self.geo_entity, self.lga):
            if record is not None:
                return record
        return None

    @property
    def target_name(self):
        target = self.target
        return str(target) if target is not None else ''

    def __str__(self):
        return f'{self.target_name} on #{self.publication_id}'


class PublicationCategory(models.Model):
    """One rule-based category suggestion on a raw publication.

    Suggestions only (Doc 04 entity 16): the engines propose, the desk
    decides in Phase 4. ``reason`` records the keywords that fired so a
    suggestion is never a bare assertion.
    """
    publication = models.ForeignKey(
        RawPublication, on_delete=models.CASCADE, related_name='category_links')
    category = models.ForeignKey(
        IntelligenceCategory, on_delete=models.CASCADE,
        related_name='publication_links')
    is_primary = models.BooleanField(default=False)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'category__label']
        constraints = [
            models.UniqueConstraint(
                fields=['publication', 'category'], name='intel_pubcat_unique'),
        ]
        verbose_name = 'publication category'
        verbose_name_plural = 'publication categories'

    def __str__(self):
        return f'{self.category} on #{self.publication_id}'


class IntelligenceAudit(models.Model):
    """Append-only audit for intelligence actions (mirrors editorial.Audit).

    Hard rule (story_intelligence precedent): detail JSON never contains
    confidential source text, PII or reporter contact details.
    """
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.action


class ReviewDecision(models.Model):
    """One recorded verification-desk action (Doc 04 entity 18).

    Every desk transition — and every assignment, merge, split and
    draft conversion — writes exactly one of these rows: who acted,
    when, the state before and after, and the note/reason they gave.
    Append-only: there are no edit or delete paths for decisions.
    Exactly one target (a cluster, or a standalone raw publication) is
    set on every row.
    """
    ACTIONS = [
        ('TRIAGE', 'Triaged into review'),
        ('BEGIN_VERIFICATION', 'Verification begun'),
        ('ASSIGN', 'Reviewer assigned'),
        ('REQUEST_INFO', 'More evidence requested'),
        ('RESUME', 'Returned to review'),
        ('VERIFY', 'Verified'),
        ('DISPUTE', 'Disputed'),
        ('REOPEN', 'Reopened for verification'),
        ('APPROVE', 'Approved — ready'),
        ('REJECT', 'Rejected'),
        ('MARK_DUPLICATE', 'Marked duplicate'),
        ('MERGE', 'Clusters merged'),
        ('SPLIT', 'Cluster split'),
        ('CONVERT', 'Converted to newsroom draft'),
        ('PUBLISH', 'Article published via newsroom'),
        ('ARCHIVE', 'Archived'),
        ('RESTRICT', 'Transferred to the security desk'),
        ('RELEASE', 'Released from the security desk'),
        ('MARK_UNVERIFIED', 'Verification withdrawn — unverified'),
    ]
    publication = models.ForeignKey(
        RawPublication, null=True, blank=True, on_delete=models.CASCADE,
        related_name='review_decisions')
    cluster = models.ForeignKey(
        EventCluster, null=True, blank=True, on_delete=models.CASCADE,
        related_name='review_decisions')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    action = models.CharField(max_length=20, choices=ACTIONS)
    from_state = models.CharField(max_length=24, choices=DESK_STATES)
    to_state = models.CharField(max_length=24, choices=DESK_STATES)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(publication__isnull=False, cluster__isnull=True)
                    | models.Q(publication__isnull=True, cluster__isnull=False)),
                name='intel_decision_one_target'),
        ]

    @property
    def unit(self):
        return self.cluster if self.cluster_id else self.publication

    @property
    def from_label(self):
        return dict(DESK_STATES).get(self.from_state, self.from_state)

    @property
    def to_label(self):
        return dict(DESK_STATES).get(self.to_state, self.to_state)

    def __str__(self):
        return f'{self.get_action_display()} on {self.unit}'


class ClusterExclusion(models.Model):
    """A manual cluster separation the engines must respect (Phase 4).

    Written when staff split a cluster: either "this item must not be
    (re)assigned to that cluster" (``cluster`` set) or "these two items
    must not be clustered together" (``other_publication`` set). The
    Phase 3 clustering engine consults these rows before every
    assignment, extending the respect-manual principle: the engine
    never undoes a human split, and a human merge clears the
    exclusions between the merged groups.
    """
    publication = models.ForeignKey(
        RawPublication, on_delete=models.CASCADE,
        related_name='cluster_exclusions')
    other_publication = models.ForeignKey(
        RawPublication, null=True, blank=True, on_delete=models.CASCADE,
        related_name='+')
    cluster = models.ForeignKey(
        EventCluster, null=True, blank=True, on_delete=models.CASCADE,
        related_name='exclusions')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(other_publication__isnull=False, cluster__isnull=True)
                    | models.Q(other_publication__isnull=True, cluster__isnull=False)),
                name='intel_exclusion_one_kind'),
        ]

    def __str__(self):
        if self.cluster_id:
            return f'#{self.publication_id} excluded from cluster #{self.cluster_id}'
        return f'#{self.publication_id} excluded from #{self.other_publication_id}'


# ---------------------------------------------------------------------------
# Phase 5 — Public Project Tracker (Doc 03 §2.6, Doc 04 §3.4, blueprint
# Part G). Integrity rules are structural, not editorial promises:
# contractor, contract amount and the award/commencement/completion
# dates are nullable/blank and are only ever filled when a source
# documents them; the guarded statuses (VERIFIED_ABANDONED,
# COMPLETED_VERIFIED) can be reached only through the service layer
# with the VERIFY_PROJECTS capability, qualifying evidence on record,
# and a verifier who did not report that evidence.
# ---------------------------------------------------------------------------

# The blueprint Part G status vocabulary, verbatim. REPORTED_ABANDONED
# is a claim made by a source; VERIFIED_ABANDONED is a finding made by
# KPN after a verification step — the two are never interchangeable.
PROJECT_STATUSES = [
    ('ANNOUNCED', 'Announced'),
    ('AWARDED_DOCUMENTED', 'Awarded — documented'),
    ('NOT_STARTED', 'Not yet started'),
    ('IN_PROGRESS', 'In progress'),
    ('DELAYED', 'Delayed'),
    ('REPORTED_ABANDONED', 'Reported abandoned'),
    ('VERIFIED_ABANDONED', 'Verified abandoned'),
    ('COMPLETED_AWAITING', 'Completed — awaiting verification'),
    ('COMPLETED_VERIFIED', 'Completed — verified'),
    ('SUSPENDED', 'Suspended'),
    ('DISPUTED', 'Disputed'),
    ('UNKNOWN', 'Unknown'),
]

# Statuses that close a project's story; the desk refuses status
# changes out of them except back to DISPUTED (a completion finding
# can be challenged, never silently rewritten).
PROJECT_TERMINAL_STATUSES = ('VERIFIED_ABANDONED', 'COMPLETED_VERIFIED')

# Blueprint Part G project types (roads, bridges, schools, ...).
PROJECT_CATEGORIES = [
    ('ROAD', 'Road'),
    ('BRIDGE', 'Bridge'),
    ('SCHOOL', 'School'),
    ('HOSPITAL', 'Hospital'),
    ('HEALTH_FACILITY', 'Primary healthcare centre'),
    ('WATER', 'Water project'),
    ('DRAINAGE', 'Drainage system'),
    ('ELECTRICITY', 'Electricity project'),
    ('PUBLIC_BUILDING', 'Public building'),
    ('AGRICULTURE', 'Agricultural facility'),
    ('IRRIGATION', 'Irrigation project'),
    ('MARKET', 'Market'),
    ('YOUTH_FACILITY', 'Youth development facility'),
    ('OTHER', 'Other public infrastructure'),
]

PROJECT_CATEGORY_ICONS = {
    'ROAD': 'fa-road',
    'BRIDGE': 'fa-bridge',
    'SCHOOL': 'fa-school',
    'HOSPITAL': 'fa-hospital',
    'HEALTH_FACILITY': 'fa-house-medical',
    'WATER': 'fa-droplet',
    'DRAINAGE': 'fa-water',
    'ELECTRICITY': 'fa-bolt',
    'PUBLIC_BUILDING': 'fa-building-columns',
    'AGRICULTURE': 'fa-seedling',
    'IRRIGATION': 'fa-faucet-drip',
    'MARKET': 'fa-store',
    'YOUTH_FACILITY': 'fa-users',
    'OTHER': 'fa-clipboard-list',
}

# Evidence kinds that can support a guarded verification finding
# (Doc 03 §2.6: FIELD_INSPECTION or OFFICIAL_RECORD).
PROJECT_VERIFYING_EVIDENCE_KINDS = ('FIELD_INSPECTION', 'OFFICIAL_RECORD')


class ProjectSequence(models.Model):
    """Per-year allocation ledger for permanent Project IDs.

    Mirrors story_intelligence.StorySequence: allocation increments
    ``last_number`` under ``select_for_update()`` inside the creation
    transaction, so two projects registered at the same moment can
    never receive the same KPN-PRJ code.
    """
    year = models.PositiveIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'project ID sequence'
        verbose_name_plural = 'project ID sequences'

    def __str__(self):
        return f'{self.year}: last {self.last_number}'


class Project(models.Model):
    """A tracked public project (blueprint Part G §12).

    Every documented-fact field (contractor, contract amount, award /
    commencement / expected-completion dates) is optional by design:
    it is filled only when a source states it, forms never require it,
    and public pages render it only when present. Nothing on this
    record is ever estimated or inferred.
    """
    project_code = models.CharField(
        max_length=20, unique=True, editable=False,
        help_text='Permanent public reference, allocated at registration '
                  '(KPN-PRJ-YYYY-NNNNN).')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    # Sector shares the Promise Tracker vocabulary so the two public
    # trackers filter the same way; category is the blueprint's
    # project-type list (road, school, water, ...).
    sector = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Thematic sector, using the Promise Tracker vocabulary. '
                  'Leave blank until the project can be classified honestly.')
    category = models.CharField(
        max_length=20, choices=PROJECT_CATEGORIES, default='OTHER')
    institution = models.ForeignKey(
        'story_intelligence.Institution', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='projects',
        help_text='The ministry, agency or authority responsible for the project.')
    lga = models.ForeignKey(
        'leadership.LGA', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='projects')
    ward = models.ForeignKey(
        'leadership.Ward', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='projects')
    district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='projects')
    community = models.ForeignKey(
        Community, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='projects')
    # Documented facts — ONLY when a source states them (blueprint:
    # "Never invent contract amounts, contractor names, dates or
    # project ownership").
    contractor_name = models.CharField(
        max_length=200, blank=True,
        help_text='Only when publicly documented. Leave blank otherwise.')
    contract_amount = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True,
        help_text='Only when documented in a source. Never estimated.')
    award_date = models.DateField(
        null=True, blank=True, help_text='Only when documented.')
    commencement_date = models.DateField(
        null=True, blank=True, help_text='Only when documented.')
    expected_completion_date = models.DateField(
        null=True, blank=True,
        help_text='The completion date the responsible authority '
                  'announced. Leave blank if none was announced.')
    status = models.CharField(
        max_length=24, choices=PROJECT_STATUSES, default='ANNOUNCED',
        db_index=True)
    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    source_url = models.URLField(
        max_length=500, blank=True,
        help_text='The original announcement or source document, where public.')
    # Provenance when the project was proposed from the verification
    # desk: the unit (cluster or standalone item) whose evidence
    # backs the registration.
    source_cluster = models.ForeignKey(
        EventCluster, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='projects')
    source_publication = models.ForeignKey(
        RawPublication, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='projects')
    stories = models.ManyToManyField(
        'campaigns.Campaign', blank=True, related_name='projects',
        help_text='Published stories connected to this project.')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='projects_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']
        indexes = [
            models.Index(fields=['lga', 'status'], name='intel_project_lga_status_idx'),
        ]

    def get_sector_display(self):
        # Sector shares the Promise vocabulary; looked up lazily to
        # keep this app's models import-order independent.
        from story_intelligence.models import Promise
        return dict(Promise.SECTOR_CHOICES).get(self.sector, self.sector)

    @property
    def category_icon(self):
        return PROJECT_CATEGORY_ICONS.get(self.category, 'fa-clipboard-list')

    @property
    def contract_amount_display(self):
        """The documented amount with thousand separators, or '' when
        no amount is documented (never a fabricated figure)."""
        if self.contract_amount is None:
            return ''
        return f'{self.contract_amount:,.2f}'

    def location_label(self):
        parts = []
        for obj in (self.community, self.district, self.ward):
            if obj is not None:
                parts.append(obj.name)
        if self.lga is not None:
            parts.append(f'{self.lga.name} LGA')
        return ', '.join(parts)

    def __str__(self):
        return f'{self.project_code}: {self.title}'


class ProjectMilestone(models.Model):
    """One dated entry in a project's evidence timeline.

    Append-only history (the PromiseUpdate pattern): status changes
    are written as milestone rows with ``status_after`` set by the
    service layer, so the public timeline and the recorded status can
    never disagree about what happened or when.
    """
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name='milestones')
    date = models.DateField()
    title = models.CharField(max_length=250)
    body = models.TextField(blank=True)
    status_after = models.CharField(
        max_length=24, choices=PROJECT_STATUSES, blank=True,
        help_text='The project status after this entry (blank = unchanged).')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at', 'pk']

    def __str__(self):
        return f'{self.project_id}: {self.title}'


class ProjectEvidence(models.Model):
    """One piece of evidence attached to a project (Doc 04 §3.4).

    ``verification_state`` keeps the blueprint's core distinction:
    an ALLEGATION is a claim by a source, DOCUMENTED is a record on
    file, VERIFIED is a finding KPN has checked. Only FIELD_INSPECTION
    and OFFICIAL_RECORD evidence can support the guarded project
    statuses. Evidence is private by default (``is_public=False``);
    reporter identities are never stored on this record.
    """
    KIND = [
        ('ANNOUNCEMENT', 'Announcement'),
        ('AWARD_DOCUMENT', 'Award document'),
        ('PROGRESS_REPORT', 'Progress report'),
        ('COMMUNITY_COMPLAINT', 'Community complaint'),
        ('FIELD_INSPECTION', 'Field inspection'),
        ('OFFICIAL_RECORD', 'Official record'),
        ('OFFICIAL_RESPONSE', 'Official response'),
        ('PHOTO', 'Photo'),
        ('VIDEO', 'Video'),
        ('OTHER', 'Other'),
    ]
    VERIFICATION_STATE = [
        ('ALLEGATION', 'Allegation — a claim by a source'),
        ('DOCUMENTED', 'Documented — a record on file'),
        ('VERIFIED', 'Verified — checked by KPN'),
    ]
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name='evidence')
    milestone = models.ForeignKey(
        ProjectMilestone, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='evidence')
    kind = models.CharField(max_length=20, choices=KIND, default='OTHER')
    title = models.CharField(max_length=250)
    url = models.URLField(max_length=500, blank=True)
    file = models.FileField(
        upload_to='project-evidence/', blank=True, null=True,
        help_text='Photo/video/document evidence, stored on the site media storage.')
    captured_at = models.DateTimeField(null=True, blank=True)
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        help_text='The staff member who captured or filed this evidence. '
                  'Internal only — never shown publicly.')
    is_public = models.BooleanField(
        default=False,
        help_text='Public evidence is listed on the public project page. '
                  'Leave off until disclosure is confirmed safe.')
    verification_state = models.CharField(
        max_length=12, choices=VERIFICATION_STATE, default='ALLEGATION')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        verbose_name = 'project evidence'
        verbose_name_plural = 'project evidence'

    def __str__(self):
        return f'Evidence: {self.title}'


class PromiseCandidate(models.Model):
    """A commitment-like statement flagged by the rules-based detector.

    A candidate is a *lead*, never a promise: it stores the EXACT
    quoted span from the source item (never a paraphrase), the rule
    that fired, and only what the text itself states — an institution
    name only when the text names one, a deadline only as the verbatim
    phrase the text uses. Nothing here is public. A candidate becomes
    a real ``story_intelligence.Promise`` only when a staff member
    confirms it in the candidate queue.
    """
    STATUS = [
        ('PENDING', 'Pending review'),
        ('CONFIRMED', 'Confirmed — promise created'),
        ('DISMISSED', 'Dismissed'),
    ]
    publication = models.ForeignKey(
        RawPublication, on_delete=models.CASCADE,
        related_name='promise_candidates')
    cluster = models.ForeignKey(
        EventCluster, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='promise_candidates')
    quote = models.TextField(
        help_text='The exact sentence from the source item, verbatim.')
    matched_pattern = models.CharField(
        max_length=80,
        help_text='The detector rule that fired (internal label).')
    institution_name = models.CharField(
        max_length=200, blank=True,
        help_text='An institution named in the quoted text itself; '
                  'blank when the text names none.')
    lga = models.ForeignKey(
        'leadership.LGA', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='promise_candidates')
    deadline_text = models.CharField(
        max_length=160, blank=True,
        help_text='A delivery-time phrase exactly as stated in the text '
                  '(e.g. "by December 2027"); never converted to a date '
                  'by the detector.')
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        max_length=12, choices=STATUS, default='PENDING', db_index=True)
    promise = models.ForeignKey(
        'story_intelligence.Promise', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='intelligence_candidates')
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(
        blank=True, help_text='Required when dismissing a candidate.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(fields=['status', '-created_at'],
                         name='intel_candidate_status_idx'),
        ]
        verbose_name = 'promise candidate'
        verbose_name_plural = 'promise candidates'

    def __str__(self):
        return f'Candidate #{self.pk} on item #{self.publication_id}'


# ---------------------------------------------------------------------------
# Phase 6 — Security Desk, Alerts & Briefings (Doc 03 §2.8/§2.10,
# Doc 04 entities 25 + 29, Doc 07 §4, blueprint §14).
#
# Security rules are structural, not editorial promises:
# * There is NO field anywhere on the security path for troop
#   positions, precise locations of vulnerable people, or coordinates:
#   security material is located at LGA level only (an LGA foreign key
#   and a coarse free-text description of the area).
# * Casualty / fatality figures exist ONLY as IncidentClaim rows —
#   each one an attributed claim ("reported by <source>"), never a
#   verified fact. Doc 04's sketch of an ``affected_count`` fact field
#   is deliberately NOT implemented (see the Phase 6 report).
# * Restricted records are excluded from general querysets in the
#   service layer (intelligence/security.py) for anyone without
#   VIEW_SECURITY_DESK; the capability itself is held by exactly two
#   staff titles (owner decision D6, 23 Nov 2026).
# ---------------------------------------------------------------------------


class SecurityIncident(models.Model):
    """A restricted security-desk record (Doc 04 entity 25).

    Created from a sensitive desk unit or manually by a security-desk
    holder. The record itself is never public: public output is only
    ever a verified newsroom article written by an editor. Real-time
    sensitive detail is not stored here at all — ``has_offline_detail``
    records only that such detail was communicated offline, per the
    blueprint's do-not-store list (Doc 07 §4).
    """
    STATUS = [
        ('OPEN', 'Open'),
        ('VERIFIED', 'Verified'),
        ('DISPUTED', 'Disputed'),
        ('CLOSED', 'Closed'),
    ]
    SENSITIVITY = [('RESTRICTED', 'Restricted')]
    title = models.CharField(max_length=300)
    incident_type = models.CharField(max_length=80, blank=True)
    reported_at = models.DateTimeField(default=timezone.now)
    occurred_at = models.DateTimeField(null=True, blank=True)
    # LGA level only — deliberately no ward/district/community/
    # geo-entity fields and no coordinates on the security path.
    lga = models.ForeignKey(
        'leadership.LGA', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='security_incidents')
    location_text = models.CharField(
        max_length=200, blank=True,
        help_text='Coarse area description at LGA level only.')
    status = models.CharField(max_length=12, choices=STATUS, default='OPEN')
    sensitivity = models.CharField(
        max_length=12, choices=SENSITIVITY, default='RESTRICTED')
    has_offline_detail = models.BooleanField(
        default=False,
        help_text='Restricted detail was communicated offline and is '
                  'not stored in this system.')
    working_notes = models.TextField(
        blank=True,
        help_text='The security desk working copy for this incident; '
                  'passages can be redacted before any story work.')
    cluster = models.ForeignKey(
        EventCluster, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='security_incidents')
    publication = models.ForeignKey(
        RawPublication, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='security_incidents')
    article = models.ForeignKey(
        'campaigns.Campaign', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='security_incidents')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-reported_at', '-pk']
        indexes = [
            models.Index(fields=['status', '-reported_at'],
                         name='intel_incident_status_idx'),
        ]

    def __str__(self):
        return self.title


class IncidentClaim(models.Model):
    """One casualty/affected figure, stored ONLY as an attributed claim.

    A claim is what a named source reported — it is never presented,
    in any view, briefing or export, as a verified fact. There is no
    "verified figure" field anywhere in the security path.
    """
    incident = models.ForeignKey(
        SecurityIncident, on_delete=models.CASCADE, related_name='claims')
    label = models.CharField(
        max_length=120,
        help_text='What the figure counts, e.g. "People reported killed".')
    count = models.PositiveIntegerField()
    source_name = models.CharField(max_length=200)
    source_url = models.URLField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    @property
    def attribution(self):
        """The only form in which a figure may be displayed."""
        return f'{self.label}: {self.count} (reported by {self.source_name})'

    def __str__(self):
        return self.attribution


# Alert rule keys (Doc 03 §2.10). One Alert row per event, ever:
# ``dedupe_key`` is unique, and re-firing an event returns the
# existing record without delivering anything again.
ALERT_RULES = [
    ('SECURITY_VERIFIED', 'A restricted/security unit is verified'),
    ('SENSITIVE_CONFIRMED', 'A confirmed-relevance item lands in a sensitive category'),
    ('SOURCE_HEALTH_FAILED', 'A source’s health fails'),
    ('CYCLE_MISSED', 'A collection cycle is missed'),
    ('PROJECT_VERIFIED_ABANDONED', 'A project is verified abandoned'),
    # Not an alert trigger: this row only holds the configuration
    # (staff Telegram chat IDs) for the briefing short summary, so it
    # is edited on the same rules surface. ``alerts.fire`` is never
    # called with this key.
    ('BRIEFING', 'Briefing short summary (Telegram recipients)'),
]

ALERT_CHANNELS = [
    ('DASHBOARD', 'Dashboard'),
    ('EMAIL', 'Email'),
    ('TELEGRAM', 'Telegram'),
]


class AlertRule(models.Model):
    """Per-rule alert configuration (dashboard surface for holders).

    Telegram alerts are delivered ONLY to the chat IDs configured
    here, through the existing BotOutbox machinery — never to the
    public channel (Doc 07 §4). Email goes through the site's existing
    EMAIL_BACKEND. Dashboard alerts go to the holders of
    ``recipient_capability`` as core.Notification rows.
    """
    key = models.CharField(max_length=30, choices=ALERT_RULES, unique=True)
    enabled = models.BooleanField(default=True)
    channels = models.JSONField(default=list, blank=True)
    recipient_capability = models.CharField(max_length=40)
    recipient_emails = models.TextField(
        blank=True,
        help_text='One email address per line (or comma-separated).')
    telegram_chat_ids = models.CharField(
        max_length=300, blank=True,
        help_text='Staff chat IDs, comma-separated. Blank means no '
                  'Telegram delivery — alerts never fall back to the '
                  'public channel.')
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def email_list(self):
        return [part.strip() for part in
                self.recipient_emails.replace(',', '\n').split('\n')
                if part.strip()]

    def chat_id_list(self):
        return [part.strip() for part in self.telegram_chat_ids.split(',')
                if part.strip()]

    def __str__(self):
        return self.get_key_display()


class Alert(models.Model):
    """One alert event (Doc 04 entity 29's dedupe/audit log)."""
    rule = models.ForeignKey(
        AlertRule, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='alerts')
    kind = models.CharField(max_length=30, choices=ALERT_RULES, db_index=True)
    title = models.CharField(max_length=300)
    message = models.TextField()
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    link = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.title


class AlertDelivery(models.Model):
    """One attempted delivery of an alert over one channel.

    A failed delivery is recorded FAILED with its error and is never
    silently retried in a loop. Dashboard deliveries double as the
    per-user read/unread state for the alerts list.
    """
    STATUS = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('SKIPPED', 'Skipped'),
    ]
    alert = models.ForeignKey(
        Alert, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.CharField(max_length=12, choices=ALERT_CHANNELS)
    recipient = models.CharField(
        max_length=200,
        help_text='Username (dashboard), email address, or Telegram chat ID.')
    status = models.CharField(max_length=8, choices=STATUS, default='PENDING')
    error = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['alert', 'channel', 'recipient'],
                name='intel_delivery_unique'),
        ]

    def __str__(self):
        return f'{self.channel} → {self.recipient} ({self.status})'


class Briefing(models.Model):
    """A template-composed briefing over a period (Doc 03 §2.10).

    Composed from real records only — no AI, no invented content. A
    period with no activity produces an honest "nothing recorded"
    briefing. The security section is restricted-safe by construction:
    counts and LGA-level headlines, with any figure phrased as an
    attributed report.
    """
    PERIOD = [('DAILY', 'Daily'), ('WEEKLY', 'Weekly')]
    period_kind = models.CharField(max_length=8, choices=PERIOD)
    period_start = models.DateField()
    period_end = models.DateField()
    title = models.CharField(max_length=200)
    body = models.TextField()
    # Structured sections composed alongside ``body`` (Phase 6 fix):
    # the dashboard page and the HTML email render this data, while
    # ``body`` remains the plain-text rendering. ``telegram_text`` is
    # the short summary exactly as delivered to staff Telegram chats.
    data = models.JSONField(default=dict, blank=True)
    telegram_text = models.TextField(blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    email_status = models.CharField(max_length=300, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['period_kind', 'period_start'],
                name='intel_briefing_period_unique'),
        ]

    def __str__(self):
        return self.title


class BriefingDelivery(models.Model):
    """One attempted delivery of a briefing short summary.

    Mirrors AlertDelivery: a delivery is recorded once per
    (briefing, channel, recipient) and never silently retried, so
    re-running generation or re-clicking the send action can never
    deliver the same briefing twice on the same channel.
    """
    STATUS = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('SKIPPED', 'Skipped'),
    ]
    briefing = models.ForeignKey(
        Briefing, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.CharField(
        max_length=12, choices=ALERT_CHANNELS, default='TELEGRAM')
    recipient = models.CharField(
        max_length=200,
        help_text='Telegram chat ID the short summary was sent to.')
    status = models.CharField(max_length=8, choices=STATUS, default='PENDING')
    error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['briefing', 'channel', 'recipient'],
                name='intel_briefing_delivery_unique'),
        ]

    def __str__(self):
        return (f'{self.briefing_id} · {self.channel} · '
                f'{self.recipient} · {self.status}')


class ArticleLocation(models.Model):
    """An explicit article ↔ LGA association (Phase 7; Doc 04 entity 14/15).

    This is the ONLY grounding the public LGA news pages read: a
    published story appears on an LGA page because a row here says so,
    never because the page guessed from the article's words at render
    time. Rows are written by exactly three paths, recorded in
    ``kind``:

    - CONVERSION — the desk converted an intelligence unit whose own
      evidence records place the story in this LGA;
    - ARTICLE — the article's own stored ``Campaign.lga`` field (set
      in the newsroom, Lane 1 or Lane 2) names this LGA;
    - MANUAL — a staff member tagged the article through the
      dashboard's article-location control.

    One row per (article, LGA): the first writer wins the ``kind``
    attribution, later writers find the row already present.
    """
    KIND = [
        ('CONVERSION', 'From intelligence conversion'),
        ('ARTICLE', 'From the article record'),
        ('MANUAL', 'Tagged by staff'),
    ]
    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.CASCADE,
        related_name='lga_links')
    lga = models.ForeignKey(
        'leadership.LGA', on_delete=models.CASCADE,
        related_name='article_links')
    kind = models.CharField(max_length=12, choices=KIND, default='MANUAL')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['lga__name', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['article', 'lga'], name='intel_article_lga_unique'),
        ]
        indexes = [
            models.Index(fields=['lga', 'kind'], name='intel_artloc_lga_idx'),
        ]

    def __str__(self):
        return f'{self.article_id} @ {self.lga}'


class FieldReport(models.Model):
    """A staff field report (Phase 7; blueprint Part on field reporting).

    The reporter's own record of a submission from the field form.
    Its intake is a :class:`RawPublication` under the MANUAL field
    source (``publication``), so the report is processed, clustered
    and worked at the verification desk exactly like monitored
    material — including the Phase 6 restriction rules, which are
    category-driven and therefore follow the category recorded here.
    The reporter's identity lives only on this staff-side record; it
    is never rendered on any public page.
    """
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='field_reports')
    headline = models.CharField(max_length=300)
    report_text = models.TextField()
    lga = models.ForeignKey(
        'leadership.LGA', on_delete=models.PROTECT,
        related_name='field_reports')
    category = models.ForeignKey(
        IntelligenceCategory, on_delete=models.PROTECT,
        related_name='field_reports')
    occurred_at = models.DateTimeField(
        help_text='When the reported event happened.')
    photo = models.ImageField(
        upload_to='field-reports/', null=True, blank=True,
        help_text='Optional photo evidence, stored via the site media '
                  'handling. Never published as-is.')
    publication = models.OneToOneField(
        RawPublication, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='field_report')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(fields=['reporter', '-created_at'],
                         name='intel_fieldrep_reporter_idx'),
        ]

    def __str__(self):
        return self.headline
