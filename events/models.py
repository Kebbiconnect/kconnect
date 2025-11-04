from django.db import models
from django.conf import settings

class Event(models.Model):
    title = models.CharField(max_length=300)
    description = models.TextField()
    location = models.CharField(max_length=300)
    
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_events')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
    
    def __str__(self):
        return self.title


class EventAttendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='attendances')
    attendee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_attendances')
    
    present = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_attendances')
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['event', 'attendee']
        ordering = ['event', 'attendee__last_name']
    
    def __str__(self):
        return f"{self.attendee.get_full_name()} - {self.event.title}"


class MeetingMinutes(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name='minutes')
    content = models.TextField(help_text="Full text of the meeting minutes")
    summary = models.TextField(help_text="Brief summary of key points and decisions")
    
    attendees_present = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='attended_meetings', blank=True)
    
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_minutes')
    recorded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-recorded_at']
        verbose_name_plural = 'Meeting Minutes'
    
    def __str__(self):
        return f"Minutes: {self.event.title}"
