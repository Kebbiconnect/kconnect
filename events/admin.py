from django.contrib import admin
from .models import Event, EventAttendance, MeetingMinutes


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'location', 'start_date', 'end_date', 'created_by', 'created_at']
    list_filter = ['start_date', 'created_at']
    search_fields = ['title', 'description', 'location']
    date_hierarchy = 'start_date'


@admin.register(EventAttendance)
class EventAttendanceAdmin(admin.ModelAdmin):
    list_display = ['event', 'attendee', 'present', 'recorded_by', 'recorded_at']
    list_filter = ['present', 'recorded_at']
    search_fields = ['event__title', 'attendee__first_name', 'attendee__last_name']


@admin.register(MeetingMinutes)
class MeetingMinutesAdmin(admin.ModelAdmin):
    list_display = ['event', 'recorded_by', 'is_published', 'published_at', 'recorded_at']
    list_filter = ['is_published', 'published_at', 'recorded_at']
    search_fields = ['event__title', 'content', 'summary']
    filter_horizontal = ['attendees_present']
