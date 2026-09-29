from django.db import models
from django.conf import settings
from django.utils import timezone


class TelegramMembership(models.Model):
    """
    Stores a KPN member's Telegram identity and channel membership status.
    OneToOne with staff.User — one Telegram account cannot link to multiple KPN accounts.
    """

    TELEGRAM_STATUS_CHOICES = [
        ('creator', 'Creator'),
        ('administrator', 'Administrator'),
        ('member', 'Member'),
        ('restricted', 'Restricted'),
        ('left', 'Left'),
        ('kicked', 'Kicked/Banned'),
        ('not_member', 'Not a Member'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_membership',
    )

    # Permanent Telegram identity — never use username as primary ID
    telegram_user_id = models.BigIntegerField(
        unique=True,
        help_text="Permanent Telegram user ID. Never changes."
    )
    telegram_username = models.CharField(
        max_length=100, blank=True,
        help_text="Telegram @username (may change — supplementary only)"
    )
    telegram_first_name = models.CharField(max_length=100, blank=True)
    telegram_last_name = models.CharField(max_length=100, blank=True)
    telegram_photo_url = models.URLField(blank=True)

    # Channel membership status
    telegram_status = models.CharField(
        max_length=20,
        choices=TELEGRAM_STATUS_CHOICES,
        default='not_member'
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="True only when Telegram confirms active channel membership"
    )

    # Timestamps
    first_verified_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When member was detected as having left the channel"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Telegram Membership'
        verbose_name_plural = 'Telegram Memberships'
        indexes = [
            models.Index(fields=['telegram_user_id'], name='tg_user_id_idx'),
            models.Index(fields=['is_verified'], name='tg_verified_idx'),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} — Telegram @{self.telegram_username or self.telegram_user_id}"

    def get_display_name(self):
        parts = [self.telegram_first_name, self.telegram_last_name]
        return ' '.join(p for p in parts if p) or f"User {self.telegram_user_id}"

    def is_active_member(self):
        """Returns True if current Telegram status represents active channel access."""
        return self.is_verified and self.telegram_status in ('creator', 'administrator', 'member')

    def mark_left(self):
        """Mark as no longer an active channel member."""
        now = timezone.now()
        self.is_verified = False
        self.left_at = now
        self.last_checked_at = now
        if self.telegram_status not in ('left', 'kicked'):
            self.telegram_status = 'left'
        self.save(update_fields=['is_verified', 'left_at', 'last_checked_at', 'telegram_status', 'updated_at'])


class KPNMeeting(models.Model):
    """
    Represents an official KPN meeting (virtual or physical) tracked via the Telegram bot.
    """

    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('ACTIVE', 'Active / In Progress'),
        ('ENDED', 'Ended'),
        ('CANCELLED', 'Cancelled'),
    ]

    MEETING_TYPE_CHOICES = [
        ('STATE_EXECUTIVE', 'State Executive Meeting'),
        ('ZONAL', 'Zonal Meeting'),
        ('LGA', 'LGA Meeting'),
        ('WARD', 'Ward Meeting'),
        ('SPECIAL', 'Special / Emergency Meeting'),
        ('GENERAL', 'General Assembly'),
    ]

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    meeting_type = models.CharField(
        max_length=20, choices=MEETING_TYPE_CHOICES, default='STATE_EXECUTIVE'
    )
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='SCHEDULED'
    )

    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)

    # Telegram message ID of the attendance announcement in the channel
    telegram_message_id = models.BigIntegerField(
        null=True, blank=True,
        help_text="Message ID of the meeting announcement in the KPN Telegram channel"
    )
    telegram_chat_id = models.CharField(
        max_length=50, blank=True,
        help_text="Chat/group where the meeting attendance is managed"
    )

    # Expected participants (can be left blank for open meetings)
    expected_participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='expected_meetings',
        help_text="KPN members expected to attend this meeting"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_meetings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_start']
        verbose_name = 'KPN Meeting'
        verbose_name_plural = 'KPN Meetings'

    def __str__(self):
        return f"{self.title} — {self.scheduled_start.strftime('%d %b %Y %H:%M')}"

    def get_attendance_summary(self):
        records = self.attendance_records.all()
        return {
            'total_expected': self.expected_participants.count(),
            'present': records.filter(status='PRESENT').count(),
            'late': records.filter(status='LATE').count(),
            'partial': records.filter(status='PARTIAL').count(),
            'absent': records.filter(status='ABSENT').count(),
            'total_confirmed': records.exclude(status='ABSENT').count(),
        }

    @property
    def is_active(self):
        return self.status == 'ACTIVE'

    @property
    def duration_minutes(self):
        if self.actual_start and self.actual_end:
            delta = self.actual_end - self.actual_start
            return int(delta.total_seconds() / 60)
        if self.scheduled_start and self.scheduled_end:
            delta = self.scheduled_end - self.scheduled_start
            return int(delta.total_seconds() / 60)
        return None


