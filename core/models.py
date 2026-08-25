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
        }.get(self.status, 'bg-gray-100 text-gray-800')


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
    ]
    
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNING')
    
    description = models.TextField()
    location_text = models.CharField(max_length=200, help_text="E.g., Birnin Kebbi Central Market")
    
    # Impact metrics
    people_reached = models.PositiveIntegerField(default=0)
    
    image = models.ImageField(upload_to='community/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AdvocacyCampaign(models.Model):
    title = models.CharField(max_length=200)
    issue = models.TextField(help_text="What is the core issue?")
    background = models.TextField(help_text="Background context")
    kpn_position = models.TextField(help_text="KPN's official position", blank=True)
    actions_taken = models.TextField(help_text="What actions have been taken?", blank=True)
    government_response = models.TextField(blank=True)
    outcome = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    
    image = models.ImageField(upload_to='advocacy/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


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
