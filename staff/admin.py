from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, DisciplinaryAction, WomensProgram

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'status', 'zone', 'lga', 'ward']
    list_filter = ['role', 'status', 'zone', 'lga']
    search_fields = ['username', 'first_name', 'last_name', 'phone']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('KPN Information', {
            'fields': ('phone', 'bio', 'photo', 'role', 'status', 'zone', 'lga', 'ward', 'role_definition', 'facebook_verified', 'date_approved', 'approved_by')
        }),
    )

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
