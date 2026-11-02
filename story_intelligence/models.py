"""KPN Media — Story Intelligence models (Phase 1: Living Stories + Truth Layers).

These models are the shared spine described in the architectural
assessment (§7.5): they hang off the existing newsroom article record
(`campaigns.Campaign`) and never replace it. All foreign keys toward the
article use PROTECT so an article with story records cannot be destroyed
through the ORM while its history exists; such articles are archived
instead (see campaigns.services).

Privacy rule: ConsentRecord and StoryAudit are internal editorial records.
No public template or API serializer exposes them, and audit/correction
text must never copy sensitive material (enforced in services).
"""
from django.conf import settings
from django.db import models


class StorySequence(models.Model):
    """Per-year allocation ledger for permanent Story IDs.

    One row per year. Allocation increments `last_number` under
    `select_for_update()` inside the publish transaction, so concurrent
    publishes can never receive the same number.
    """

    year = models.PositiveIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Story ID sequence'
        verbose_name_plural = 'Story ID sequences'

    def __str__(self):
        return f'{self.year}: last {self.last_number}'


class StoryProfile(models.Model):
    """Reader-facing story context for one article (Living Stories).

    Phase 4 (v2.8.0) activates the SIGNAL and IMPACT kinds:
    - SIGNAL (Future Signal): an evidence-led editorial analysis. The
      signal_* fields frame it as analysis — never as established fact
      or prediction — and `related_stories` links it to the published
      stories it is based on.
    - IMPACT (Human Impact File): a story about identifiable people
      carries `features_identifiable_people`; while that flag is set,
      publication is blocked in the service layer until a
      ConsentRecord is on file (see services.consent_block_reason).
    """

    KIND_CHOICES = [
        ('NEWS', 'News'),
        ('SIGNAL', 'Future Signal'),
        ('IMPACT', 'Human Impact'),
    ]

    # Plain-language confidence framing for Future Signal pieces: how
    # strong the EVIDENCE behind the analysis is. Deliberately not a
    # probability and never worded as a prediction.
    SIGNAL_CONFIDENCE_CHOICES = [
        ('EMERGING', 'Emerging — early signs; evidence is still limited'),
        ('DEVELOPING', 'Developing — the evidence is growing'),
        ('ESTABLISHED', 'Established — supported by evidence from several sources'),
    ]

    article = models.OneToOneField(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='story_profile')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='NEWS')
    why_it_matters = models.TextField(blank=True)
    who_is_affected = models.TextField(blank=True)
    what_is_unknown = models.TextField(blank=True)
    what_to_watch = models.TextField(blank=True)
    # ── Phase 4: Future Signal framing (kind == 'SIGNAL') ──
    signal_observation = models.TextField(
        blank=True,
        help_text='Future Signal: what KPN is seeing — the development '
                  'or trend this analysis is about.')
    signal_confidence = models.CharField(
        max_length=20, choices=SIGNAL_CONFIDENCE_CHOICES, blank=True, default='',
        help_text='Future Signal: how strong the evidence behind this '
                  'analysis is. This is analysis, not established fact.')
    signal_horizon = models.CharField(
        max_length=200, blank=True,
        help_text='Future Signal: the period this analysis looks at, '
                  'e.g. "the next farming season".')
    signal_change_condition = models.TextField(
        blank=True,
        help_text='Future Signal: what would change this assessment.')
    related_stories = models.ManyToManyField(
        'campaigns.Campaign', blank=True, related_name='analysed_by_signals',
        help_text='Published stories this Future Signal analysis is based on.')
    # ── Phase 4: Human Impact framing (kind == 'IMPACT') ──
    features_identifiable_people = models.BooleanField(
        default=False,
        help_text='Human Impact: tick when real people in this story can '
                  'be identified. While ticked, the story cannot be '
                  'published until a consent record is on file.')
    impact_story = models.ForeignKey(
        'core.ImpactStory', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='story_profiles',
        help_text='Optional link to the related KPN impact record.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def has_content(self):
        return any([self.why_it_matters.strip(), self.who_is_affected.strip(),
                    self.what_is_unknown.strip(), self.what_to_watch.strip(),
                    self.signal_observation.strip(),
                    self.signal_change_condition.strip()])

    def signal_has_evidence(self):
        """A Future Signal must rest on evidence: linked stories it
        analyses, and/or the story's own claims or evidence records.
        The desk flags a signal with none of these (editorial warning)."""
        if self.related_stories.exists():
            return True
        return (self.article.claims.exists()
                or self.article.evidence_records.exists())

    def consent_on_file(self):
        """True when a live (not withdrawn) consent record exists for
        this story. A record with basis NOT_REQUIRED counts: an editor
        has recorded why consent is not required for this material."""
        return self.article.consent_records.filter(withdrawn=False).exists()

    def __str__(self):
        return f'Story profile for {self.article_id}'


class StoryUpdate(models.Model):
    """A chronological development attached to a story.

    Published updates are historical records: they are corrected through
    Correction records, not silently rewritten.
    """

    KIND_CHOICES = [
        ('DEVELOPMENT', 'Development'),
        ('FOLLOW_UP', 'Follow-up report'),
        ('OFFICIAL_RESPONSE', 'Official response'),
        ('COMMUNITY_UPDATE', 'Community update'),
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
    ]

    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='story_updates')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='DEVELOPMENT')
    title = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='story_updates')
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.article_id}: {self.title}'


