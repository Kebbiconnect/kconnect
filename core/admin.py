from django.contrib import admin
from .models import FAQ, Report, Opportunity, CommunityInitiative, AdvocacyCampaign, CommunityReport, ImpactStory, Patron

@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'is_active')
    list_editable = ('order', 'is_active')

@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'deadline', 'is_featured')
    list_filter = ('category', 'status', 'is_featured')
    search_fields = ('title', 'provider')

@admin.register(CommunityInitiative)
class CommunityInitiativeAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'people_reached')
    list_filter = ('category', 'status')

@admin.register(AdvocacyCampaign)
class AdvocacyCampaignAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'created_at')
    list_filter = ('is_active',)

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
