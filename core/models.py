from django.conf import settings
from django.db import models
from django.utils import timezone

class FAQ(models.Model):
    question = models.CharField(max_length=500)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'
    
    def __str__(self):
        return self.question


class Report(models.Model):
    REPORT_TYPE_CHOICES = [
        ('WARD_TO_LGA', 'Ward to LGA Report'),
        ('LGA_TO_ZONAL', 'LGA to Zonal Report'),
        ('ZONAL_TO_STATE', 'Zonal to State Report'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('APPROVED', 'Approved'),
        ('FLAGGED', 'Flagged for Issues'),
        ('REJECTED', 'Rejected'),
        ('ESCALATED', 'Escalated to Next Level'),
    ]
    
    title = models.CharField(max_length=300)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    content = models.TextField()
    period = models.CharField(max_length=100, blank=True, default='', help_text="Reporting period (e.g., 'January 2025', 'Q1 2025', 'Week 1')")
    
    submitted_by = models.ForeignKey('staff.User', on_delete=models.CASCADE, related_name='submitted_reports')
    submitted_to = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_reports', help_text="Supervisor who receives this report")
    reviewed_by = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    
    parent_report = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_reports', help_text="Parent report that this report was escalated from")
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    is_reviewed = models.BooleanField(default=False)
    is_escalated = models.BooleanField(default=False, help_text="Whether this report has been escalated to next level")
    review_notes = models.TextField(blank=True)
    
    deadline = models.DateField(null=True, blank=True, help_text="Deadline for report submission")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True, help_text="When this report was escalated")
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'submitted_to'], name='report_status_receiver_idx'),
            models.Index(fields=['status', '-created_at'], name='report_status_created_idx'),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.get_report_type_display()}"
    
    def is_overdue(self):
        """Check if report is overdue"""
        if self.deadline and self.status in ['DRAFT', 'SUBMITTED']:
            from django.utils import timezone
            return timezone.now().date() > self.deadline
        return False
    
    def get_report_chain(self):
        """Get the full chain of reports from root to this report"""
        chain = [self]
        current = self.parent_report
        while current:
            chain.insert(0, current)
            current = current.parent_report
        return chain
    
    def can_be_escalated(self):
        """Check if this report can be escalated to the next level"""
        return (
            self.status == 'APPROVED' and 
            not self.is_escalated and 
            self.report_type in ['WARD_TO_LGA', 'LGA_TO_ZONAL']
        )


class Opportunity(models.Model):
    CATEGORY_CHOICES = [
        ('SCHOLARSHIP', 'Scholarships & Education'),
        ('GRANT', 'Grants & Funding'),
        ('JOB', 'Jobs & Employment'),
        ('INTERNSHIP', 'Internships'),
        ('VOLUNTEER', 'Volunteer Opportunities'),
        ('ENTREPRENEURSHIP', 'Entrepreneurship'),
        ('TRAINING', 'Skills & Training'),
        ('EMPOWERMENT', 'Empowerment Programs'),
        ('FELLOWSHIP', 'Fellowships & Leadership'),
    ]

    STATUS_CHOICES = [
        ('OPEN', 'Open & Accepting Applications'),
        ('CLOSING_SOON', 'Closing Soon'),
        ('CLOSED', 'Closed'),
        # Page-by-Page Upgrade Priority 1 (D-06): a listing whose details
        # are still being checked against the provider's official source.
        # Public with a "Verifying" badge; no application link is handed
        # out while a listing is in this state.
        ('VERIFICATION_PENDING', 'Verification Pending'),
    ]

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='GRANT')
    
    provider = models.CharField(max_length=200, help_text="Who is providing this? (e.g. Federal Govt, NGO, Private Sector)")
    description = models.TextField()
    
    requirements = models.TextField(blank=True, help_text="Eligibility requirements (bullet points recommended)")
    benefits = models.TextField(blank=True, help_text="What does it offer? (Funding amount, salary, etc.)")
    
    application_link = models.URLField(blank=True, help_text="External link to apply")
    deadline = models.DateField(null=True, blank=True)

    # Page-by-Page Upgrade Priority 1 (brief §B): opening date, location
    # and eligibility detail. All optional — listings published before
    # this upgrade simply leave them unstated.
    opens_at = models.DateField(null=True, blank=True,
                                help_text="Date applications open, if announced")
    location_text = models.CharField(max_length=200, blank=True,
                                     help_text="Where the opportunity is based or takes place")
    lga = models.ForeignKey(
        'leadership.LGA', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='opportunities',
        help_text="Kebbi LGA the opportunity is tied to, if any")
    nigerians_eligible = models.BooleanField(
        null=True, blank=True,
        help_text="Tick if Nigerians are eligible; leave unset if not stated")
    verification_source = models.CharField(
        max_length=300, blank=True,
        help_text="Official source this listing was checked against (recorded at verification)")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    
    is_featured = models.BooleanField(default=False, help_text="Feature this opportunity on the homepage/hub top")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Opportunity'
        verbose_name_plural = 'Opportunities'
        indexes = [
            models.Index(fields=['status', 'category'], name='opp_status_cat_idx'),
            models.Index(fields=['deadline'], name='opp_deadline_idx'),
        ]

    def __str__(self):
        return self.title

    def get_status_colour(self):
        return {
            'OPEN': 'bg-green-100 text-green-800',
            'CLOSING_SOON': 'bg-yellow-100 text-yellow-800',
            'CLOSED': 'bg-red-100 text-red-800',
            'VERIFICATION_PENDING': 'bg-amber-100 text-amber-800',
        }.get(self.status, 'bg-gray-100 text-gray-800')

    @property
    def is_verifying(self):
        return self.status == 'VERIFICATION_PENDING'

    @property
    def public_application_link(self):
        """The link a visitor may use. A listing still being verified
        never hands out an application link (D-06)."""
        if self.is_verifying:
            return ''
        return self.application_link