class Claim(models.Model):
    """One checkable claim in a story, with its Truth Layers status.

    OFFICIAL_STATEMENT is deliberately distinct from CONFIRMED: an
    authority saying something is not the same as KPN verifying it.
    """

    STATUS_CHOICES = [
        ('CONFIRMED', 'Confirmed'),
        ('OFFICIAL_STATEMENT', 'Official statement'),
        ('DEVELOPING', 'Developing'),
        ('DISPUTED', 'Disputed'),
        ('NOT_ESTABLISHED', 'Not established'),
    ]
    # Plain-language reader labels: never present an official statement
    # as independently verified.
    STATUS_LABELS = {
        'CONFIRMED': 'Confirmed by KPN',
        'OFFICIAL_STATEMENT': 'Official statement — not independently verified by KPN',
        'DEVELOPING': 'Still developing — KPN is following this up',
        'DISPUTED': 'Disputed — sources disagree',
        'NOT_ESTABLISHED': 'Not yet established',
    }

    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='claims')
    update = models.ForeignKey(
        StoryUpdate, on_delete=models.PROTECT,
        null=True, blank=True, related_name='claims')
    text = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DEVELOPING')
    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    noted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='claims_noted')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def __str__(self):
        return f'Claim ({self.status}) on article {self.article_id}'


class EvidenceRecord(models.Model):
    """A piece of evidence supporting a story or a specific claim."""

    KIND_CHOICES = [
        ('SOURCE_LINK', 'Source link'),
        ('DOCUMENT', 'Document'),
        ('PHOTO', 'Photo'),
        ('VIDEO', 'Video'),
        ('OFFICIAL_RECORD', 'Official record'),
    ]

    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='evidence_records')
    claim = models.ForeignKey(
        Claim, on_delete=models.PROTECT,
        null=True, blank=True, related_name='evidence_records')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='SOURCE_LINK')
    title = models.CharField(max_length=200)
    url = models.URLField(max_length=500, blank=True)
    file = models.FileField(upload_to='story-evidence/', blank=True, null=True)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(
        default=True,
        help_text='Private evidence is never shown on the public article page.')
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='evidence_added')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'Evidence: {self.title}'


class VerificationEvent(models.Model):
    """Append-only history of trust-status changes (Truth Layers)."""

    FIELD_CHOICES = [
        ('article_verification_status', 'Article verification status'),
        ('claim_status', 'Claim status'),
    ]

    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='verification_events')
    claim = models.ForeignKey(
        Claim, on_delete=models.PROTECT,
        null=True, blank=True, related_name='verification_events')
    field = models.CharField(max_length=40, choices=FIELD_CHOICES)
    old_value = models.CharField(max_length=30, blank=True)
    new_value = models.CharField(max_length=30)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verification_events')
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.field}: {self.old_value} -> {self.new_value}'


