from django.contrib import admin
from .models import FAQ, Report, Opportunity, OpportunityReport, CommunityInitiative, AdvocacyCampaign, AdvocacyActivity, CommunityReport, ImpactStory, Patron, IctAdminAssignment, IctAdminChange
from staff.models import User

@admin.register(IctAdminAssignment)
class IctAdminAssignmentAdmin(admin.ModelAdmin):
    """The ICT Admin assignment — the ONLY place it can be changed.

    Owner instruction + clarification (2026-11-24): the Super Admin
    operates only through the Django admin panel, so the holder is
    changed here and nowhere else — the ICT Admin console page is
    read-only, and no role on the website (not even the President)
    can move the assignment. The picker lists members and position
    holders only: super admin accounts are never offered as holder.
    The row is a singleton: it cannot be added twice or deleted.
    """
    list_display = ('user', 'updated_by', 'updated_at')
    fields = ('user',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'user':
            kwargs['queryset'] = User.objects.filter(
                is_superuser=False).order_by(
                    'last_name', 'first_name', 'username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        previous_user_id = None
        if change:
            previous_user_id = IctAdminAssignment.objects.filter(
                pk=obj.pk).values_list('user_id', flat=True).first()
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        if obj.user_id != previous_user_id:
            IctAdminChange.objects.create(
                previous_holder_id=previous_user_id,
                new_holder=obj.user, changed_by=request.user)

    def has_add_permission(self, request):
        # Singleton: the seed creates the one row; never a second.
        return not IctAdminAssignment.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IctAdminChange)
class IctAdminChangeAdmin(admin.ModelAdmin):
    """The ICT Admin change history — read-only audit, here and on
    the console page. Rows are written by the assignment's save_model
    and are never edited or deleted."""
    list_display = ('created_at', 'previous_holder', 'new_holder',
                    'changed_by')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'is_active')
    list_editable = ('order', 'is_active')

@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'deadline', 'is_featured')
    list_filter = ('category', 'status', 'is_featured')
    search_fields = ('title', 'provider')

@admin.register(OpportunityReport)
class OpportunityReportAdmin(admin.ModelAdmin):
    list_display = ('opportunity', 'status', 'reporter_name', 'created_at')
    list_filter = ('status',)
    search_fields = ('opportunity__title', 'reason')

@admin.register(CommunityInitiative)
class CommunityInitiativeAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'people_reached')
    list_filter = ('category', 'status')

@admin.register(AdvocacyCampaign)
class AdvocacyCampaignAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'is_active', 'created_at')
    list_filter = ('status', 'is_active')

@admin.register(AdvocacyActivity)
class AdvocacyActivityAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'date', 'entry')
    list_filter = ('campaign',)

@admin.register(CommunityReport)
class CommunityReportAdmin(admin.ModelAdmin):
    list_display = ('category', 'reporter_name', 'status', 'info_status', 'created_at')
    list_filter = ('status', 'info_status', 'category')
    search_fields = ('what_happened', 'reporter_name')

@admin.register(ImpactStory)
class ImpactStoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'date_achieved', 'is_published')
    list_filter = ('category', 'is_published')
    search_fields = ('title', 'description')


@admin.register(Patron)
class PatronAdmin(admin.ModelAdmin):
    """
    Admin for KPN Patrons (Grand Patron + regular Patrons).
    The biography is stored in full — the 20-word preview is UI-only.
    """
    list_display = ('full_name', 'patron_type', 'title', 'is_published', 'order')
    list_filter = ('patron_type', 'is_published')
    list_editable = ('is_published', 'order')
    search_fields = ('full_name', 'title', 'bio')
    ordering = ('patron_type', 'order', 'full_name')
    fields = ('patron_type', 'full_name', 'title', 'bio', 'photo', 'is_published', 'order')
    help_texts = {
        'bio': (
            'Enter the full biography. '
            'The website will automatically show only the first 20 words to visitors, '
            'with a "Read More" button to expand. '
            'Do NOT truncate biographies here — store the full text.'
        ),
    }
