from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    path('calendar/', views.event_calendar, name='event_calendar'),
    path('create/', views.create_event, name='create_event'),
    path('<int:pk>/', views.event_detail, name='event_detail'),
    path('<int:pk>/edit/', views.edit_event, name='edit_event'),
    path('<int:pk>/delete/', views.delete_event, name='delete_event'),
    
    path('<int:pk>/attendance/', views.manage_attendance, name='manage_attendance'),
    path('<int:pk>/attendance/<int:attendee_id>/toggle/', views.mark_individual_attendance, name='mark_individual_attendance'),
    path('attendance/logs/', views.view_attendance_logs, name='view_attendance_logs'),
    
    path('<int:pk>/minutes/create/', views.create_meeting_minutes, name='create_meeting_minutes'),
    path('<int:pk>/minutes/edit/', views.edit_meeting_minutes, name='edit_meeting_minutes'),
    path('<int:pk>/minutes/', views.view_meeting_minutes, name='view_meeting_minutes'),
    path('minutes/all/', views.all_meeting_minutes, name='all_meeting_minutes'),
]