class Correction(models.Model):
    """A public correction, clarification or redaction notice.

    Corrections are new records linked to what they correct; the history
    of an editorial correction is never silently erased. A REDACTION
    notice describes the action only — never the sensitive material.
    """

    KIND_CHOICES = [
        ('CORRECTION', 'Correction'),
        ('CLARIFICATION', 'Clarification'),
        ('REDACTION', 'Redaction'),
    ]

    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='corrections')
    update = models.ForeignKey(
        StoryUpdate, on_delete=models.PROTECT,
        null=True, blank=True, related_name='corrections')
    claim = models.ForeignKey(
        Claim, on_delete=models.PROTECT,
        null=True, blank=True, related_name='corrections')
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default='CORRECTION')
    text = models.TextField()
    published = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='corrections_made')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.get_kind_display()} on article {self.article_id}'


class ConsentRecord(models.Model):
    """Internal consent record for human-identifying material.

    INTERNAL ONLY: never exposed by any public template or API.
    `subject_descriptor` is an internal reference (e.g. "market trader,
    Argungu — interview 12 Oct"), not a public name.
    """

    BASIS_CHOICES = [
        ('WRITTEN', 'Written consent'),
        ('VERBAL_RECORDED', 'Verbal consent (recorded)'),
        ('GUARDIAN', 'Guardian consent'),
        ('NOT_REQUIRED', 'Not required'),
    ]

    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        null=True, blank=True, related_name='consent_records')
    impact_story = models.ForeignKey(
        'core.ImpactStory', on_delete=models.PROTECT,
        null=True, blank=True, related_name='consent_records')
    subject_descriptor = models.CharField(max_length=200)
    consent_basis = models.CharField(max_length=20, choices=BASIS_CHOICES)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='consent_records_made')
    notes = models.TextField(blank=True, help_text='Internal only. Never published.')
    withdrawn = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(article__isnull=False) | models.Q(impact_story__isnull=False),
                name='consent_needs_a_subject_record'),
        ]

    def __str__(self):
        return f'Consent ({self.consent_basis}) — internal'


