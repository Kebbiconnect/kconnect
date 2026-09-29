from django.contrib import admin
from django.contrib import messages
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from .models import TelegramMembership, KPNMeeting, MeetingAttendance, TelegramAuthState, AIRateLimit, AIProviderConfig, BotKnowledgeBase


@admin.register(TelegramMembership)
class TelegramMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'telegram_user_id', 'telegram_username', 'telegram_status', 'is_verified', 'last_checked_at')
    list_filter = ('is_verified', 'telegram_status', 'last_checked_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'telegram_username', 'telegram_user_id')
    readonly_fields = ('created_at', 'updated_at')
    
    actions = ['force_verify']
    
    def force_verify(self, request, queryset):
        from .services import verify_telegram_membership
        count = 0
        for tm in queryset:
            res = verify_telegram_membership(tm.telegram_user_id)
            if res['success']:
                count += 1
        self.message_user(request, f"Successfully triggered verification for {count} member(s).")
    force_verify.short_description = "Force re-verification with Telegram"


class MeetingAttendanceInline(admin.TabularInline):
    model = MeetingAttendance
    extra = 0
    readonly_fields = ('confirmed_at',)


@admin.register(KPNMeeting)
class KPNMeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting_type', 'status', 'scheduled_start', 'get_total_confirmed')
    list_filter = ('status', 'meeting_type', 'scheduled_start')
    search_fields = ('title', 'description')
    filter_horizontal = ('expected_participants',)
    inlines = [MeetingAttendanceInline]
    
    def get_total_confirmed(self, obj):
        return obj.attendance_records.exclude(status='ABSENT').count()
    get_total_confirmed.short_description = "Confirmed Attendees"


@admin.register(MeetingAttendance)
class MeetingAttendanceAdmin(admin.ModelAdmin):
    list_display = ('meeting', 'user', 'status', 'confirmed_at')
    list_filter = ('status', 'meeting__status', 'meeting__meeting_type')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'meeting__title')


@admin.register(AIRateLimit)
class AIRateLimitAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'request_count_today', 'request_count_hour', 'is_blocked', 'last_request_at')
    list_filter = ('is_blocked', 'last_day_reset')
    search_fields = ('telegram_user_id', 'blocked_reason')


@admin.register(TelegramAuthState)
class TelegramAuthStateAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used', 'is_expired')
    list_filter = ('used', 'created_at')
    readonly_fields = ('state_token', 'session_key')


@admin.register(AIProviderConfig)
class AIProviderConfigAdmin(admin.ModelAdmin):
    """
    Admin interface for managing AI Provider configurations.

    Supports any OpenAI-compatible provider (Groq, DeepSeek, Together AI, Mistral,
    custom self-hosted, etc.) as well as OpenRouter and Google Gemini.

    API keys are stored server-side only. They are never exposed to the frontend.
    """
    list_display = (
        'name', 'protocol', 'default_model', 'is_active',
        'order', 'supports_chat', 'supports_vision', 'test_connection_button',
    )
    list_filter = ('protocol', 'is_active', 'supports_chat', 'supports_vision')
    list_editable = ('is_active', 'order')
    search_fields = ('name', 'default_model', 'base_url')
    ordering = ('order', 'name')

    fieldsets = (
        ('Provider Identity', {
            'fields': ('name', 'protocol', 'is_active', 'order'),
            'description': (
                'Configure the provider name, protocol, and priority order. '
                'Lower "order" = higher priority when falling back through providers.'
            ),
        }),
        ('API Credentials (Server-Side Only)', {
            'fields': ('api_key', 'base_url', 'default_model'),
            'description': (
                'API keys are stored server-side and NEVER exposed to the browser, '
                'templates, or JavaScript. For OpenAI-compatible providers, set the '
                'base URL to the provider\'s API endpoint (e.g. https://api.groq.com/openai/v1). '
                'Leave base_url blank for OpenRouter and Google (their URLs are built-in). '
                'If api_key is blank, the system falls back to the corresponding ENV variable.'
            ),
        }),
        ('Capabilities', {
            'fields': ('supports_chat', 'supports_vision', 'supports_embeddings'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('created_at', 'updated_at')

    def test_connection_button(self, obj):
        return format_html(
            '<button type="button" '
            'onclick="kpnTestProvider({})" '
            'style="padding:3px 10px;background:#417690;color:#fff;border:none;'
            'border-radius:4px;cursor:pointer;font-size:12px;">'
            'Test</button>',
            obj.pk,
        )
    test_connection_button.short_description = 'Test'
    test_connection_button.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'test-provider/<int:pk>/',
                self.admin_site.admin_view(self.test_provider_view),
                name='telegram_integration_aiproviderconfig_test',
            ),
        ]
        return custom + urls

    def test_provider_view(self, request, pk):
        """
        Secure backend endpoint: tests an AI provider configuration.
        Only accessible by staff. API keys are NEVER returned in the response.
        """
        if not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

        try:
            provider = AIProviderConfig.objects.get(pk=pk)
        except AIProviderConfig.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Provider not found.'}, status=404)

        from .ai import test_provider_connection
        result = test_provider_connection(provider)
        return JsonResponse(result)

    class Media:
        js = ('admin/js/kpn_provider_test.js',)


@admin.register(BotKnowledgeBase)
class BotKnowledgeBaseAdmin(admin.ModelAdmin):
    """
    Admin interface for adding text to the bot's memory.
    """
    list_display = ('topic', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('topic', 'content')
    ordering = ('topic',)