class OpportunityReport(models.Model):
    """A visitor's report that an opportunity listing looks suspicious
    (brief §B, decision D-07). Reports land in the staff triage queue
    inside Manage Opportunities; nothing is published or changed
    automatically. An upheld report moves the listing to
    VERIFICATION_PENDING pending re-check — it never deletes it."""

    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('REVIEWED', 'Reviewed — no action'),
        ('UPHELD', 'Upheld — listing sent for re-verification'),
        ('DISMISSED', 'Dismissed'),
    ]

    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.CASCADE, related_name='listing_reports')
    reason = models.TextField(help_text="What looks wrong about this listing?")
    reporter_name = models.CharField(max_length=120, blank=True)
    reporter_contact = models.CharField(
        max_length=200, blank=True,
        help_text="Optional email or phone, if the reporter wants a reply")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='NEW')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='opportunity_reports_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Opportunity listing report'
        verbose_name_plural = 'Opportunity listing reports'

    def __str__(self):
        return f'Report on {self.opportunity.title} ({self.get_status_display()})'


class CommunityInitiative(models.Model):
    CATEGORY_CHOICES = [
        ('WELFARE', 'Welfare & Relief'),
        ('VOLUNTEER', 'Volunteer Work'),
        ('PROJECT', 'Community Project'),
        ('HUMANITARIAN', 'Humanitarian Aid'),
    ]
    STATUS_CHOICES = [
        ('PLANNING', 'Planning'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        # Page-by-Page Upgrade Priority 2 (brief §D): the public
        # lifecycle also distinguishes paused and cancelled work.
        ('PAUSED', 'Paused'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Public presentation labels — the brief names the first state
    # "Planned"; the stored value and staff wording stay PLANNING.
    PUBLIC_STATUS_LABELS = {
        'PLANNING': 'Planned',
        'ACTIVE': 'Active',
        'COMPLETED': 'Completed',
        'PAUSED': 'Paused',
        'CANCELLED': 'Cancelled',
    }

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNING')

    description = models.TextField()
    location_text = models.CharField(max_length=200, help_text="E.g., Birnin Kebbi Central Market")

    # Page-by-Page Upgrade Priority 2 (brief §D): each initiative shows
    # its objective, dates, responsible KPN team and documented
    # results. All optional — records created before this upgrade
    # simply leave them unstated.
    objective = models.TextField(
        blank=True, help_text="What this initiative sets out to achieve")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    responsible_team = models.CharField(
        max_length=200, blank=True,
        help_text="Responsible KPN team (e.g. Jega LGA Chapter)")
    results = models.TextField(
        blank=True, help_text="Documented results, shown for completed initiatives")
    lga = models.ForeignKey(
        'leadership.LGA', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='community_initiatives',
        help_text="Kebbi LGA the initiative is based in, if it has one")
    ward = models.ForeignKey(
        'leadership.Ward', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='community_initiatives',
        help_text="Ward the initiative is based in, if it has one")

    # Impact metrics
    people_reached = models.PositiveIntegerField(default=0)

    image = models.ImageField(upload_to='community/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def public_status_label(self):
        return self.PUBLIC_STATUS_LABELS.get(self.status, self.get_status_display())

    def get_status_colour(self):
        return {
            'PLANNING': 'bg-yellow-100 text-yellow-800',
            'ACTIVE': 'bg-green-100 text-green-800',
            'COMPLETED': 'bg-blue-100 text-blue-800',
            'PAUSED': 'bg-orange-100 text-orange-800',
            'CANCELLED': 'bg-red-100 text-red-800',
        }.get(self.status, 'bg-gray-100 text-gray-800')


class AdvocacyCampaign(models.Model):
    # Page-by-Page Upgrade Priority 2 (brief §E): a campaign lifecycle
    # recorded alongside the long-standing is_active flag, which keeps
    # its existing meaning (shown on the public campaigns page).
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
        ('CLOSED', 'Closed'),
    ]

    title = models.CharField(max_length=200)
    issue = models.TextField(help_text="What is the core issue?")
    background = models.TextField(help_text="Background context")
    kpn_position = models.TextField(help_text="KPN's official position", blank=True)
    actions_taken = models.TextField(help_text="What actions have been taken?", blank=True)
    government_response = models.TextField(blank=True)
    outcome = models.TextField(blank=True)

    # Page-by-Page Upgrade Priority 2 (brief §E): the full campaign
    # structure. All optional — campaigns recorded before this upgrade
    # start empty here rather than backfilled with guesses (C-08).
    objective = models.TextField(
        blank=True, help_text="What the campaign sets out to achieve")
    affected_communities = models.TextField(
        blank=True, help_text="Communities affected by the issue")
    proposed_action = models.TextField(
        blank=True, help_text="The action KPN proposes or is pursuing")
    responsible_team = models.CharField(
        max_length=200, blank=True,
        help_text="Responsible KPN team (e.g. Civic Engagement Team)")
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='ACTIVE')
    evidence_articles = models.ManyToManyField(
        'campaigns.Campaign', blank=True, related_name='advocacy_evidence_for',
        help_text="Published KPN articles that document the evidence behind this campaign")

    is_active = models.BooleanField(default=True)

    image = models.ImageField(upload_to='advocacy/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AdvocacyActivity(models.Model):
    """One dated entry in an advocacy campaign's progress log
    (brief §E: progress and activities). The campaign's actions_taken
    field remains the summary; this log carries the dated record."""

    campaign = models.ForeignKey(
        AdvocacyCampaign, on_delete=models.CASCADE, related_name='activities')
    date = models.DateField()
    entry = models.TextField(help_text="What happened on this date?")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']
        verbose_name = 'Advocacy activity'
        verbose_name_plural = 'Advocacy activities'

    def __str__(self):
        return f'{self.campaign.title} — {self.date}'


class CommunityReport(models.Model):
    # This is the public "Report a story" model
    CATEGORY_CHOICES = [
        ('COMMUNITY', 'Community'),
        ('EDUCATION', 'Education'),
        ('AGRICULTURE', 'Agriculture'),
        ('HEALTH', 'Health'),
        ('SECURITY', 'Security'),
        ('INFRASTRUCTURE', 'Infrastructure'),
        ('MARKETS', 'Markets & Business'),
        ('YOUTH', 'Youth'),
        ('WOMEN', 'Women'),
        ('ENVIRONMENT', 'Environment'),
        ('HUMAN_INTEREST', 'Human Interest'),
        ('CULTURE', 'Culture'),
        ('TRADITIONAL', 'Traditional Institutions'),
        ('GOVERNMENT', 'Government & Governance'),
        ('EMERGENCY', 'Emergency'),
        ('OPPORTUNITY', 'Opportunity'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('UNDER_REVIEW', 'Under Review'),
        ('ESCALATED', 'Escalated'),
        ('APPROVED', 'Approved for Publication'),
        ('REJECTED', 'Rejected'),
    ]
    
    INFO_STATUS_CHOICES = [
        ('VERIFIED', 'KPN VERIFIED'),
        ('CONFIRMED', 'KPN CONFIRMED'),
        ('DEVELOPING', 'KPN DEVELOPING'),
        ('ALERT', 'KPN COMMUNITY ALERT'),
    ]
    
    reporter_name = models.CharField(max_length=100)
    reporter_phone = models.CharField(max_length=20, blank=True)
    submitted_by = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='community_reports')
    
    # Geographic mapping (optional if reporter doesn't know)
    ward = models.ForeignKey('leadership.Ward', on_delete=models.SET_NULL, null=True, blank=True)
    lga = models.ForeignKey('leadership.LGA', on_delete=models.SET_NULL, null=True, blank=True)
    zone = models.ForeignKey('leadership.Zone', on_delete=models.SET_NULL, null=True, blank=True)
    
    location_details = models.CharField(max_length=200, help_text="Specific location or village")
    
    incident_date = models.DateField(null=True, blank=True)
    incident_time = models.TimeField(null=True, blank=True)
    
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    
    what_happened = models.TextField()
    who_was_involved = models.TextField(blank=True)
    why_is_it_important = models.TextField(blank=True)
    
    evidence_image = models.ImageField(upload_to='reports/evidence/', null=True, blank=True)
    evidence_video = models.FileField(upload_to='reports/evidence/videos/', null=True, blank=True)
    
    # Internal fields
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    info_status = models.CharField(max_length=20, choices=INFO_STATUS_CHOICES, blank=True)
    internal_notes = models.TextField(blank=True, help_text="Not visible to public")

    # Page-by-Page Upgrade Priority 2 (brief §E, decision D-08):
    # Community Voice publication is an explicit reviewer decision,
    # separate from newsroom approval. Nothing is published to
    # Community Voice automatically.
    published_to_voice = models.BooleanField(
        default=False,
        help_text="Reviewer decision: show this documented concern on Community Voice")
    voice_published_at = models.DateTimeField(null=True, blank=True)
    # The brief's escalation path as a record: a documented concern can
    # become an advocacy campaign. Staff create the campaign and link
    # it here; nothing escalates automatically.
    escalated_campaign = models.ForeignKey(
        'core.AdvocacyCampaign', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_reports',
        help_text="Advocacy campaign this concern escalated into, if any")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Report: {self.get_category_display()} at {self.location_details}"


class ImpactStory(models.Model):
    CATEGORY_CHOICES = [
        ('SUCCESS', 'Success Story'),
        ('PROJECT', 'Community Project'),
        ('GOVERNMENT', 'Government Response'),
        ('EMPOWERMENT', 'Youth Empowerment'),
        ('TRAINING', 'Training Programme'),
        ('PARTNERSHIP', 'Partnership Achievement'),
        ('HUMANITARIAN', 'Humanitarian Activity'),
    ]
    
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    description = models.TextField()
    
    # Impact numbers (optional)
    people_impacted = models.PositiveIntegerField(null=True, blank=True)
    communities_reached = models.PositiveIntegerField(null=True, blank=True)
    
    image = models.ImageField(upload_to='impact_stories/', null=True, blank=True)
    
    date_achieved = models.DateField(default=timezone.now)
    
    is_published = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date_achieved', '-created_at']
        verbose_name = 'Impact Story'
        verbose_name_plural = 'Impact Stories'
        
    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"


class Notification(models.Model):
    """In-app notifications delivered to individual users."""

    TYPE_CHOICES = [
        ('INFO', 'Information'),
        ('SUCCESS', 'Success'),
        ('WARNING', 'Warning'),
        ('ACTION', 'Action Required'),
    ]

    user = models.ForeignKey(
        'staff.User',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notif_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='INFO')
    event = models.CharField(max_length=50, default='INFO')
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(
        max_length=300, blank=True,
        help_text="Optional URL the bell notification links to"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"[{self.notif_type}] {self.title} → {self.user}"
class IctAdminAssignment(models.Model):
    """The single ICT Admin assignment (owner instruction, 2026-11-24).

    KPN has no "ICT Admin" role: the assignment names ONE member or
    position holder who acts as ICT admin and may open the ICT Admin
    console. It starts with the Director of Media & Communications
    (seeded fail-safe by ``seed_ict_admin`` inside ``release_migrate``)
    and can be moved to another person ONLY by the Super Admin, in
    the Django admin panel — the Super Admin operates only through
    /admin/ (owner clarification, 2026-11-24); the console itself is
    read-only and the President or any other role cannot change it.
    The row is a singleton (``id`` is pinned to 1, the same pattern
    as ``editorial.Control``); ``user`` stays empty until a holder
    exists.
    """
    id = models.PositiveSmallIntegerField(
        primary_key=True, default=1, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ict_admin_assignment',
        help_text="The current ICT Admin holder. Empty = unassigned; "
                  "the console is then superuser-only.")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        help_text="Super admin who last changed the assignment.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ICT Admin assignment'
        verbose_name_plural = 'ICT Admin assignment'

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    def __str__(self):
        if self.user_id:
            return f'ICT Admin: {self.user}'
        return 'ICT Admin: unassigned'


class IctAdminChange(models.Model):
    """Append-only audit record of ICT Admin reassignments.

    Written only when the Super Admin changes the holder in the
    Django admin panel (the ModelAdmin's save_model); rows are never
    edited or deleted by the site.
    """
    previous_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    new_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        help_text="The super admin who made the change.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'ICT Admin change'
        verbose_name_plural = 'ICT Admin changes'

    def __str__(self):
        return (f'ICT Admin: {self.previous_holder} -> {self.new_holder} '
                f'by {self.changed_by}')


class Patron(models.Model):
    PATRON_TYPE = [('GRAND', 'Grand Patron'), ('PATRON', 'Patron')]
    patron_type = models.CharField(max_length=10, choices=PATRON_TYPE, default='PATRON')
    full_name = models.CharField(max_length=200)
    title = models.CharField(max_length=200, help_text="Official title/designation")
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='patrons/', blank=True, null=True)
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order (lower = higher)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['patron_type', 'order', 'full_name']
        
    def __str__(self):
        return self.full_name
