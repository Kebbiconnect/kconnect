from django.contrib.auth.models import AbstractUser
from django.db import models
from leadership.models import Zone, LGA, Ward, RoleDefinition

class User(AbstractUser):
    ROLE_CHOICES = [
        ('GENERAL', 'General Member'),
        ('STATE', 'State Executive'),
        ('ZONAL', 'Zonal Excos'),
        ('LGA', 'LGA Excos'),
        ('WARD', 'Ward Leaders'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('SUSPENDED', 'Suspended'),
        ('DISMISSED', 'Dismissed'),
    ]
    
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]
    
    phone = models.CharField(max_length=20)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    
    # Social Media Links (optional)
    facebook_url = models.URLField(max_length=200, blank=True, help_text="Your Facebook profile URL")
    twitter_url = models.URLField(max_length=200, blank=True, help_text="Your Twitter/X profile URL")
    instagram_url = models.URLField(max_length=200, blank=True, help_text="Your Instagram profile URL")
    tiktok_url = models.URLField(max_length=200, blank=True, help_text="Your TikTok profile URL")
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='GENERAL')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    
    role_definition = models.ForeignKey(RoleDefinition, on_delete=models.SET_NULL, null=True, blank=True, related_name='holders')
    
    facebook_verified = models.BooleanField(default=False)
    date_approved = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_members')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'role'], name='user_status_role_idx'),
            models.Index(fields=['status', 'zone'], name='user_status_zone_idx'),
            models.Index(fields=['status', 'lga'], name='user_status_lga_idx'),
            models.Index(fields=['status', 'ward'], name='user_status_ward_idx'),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    def is_leader(self):
        return self.role in ['STATE', 'ZONAL', 'LGA', 'WARD']
    
    def can_approve_members(self):
        return self.role in ['STATE', 'ZONAL', 'LGA'] and self.status == 'APPROVED'
    
    def get_jurisdiction(self):
        if self.role == 'STATE':
            return 'State'
        elif self.role == 'ZONAL' and self.zone:
            return self.zone.name
        elif self.role == 'LGA' and self.lga:
            return self.lga.name
        elif self.role == 'WARD' and self.ward:
            return self.ward.name
        return 'N/A'


class DisciplinaryAction(models.Model):
    ACTION_CHOICES = [
        ('WARNING', 'Warning'),
        ('SUSPENSION', 'Suspension'),
        ('DISMISSAL', 'Dismissal'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='disciplinary_actions')
    action_type = models.CharField(max_length=15, choices=ACTION_CHOICES)
    reason = models.TextField()
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_actions')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_actions')
    is_approved = models.BooleanField(default=False)
    
    legal_reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='legal_reviewed_actions')
    legal_opinion = models.TextField(blank=True, help_text="Legal Adviser's opinion on the disciplinary action")
    legal_approved = models.BooleanField(default=False)
    legal_reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.user.get_full_name()}"


class WomensProgram(models.Model):
    PROGRAM_STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PROGRAM_TYPE_CHOICES = [
        ('TRAINING', 'Training & Skills Development'),
        ('EMPOWERMENT', 'Women Empowerment'),
        ('HEALTH', 'Health & Wellness'),
        ('ADVOCACY', 'Advocacy & Rights'),
        ('NETWORKING', 'Networking Event'),
        ('OTHER', 'Other'),
    ]
    
    title = models.CharField(max_length=300)
    description = models.TextField()
    program_type = models.CharField(max_length=20, choices=PROGRAM_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=PROGRAM_STATUS_CHOICES, default='PLANNED')
    
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank for State-level programs")
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank for Zonal/State-level programs")
    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    participants = models.ManyToManyField(User, blank=True, related_name='womens_programs')
    target_participants = models.PositiveIntegerField(default=0, help_text="Expected number of participants")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_womens_programs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-start_date', '-created_at']
        verbose_name = "Women's Program"
        verbose_name_plural = "Women's Programs"
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    def get_participant_count(self):
        return self.participants.count()
    
    def get_scope(self):
        if self.lga:
            return f"LGA - {self.lga.name}"
        elif self.zone:
            return f"Zonal - {self.zone.name}"
        return "State-wide"


