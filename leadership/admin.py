from django.contrib import admin
from .models import Zone, LGA, Ward, RoleDefinition

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']

@admin.register(LGA)
class LGAAdmin(admin.ModelAdmin):
    list_display = ['name', 'zone', 'created_at']
    list_filter = ['zone']
    search_fields = ['name']

@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ['name', 'lga', 'created_at']
    list_filter = ['lga__zone', 'lga']
    search_fields = ['name']

@admin.register(RoleDefinition)
class RoleDefinitionAdmin(admin.ModelAdmin):
    list_display = ['title', 'tier', 'seat_number']
    list_filter = ['tier']
    search_fields = ['title']
