from django.db import models
from django.conf import settings
import math


class Campaign(models.Model):

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
        ('GOVERNANCE', 'Government & Governance'),
        ('EMERGENCY', 'Emergency'),
        ('CIVIC', 'Civic'),
        ('GENERAL', 'General'),
    ]

    VERIFICATION_STATUS_CHOICES = [
        ('DEVELOPING', 'KPN Developing'),
        ('CONFIRMED', 'KPN Confirmed'),
        ('VERIFIED', 'KPN Verified'),
        ('COMMUNITY_ALERT', 'KPN Community Alert'),
    ]

    REPORTER_CREDIT_CHOICES = [
        ('KPN_REPORTER', 'KPN Community Reporter'),
        ('KPN_CORRESPONDENT', 'KPN Ward Correspondent'),
        ('KPN_LGA', 'KPN LGA Network Team'),
        ('KPN_STATE', 'KPN State Team'),
        ('KPN_EDITORIAL', 'KPN Editorial Team'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Review'),
        ('PUBLISHED', 'Published'),
        ('REJECTED', 'Returned for Revision'),
        ('ARCHIVED', 'Archived'),
    ]

    # Core fields (kept for backward compatibility)
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True)
    content = models.TextField(blank=True)
    featured_image = models.ImageField(upload_to='campaigns/', blank=True, null=True)

    # KPN 2.0 newsroom fields
    subheadline = models.CharField(
        max_length=500, blank=True,
        help_text="Short deck/subheadline that appears below the main headline"
    )
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='GENERAL'
    )
    location = models.CharField(
        max_length=200, blank=True,
        help_text="Specific community or location (e.g. Birnin Kebbi)"
    )
    lga = models.ForeignKey(
        'leadership.LGA', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='articles'
    )
    ward = models.ForeignKey(
        'leadership.Ward', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='articles'
    )
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUS_CHOICES, default='DEVELOPING'
    )
    reporter_credit = models.CharField(
        max_length=20, choices=REPORTER_CREDIT_CHOICES, default='KPN_REPORTER'
    )
    meta_description = models.CharField(
        max_length=160, blank=True,
        help_text="Short summary for search engines (max 160 characters)"
    )

    # Block editor content (Editor.js JSON)
    content_json = models.JSONField(
        null=True, blank=True,
        help_text="Block editor content stored as JSON"
    )

    # Workflow
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaigns'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_campaigns'
    )
    rejection_note = models.TextField(
        blank=True,
        help_text="Note from editor when returning article for revision"
    )

    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-published_at', '-created_at']
        verbose_name = 'Article'
        verbose_name_plural = 'Articles'
        indexes = [
            models.Index(fields=['status', 'category'], name='campaign_status_cat_idx'),
            models.Index(fields=['status', '-published_at'], name='campaign_status_pub_idx'),
            models.Index(fields=['status', 'lga'], name='campaign_status_lga_idx'),
        ]

    def __str__(self):
        return self.title

    def get_read_time(self):
        """Estimate reading time in minutes from block content."""
        words = 0
        if self.content_json and isinstance(self.content_json, dict):
            blocks = self.content_json.get('blocks', [])
            for block in blocks:
                data = block.get('data', {})
                text = data.get('text', '') or data.get('content', '')
                if isinstance(text, str):
                    words += len(text.split())
                items = data.get('items', [])
                for item in items:
                    if isinstance(item, str):
                        words += len(item.split())
        elif self.content:
            words = len(self.content.split())
        minutes = max(1, math.ceil(words / 200))
        return minutes

    def get_verification_badge_class(self):
        """Return Tailwind CSS colour class for the verification badge."""
        return {
            'VERIFIED': 'bg-green-100 text-green-800 border-green-300',
            'CONFIRMED': 'bg-blue-100 text-blue-800 border-blue-300',
            'DEVELOPING': 'bg-yellow-100 text-yellow-800 border-yellow-300',
            'COMMUNITY_ALERT': 'bg-red-100 text-red-800 border-red-300',
        }.get(self.verification_status, 'bg-gray-100 text-gray-800 border-gray-300')

    def get_category_colour(self):
        """Return Tailwind colour class for the category pill."""
        colour_map = {
            'EMERGENCY': 'bg-red-500',
            'COMMUNITY_ALERT': 'bg-red-500',
            'HEALTH': 'bg-pink-500',
            'SECURITY': 'bg-orange-500',
            'GOVERNANCE': 'bg-purple-600',
            'EDUCATION': 'bg-blue-500',
            'YOUTH': 'bg-cyan-500',
            'WOMEN': 'bg-fuchsia-500',
            'AGRICULTURE': 'bg-lime-600',
            'ENVIRONMENT': 'bg-green-600',
            'INFRASTRUCTURE': 'bg-amber-600',
            'MARKETS': 'bg-yellow-600',
            'CULTURE': 'bg-indigo-500',
            'TRADITIONAL': 'bg-stone-600',
            'CIVIC': 'bg-teal-600',
            'HUMAN_INTEREST': 'bg-rose-500',
            'COMMUNITY': 'bg-green-500',
        }
        return colour_map.get(self.category, 'bg-gray-500')