class YouthProgram(models.Model):
    PROGRAM_STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PROGRAM_TYPE_CHOICES = [
        ('TRAINING', 'Training & Skills Development'),
        ('WORKSHOP', 'Workshop'),
        ('MENTORSHIP', 'Mentorship Program'),
        ('ENTREPRENEURSHIP', 'Entrepreneurship'),
        ('LEADERSHIP', 'Leadership Development'),
        ('SPORTS', 'Sports & Recreation'),
        ('OTHER', 'Other'),
    ]
    
    title = models.CharField(max_length=300)
    description = models.TextField()
    program_type = models.CharField(max_length=20, choices=PROGRAM_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=PROGRAM_STATUS_CHOICES, default='PLANNED')
    
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank for State-level programs")
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank for Zonal/State-level programs")
    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    participants = models.ManyToManyField(User, blank=True, related_name='youth_programs')
    target_participants = models.PositiveIntegerField(default=0, help_text="Expected number of participants")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_youth_programs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    impact_report = models.TextField(blank=True, help_text="Summary of program impact and outcomes")
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-start_date', '-created_at']
        verbose_name = "Youth Program"
        verbose_name_plural = "Youth Programs"
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    def get_participant_count(self):
        return self.participants.count()
    
    def get_scope(self):
        if self.lga:
            return f"LGA - {self.lga.name}"
        elif self.zone:
            return f"Zonal - {self.zone.name}"
        return "State-wide"


class WelfareProgram(models.Model):
    PROGRAM_STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PROGRAM_TYPE_CHOICES = [
        ('HEALTH', 'Health Support'),
        ('FINANCIAL', 'Financial Assistance'),
        ('EDUCATION', 'Educational Support'),
        ('EMERGENCY', 'Emergency Relief'),
        ('SOCIAL', 'Social Welfare'),
        ('OTHER', 'Other'),
    ]
    
    title = models.CharField(max_length=300)
    description = models.TextField()
    program_type = models.CharField(max_length=20, choices=PROGRAM_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=PROGRAM_STATUS_CHOICES, default='PLANNED')
    
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank for State-level programs")
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank for Zonal/State-level programs")
    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    beneficiaries = models.ManyToManyField(User, blank=True, related_name='welfare_programs')
    target_beneficiaries = models.PositiveIntegerField(default=0, help_text="Expected number of beneficiaries")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_welfare_programs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    funds_disbursed = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Amount already disbursed")
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-start_date', '-created_at']
        verbose_name = "Welfare Program"
        verbose_name_plural = "Welfare Programs"
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    def get_beneficiary_count(self):
        return self.beneficiaries.count()
    
    def get_remaining_budget(self):
        if self.budget:
            return self.budget - self.funds_disbursed
        return 0
    
    def get_scope(self):
        if self.lga:
            return f"LGA - {self.lga.name}"
        elif self.zone:
            return f"Zonal - {self.zone.name}"
        return "State-wide"


class CommunityOutreach(models.Model):
    ENGAGEMENT_TYPE_CHOICES = [
        ('MEETING', 'Meeting'),
        ('PARTNERSHIP', 'Partnership Discussion'),
        ('EVENT', 'Community Event'),
        ('MEDIA', 'Media Engagement'),
        ('COLLABORATION', 'Collaboration'),
        ('OTHER', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('FOLLOW_UP', 'Follow-up Required'),
    ]
    
    organization = models.CharField(max_length=300, help_text="Organization or community group name")
    contact_person = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    
    engagement_type = models.CharField(max_length=20, choices=ENGAGEMENT_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PLANNED')
    
    date = models.DateField(help_text="Date of outreach activity")
    location = models.CharField(max_length=200, blank=True)
    
    purpose = models.TextField(help_text="Purpose of the outreach")
    notes = models.TextField(blank=True, help_text="Details and outcomes of the engagement")
    
    follow_up_date = models.DateField(null=True, blank=True, help_text="Date for follow-up action")
    follow_up_notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_outreach')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Community Outreach'
        verbose_name_plural = 'Community Outreach Activities'
    
    def __str__(self):
        return f"{self.organization} - {self.get_engagement_type_display()} ({self.date})"


class WardMeeting(models.Model):
    MEETING_TYPE_CHOICES = [
        ('GENERAL', 'General Meeting'),
        ('EXECUTIVE', 'Executive Meeting'),
        ('EMERGENCY', 'Emergency Meeting'),
        ('PLANNING', 'Planning Session'),
        ('OTHER', 'Other'),
    ]
    
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='ward_meetings')
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPE_CHOICES)
    
    title = models.CharField(max_length=300)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    agenda = models.TextField(blank=True, help_text="Meeting agenda and topics")
    minutes = models.TextField(blank=True, help_text="Meeting minutes and decisions")
    
    attendees = models.ManyToManyField(User, blank=True, related_name='attended_ward_meetings', through='WardMeetingAttendance', through_fields=('meeting', 'member'))
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_ward_meetings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Ward Meeting'
        verbose_name_plural = 'Ward Meetings'
    
    def __str__(self):
        return f"{self.ward.name} - {self.title} ({self.date})"
    
    def get_attendance_count(self):
        return self.attendees.count()