class MeetingAttendance(models.Model):
    """
    Records attendance for a KPN meeting.
    Status is based on when the member confirmed attendance via bot command /present.
    We record the confirmation time only — NOT voice-chat presence, which Telegram
    does not expose reliably via Bot API. This is clearly labeled as 'attendance confirmation'.
    """

    ATTENDANCE_STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('LATE', 'Late (confirmed after grace period)'),
        ('ABSENT', 'Absent'),
        ('PARTIAL', 'Partial Attendance'),
    ]

    meeting = models.ForeignKey(
        KPNMeeting,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meeting_attendances'
    )

    # Telegram identity at time of attendance (for non-linked users who confirm via bot)
    telegram_user_id = models.BigIntegerField(
        null=True, blank=True,
        help_text="Telegram user ID of the attendee"
    )

    status = models.CharField(
        max_length=10,
        choices=ATTENDANCE_STATUS_CHOICES,
        default='ABSENT'
    )

    # Attendance confirmation time — this is when the member clicked /present in Telegram
    # IMPORTANT: This is attendance CONFIRMATION time, not voice-chat join time
    confirmed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the member confirmed attendance via /present command"
    )

    # If technically measurable (e.g., future Telegram API improvements)
    joined_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When member joined the group chat/voice (if technically measurable)"
    )
    left_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When member left the group chat/voice (if technically measurable)"
    )
    measurable_duration_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Measurable participation duration in seconds (if technically available)"
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['meeting', 'user']
        ordering = ['status', 'confirmed_at']
        verbose_name = 'Meeting Attendance'
        verbose_name_plural = 'Meeting Attendance Records'

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.meeting.title} — {self.get_status_display()}"


class TelegramAuthState(models.Model):
    """
    CSRF/state tokens for Telegram Login Widget callbacks.
    Prevents replay attacks and CSRF during Telegram authentication.
    """
    state_token = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="The KPN user initiating Telegram connection (null for new registrants)"
    )
    session_key = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Telegram Auth State'
        verbose_name_plural = 'Telegram Auth States'
        indexes = [
            models.Index(fields=['state_token'], name='tg_state_idx'),
            models.Index(fields=['expires_at'], name='tg_state_exp_idx'),
        ]

    def __str__(self):
        return f"AuthState for {self.user or 'anonymous'} — expires {self.expires_at}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class AIRateLimit(models.Model):
    """
    Tracks AI assistant usage per Telegram user to prevent abuse.
    """
    telegram_user_id = models.BigIntegerField(unique=True)
    request_count_today = models.PositiveIntegerField(default=0)
    request_count_hour = models.PositiveIntegerField(default=0)
    last_request_at = models.DateTimeField(null=True, blank=True)
    last_hour_reset = models.DateTimeField(null=True, blank=True)
    last_day_reset = models.DateField(null=True, blank=True)
    is_blocked = models.BooleanField(default=False)
    blocked_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'AI Rate Limit'
        verbose_name_plural = 'AI Rate Limits'

    def __str__(self):
        return f"RateLimit for Telegram user {self.telegram_user_id}"


class AIProviderConfig(models.Model):
    """
    Configuration for AI API providers, allowing dynamic switching without code changes.
    """
    PROTOCOL_CHOICES = [
        ('openrouter', 'OpenRouter'),
        ('openai_compatible', 'OpenAI Compatible'),
        ('google', 'Google Gemini'),
    ]

    name = models.CharField(max_length=100, help_text="e.g., 'Groq', 'DeepSeek', 'OpenRouter'")
    protocol = models.CharField(max_length=50, choices=PROTOCOL_CHOICES, default='openai_compatible')
    base_url = models.URLField(blank=True, help_text="e.g., 'https://api.openai.com/v1' or 'https://api.groq.com/openai/v1'")
    api_key = models.CharField(max_length=255, blank=True, help_text="Provider API Key (if blank, falls back to ENV var based on protocol)")
    default_model = models.CharField(max_length=100, help_text="e.g., 'llama-3.1-8b-instant'")
    
    is_active = models.BooleanField(default=True, help_text="Whether this provider is enabled for fallback iteration")
    order = models.PositiveIntegerField(default=0, help_text="Lower number = higher priority during failover")

    supports_chat = models.BooleanField(default=True)
    supports_vision = models.BooleanField(default=False)
    supports_embeddings = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'AI Provider'
        verbose_name_plural = 'AI Providers'

    def __str__(self):
        return f"{self.name} ({self.get_protocol_display()})"


class BotKnowledgeBase(models.Model):
    """
    Dynamic Knowledge Base for the AI Assistant.
    Admins can paste organizational facts, constitution text, or rules here.
    The AI reads all active records to answer user questions.
    """
    topic = models.CharField(max_length=200, help_text="e.g., 'KPN Constitution', 'Event Rules', 'Membership Duties'")
    content = models.TextField(help_text="Paste the factual information here. The bot will read this to answer questions accurately.")
    is_active = models.BooleanField(default=True, help_text="Turn off to temporarily hide this info from the bot's brain.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bot Knowledge (Brain)"
        verbose_name_plural = "Bot Knowledge (Brain)"
        ordering = ['topic']

    def __str__(self):
        return self.topic

