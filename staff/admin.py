from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from .models import User, DisciplinaryAction, WomensProgram, YouthProgram, WelfareProgram, Announcement

def approve_members(modeladmin, request, queryset):
    """Action to approve selected members"""
    approved_count = 0
    for user in queryset.filter(status='PENDING'):
        user.status = 'APPROVED'
        user.approved_by = request.user
        user.date_approved = timezone.now()
        user.save()
        approved_count += 1
    
    modeladmin.message_user(request, f'{approved_count} member(s) have been approved successfully.')
approve_members.short_description = "Approve selected members"

def suspend_members(modeladmin, request, queryset):
    """Action to suspend selected members"""
    suspended_count = queryset.update(status='SUSPENDED')
    modeladmin.message_user(request, f'{suspended_count} member(s) have been suspended.')
suspend_members.short_description = "Suspend selected members"

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'role_definition', 'status', 'zone', 'lga', 'ward', 'date_joined']
    list_filter = ['status', 'role', 'zone', 'lga', 'date_joined']
    search_fields = ['username', 'first_name', 'last_name', 'phone', 'email']
    actions = [approve_members, suspend_members]
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('KPN Information', {
            'fields': ('phone', 'bio', 'photo', 'role', 'status', 'zone', 'lga', 'ward', 'role_definition', 'facebook_verified', 'date_approved', 'approved_by')
        }),
    )
    
    def get_queryset(self, request):
        """Show pending members at the top"""
        qs = super().get_queryset(request)
        return qs.order_by('status', '-date_joined')

@admin.register(DisciplinaryAction)
class DisciplinaryActionAdmin(admin.ModelAdmin):
    list_display = ['user', 'action_type', 'issued_by', 'is_approved', 'created_at']
    list_filter = ['action_type', 'is_approved']
    search_fields = ['user__username', 'reason']

@admin.register(WomensProgram)
class WomensProgramAdmin(admin.ModelAdmin):
    list_display = ['title', 'program_type', 'status', 'get_scope', 'start_date', 'get_participant_count']
    list_filter = ['program_type', 'status', 'zone', 'lga']
    search_fields = ['title', 'description']
    filter_horizontal = ['participants']


@admin.register(YouthProgram)
class YouthProgramAdmin(admin.ModelAdmin):
    list_display = ['title', 'program_type', 'status', 'get_scope', 'start_date', 'get_participant_count']
    list_filter = ['program_type', 'status', 'zone', 'lga']
    search_fields = ['title', 'description']
    filter_horizontal = ['participants']


@admin.register(WelfareProgram)
class WelfareProgramAdmin(admin.ModelAdmin):
    list_display = ['title', 'program_type', 'status', 'get_scope', 'start_date', 'get_beneficiary_count', 'budget', 'funds_disbursed']
    list_filter = ['program_type', 'status', 'zone', 'lga']
    search_fields = ['title', 'description']
    filter_horizontal = ['beneficiaries']


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'scope', 'get_target_display', 'priority', 'is_active', 'created_by', 'created_at']
    list_filter = ['scope', 'priority', 'is_active', 'target_zone', 'target_lga', 'created_at']
    search_fields = ['title', 'content']
    readonly_fields = ['created_by', 'created_at', 'updated_at']
    
    fieldsets = [
        ('Announcement Details', {
            'fields': ('title', 'content', 'priority')
        }),
        ('Targeting', {
            'fields': ('scope', 'target_zone', 'target_lga', 'target_ward'),
            'description': 'Select the scope and target for this announcement. For GENERAL scope, leave all targets empty.'
        }),
        ('Activation & Expiration', {
            'fields': ('is_active', 'expires_at')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ['collapse']
        })
    ]
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)