class WardMeetingAttendance(models.Model):
    meeting = models.ForeignKey(WardMeeting, on_delete=models.CASCADE, related_name='attendance_records')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ward_meeting_attendance')
    
    present = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_ward_attendance')
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['meeting', 'member']
        ordering = ['member__last_name', 'member__first_name']
    
    def __str__(self):
        status = "Present" if self.present else "Absent"
        return f"{self.member.get_full_name()} - {status}"


class Announcement(models.Model):
    SCOPE_CHOICES = [
        ('GENERAL', 'General - All KPN Members'),
        ('ZONAL', 'Zonal - Specific Zone'),
        ('LGA', 'LGA - Specific LGA'),
        ('WARD', 'Ward - Specific Ward'),
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]
    
    title = models.CharField(max_length=200, help_text="Brief title for the announcement")
    content = models.TextField(help_text="Announcement message")
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, help_text="Who should receive this announcement")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='NORMAL')
    
    target_zone = models.ForeignKey(Zone, on_delete=models.CASCADE, null=True, blank=True, related_name='announcements', 
                                   help_text="Required for ZONAL scope - all LGAs in this zone will receive the announcement")
    target_lga = models.ForeignKey(LGA, on_delete=models.CASCADE, null=True, blank=True, related_name='announcements',
                                  help_text="Required for LGA scope")
    target_ward = models.ForeignKey(Ward, on_delete=models.CASCADE, null=True, blank=True, related_name='announcements',
                                   help_text="Required for WARD scope")
    
    is_active = models.BooleanField(default=True, help_text="Only active announcements are shown to users")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Optional expiration date (announcement will auto-deactivate)")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_announcements')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['is_active', 'scope', 'target_zone'], name='ann_zone_idx'),
            models.Index(fields=['is_active', 'scope', 'target_lga'], name='ann_lga_idx'),
            models.Index(fields=['is_active', 'scope', 'target_ward'], name='ann_ward_idx'),
            models.Index(fields=['is_active', 'created_at'], name='ann_active_idx'),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.get_scope_display()})"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        if self.scope == 'GENERAL':
            if self.target_zone or self.target_lga or self.target_ward:
                raise ValidationError("General announcements should not have zone, LGA, or ward targets.")
        elif self.scope == 'ZONAL':
            if not self.target_zone:
                raise ValidationError("Zonal announcements must have a target zone.")
            if self.target_lga or self.target_ward:
                raise ValidationError("Zonal announcements should only specify a zone.")
        elif self.scope == 'LGA':
            if not self.target_lga:
                raise ValidationError("LGA announcements must have a target LGA.")
            if self.target_ward:
                raise ValidationError("LGA announcements should not specify a ward.")
            if self.target_zone and self.target_lga and self.target_zone != self.target_lga.zone:
                raise ValidationError("Target LGA must belong to the target zone.")
        elif self.scope == 'WARD':
            if not self.target_ward:
                raise ValidationError("Ward announcements must have a target ward.")
            if self.target_lga and self.target_ward and self.target_lga != self.target_ward.lga:
                raise ValidationError("Target ward must belong to the target LGA.")
    
    @classmethod
    def for_user(cls, user):
        from django.utils import timezone
        from django.db.models import Q
        
        now = timezone.now()
        base_query = cls.objects.filter(is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        
        query = Q(scope='GENERAL')
        
        if user.zone:
            query |= Q(scope='ZONAL', target_zone=user.zone)
        
        if user.lga:
            query |= Q(scope='LGA', target_lga=user.lga)
        
        if user.ward:
            query |= Q(scope='WARD', target_ward=user.ward)
        
        return base_query.filter(query).select_related('created_by', 'target_zone', 'target_lga', 'target_ward')
    
    def get_target_display(self):
        if self.scope == 'GENERAL':
            return 'All KPN Members'
        elif self.scope == 'ZONAL' and self.target_zone:
            return f'{self.target_zone.name} Zone'
        elif self.scope == 'LGA' and self.target_lga:
            return self.target_lga.name
        elif self.scope == 'WARD' and self.target_ward:
            return self.target_ward.name
        return 'Unknown'