class StoryAudit(models.Model):
    """Editorial audit trail for story records.

    Mirrors editorial.Audit's proven shape, scoped to public-journalism
    records. HARD RULE (enforced in services): `detail` must never
    contain confidential source text, personal data, or redacted content.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='story_audit_entries')
    action = models.CharField(max_length=60)
    target_type = models.CharField(max_length=40)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'{self.action} on {self.target_type} {self.target_id}'


# ─── Phase 2: Public Promise Tracker ──────────────────────────────────────────

class Institution(models.Model):
    """A public institution or authority responsible for a promise.

    `contact_note` and `notes` are internal editorial context and are
    never rendered on public pages.
    """

    KIND_CHOICES = [
        ('MINISTRY', 'Ministry'),
        ('AGENCY', 'Agency / parastatal'),
        ('LGA_GOVERNMENT', 'Local government'),
        ('COMPANY', 'Company / contractor'),
        ('OTHER', 'Other authority'),
    ]

    name = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='AGENCY')
    contact_note = models.CharField(max_length=300, blank=True,
                                    help_text='Internal only. Never published.')
    notes = models.TextField(blank=True, help_text='Internal only. Never published.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Promise(models.Model):
    """A public commitment tracked by KPN (Public Promise Tracker).

    Status vocabulary is the owner's: a promise moves ANNOUNCED →
    DOCUMENTED → IN_PROGRESS → COMPLETED_VERIFIED, and may be DELAYED
    or DISPUTED. COMPLETED_VERIFIED is guarded in the service layer
    (`services.set_promise_status`): it requires verification evidence
    on record — an official saying "completed" is never enough.
    `deadline` is nullable and is only ever a date the institution
    itself announced; it is never invented by editors.
    """

    STATUS_CHOICES = [
        ('ANNOUNCED', 'Announced'),
        ('DOCUMENTED', 'Documented'),
        ('IN_PROGRESS', 'In progress'),
        ('COMPLETED_VERIFIED', 'Completed — verified'),
        ('DELAYED', 'Delayed'),
        ('DISPUTED', 'Disputed'),
    ]
    # Plain-language reader labels for the public tracker.
    STATUS_LABELS = {
        'ANNOUNCED': 'Announced — the promise has been made publicly',
        'DOCUMENTED': 'Documented — KPN has recorded the details and evidence',
        'IN_PROGRESS': 'In progress — work is under way',
        'COMPLETED_VERIFIED': 'Completed — KPN has verified this with evidence',
        'DELAYED': 'Delayed — the promised date has passed or work is behind schedule',
        'DISPUTED': 'Disputed — sources disagree about this promise',
    }

    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, related_name='promises')
    title = models.CharField(max_length=250)
    description = models.TextField(help_text='What exactly was promised.')
    announced_by = models.CharField(
        max_length=200, blank=True,
        help_text='Who announced it, e.g. "Governor Nasir Idris".')
    announced_on = models.DateField()
    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    deadline = models.DateField(
        null=True, blank=True,
        help_text='The date the institution promised completion by. '
                  'Leave blank if no date was announced.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ANNOUNCED')
    zone = models.ForeignKey(
        'leadership.Zone', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promises')
    lga = models.ForeignKey(
        'leadership.LGA', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promises')
    ward = models.ForeignKey(
        'leadership.Ward', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promises')
    stories = models.ManyToManyField(
        'campaigns.Campaign', blank=True, related_name='promises',
        help_text='Published stories connected to this promise.')
    verification_claim = models.ForeignKey(
        Claim, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_promises',
        help_text='Optional: a CONFIRMED claim on a linked story, backed '
                  'by evidence, that verifies completion.')
    next_check_date = models.DateField(
        null=True, blank=True,
        help_text='When editors should next check on this promise.')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promises_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-announced_on', '-pk']

    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def location_label(self):
        parts = [obj.name for obj in (self.ward, self.lga, self.zone) if obj]
        return ', '.join(parts)

    def has_verification_evidence(self):
        """True when completion can honestly be called verified:
        either a linked CONFIRMED claim backed by >=1 evidence record,
        or >=1 promise update carrying its own evidence link."""
        claim = self.verification_claim
        if (claim is not None and claim.status == 'CONFIRMED'
                and claim.evidence_records.exists()):
            return True
        return self.updates.exclude(evidence_url='').exists()

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'


class PromiseUpdate(models.Model):
    """A dated progress record on a promise.

    History is append-only: every status change is written as an
    update row by the service layer (with `status_after` set), and
    edits are tracked through StoryAudit. Updates carry their own
    evidence links.
    """

    promise = models.ForeignKey(
        Promise, on_delete=models.PROTECT, related_name='updates')
    update_date = models.DateField()
    title = models.CharField(max_length=250)
    body = models.TextField(blank=True)
    status_after = models.CharField(
        max_length=20, choices=Promise.STATUS_CHOICES, blank=True,
        help_text='The promise status after this update (blank = unchanged).')
    evidence_title = models.CharField(max_length=200, blank=True)
    evidence_url = models.URLField(max_length=500, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promise_updates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['update_date', 'created_at', 'pk']

    def __str__(self):
        return f'{self.promise_id}: {self.title}'


# ─── Phase 2: Community Radar ─────────────────────────────────────────────────

class StorySourceLink(models.Model):
    """An editorial link between a community report and a story
    (Community Radar).

    Deliberately a link model in this app so `core.CommunityReport`
    stays untouched and one report can feed several stories. The link
    stores NO reporter data: the public story page may only ever show
    geography-level attribution for APPROVED reports — never a
    reporter's name, phone number or report details.
    """

    KIND_CHOICES = [
        ('SOURCE', 'Report was a source for this story'),
        ('FOLLOW_UP', 'Story follows up this report'),
        ('RELATED', 'Related to this story'),
    ]

    report = models.ForeignKey(
        'core.CommunityReport', on_delete=models.PROTECT,
        related_name='story_links')
    article = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.PROTECT,
        related_name='source_links')
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default='SOURCE')
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='story_source_links')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['report', 'article'],
                name='one_link_per_report_and_story'),
        ]

    def __str__(self):
        return f'Report {self.report_id} -> article {self.article_id} ({self.kind})'
