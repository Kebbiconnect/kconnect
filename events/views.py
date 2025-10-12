from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from .models import Event, EventAttendance, MeetingMinutes
from .forms import EventForm, AttendanceForm, BulkAttendanceForm, MeetingMinutesForm
from staff.decorators import specific_role_required
from staff.models import User


@login_required
def event_calendar(request):
    upcoming_events = Event.objects.filter(start_date__gte=timezone.now()).order_by('start_date')
    past_events = Event.objects.filter(start_date__lt=timezone.now()).order_by('-start_date')[:10]
    
    context = {
        'upcoming_events': upcoming_events,
        'past_events': past_events,
    }
    
    return render(request, 'events/event_calendar.html', context)


@specific_role_required('Organizing Secretary')
def create_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            messages.success(request, f'Event "{event.title}" created successfully!')
            return redirect('events:event_detail', pk=event.pk)
    else:
        form = EventForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'events/create_event.html', context)


@specific_role_required('Organizing Secretary')
def edit_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, f'Event "{event.title}" updated successfully!')
            return redirect('events:event_detail', pk=event.pk)
    else:
        form = EventForm(instance=event)
    
    context = {
        'form': form,
        'event': event,
    }
    
    return render(request, 'events/edit_event.html', context)


@specific_role_required('Organizing Secretary')
def delete_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    
    if request.method == 'POST':
        event_title = event.title
        event.delete()
        messages.success(request, f'Event "{event_title}" has been deleted.')
        return redirect('events:event_calendar')
    
    context = {
        'event': event,
    }
    
    return render(request, 'events/delete_event.html', context)


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    attendances = event.attendances.all()
    
    try:
        minutes = event.minutes
    except MeetingMinutes.DoesNotExist:
        minutes = None
    
    context = {
        'event': event,
        'attendances': attendances,
        'minutes': minutes,
    }
    
    return render(request, 'events/event_detail.html', context)


@specific_role_required('Organizing Secretary')
def manage_attendance(request, pk):
    event = get_object_or_404(Event, pk=pk)
    
    if request.method == 'POST':
        form = BulkAttendanceForm(request.POST, event=event)
        if form.is_valid():
            count = 0
            for field_name, value in form.cleaned_data.items():
                if field_name.startswith('attendee_') and value:
                    attendee_id = field_name.split('_')[1]
                    attendee = User.objects.get(id=attendee_id)
                    
                    attendance, created = EventAttendance.objects.get_or_create(
                        event=event,
                        attendee=attendee,
                        defaults={
                            'present': True,
                            'recorded_by': request.user
                        }
                    )
                    
                    if not created:
                        attendance.present = True
                        attendance.recorded_by = request.user
                        attendance.save()
                    
                    count += 1
            
            messages.success(request, f'Attendance recorded for {count} member(s).')
            return redirect('events:event_detail', pk=event.pk)
    else:
        form = BulkAttendanceForm(event=event)
    
    existing_attendances = event.attendances.filter(present=True).values_list('attendee_id', flat=True)
    
    context = {
        'event': event,
        'form': form,
        'existing_attendances': list(existing_attendances),
    }
    
    return render(request, 'events/manage_attendance.html', context)


@specific_role_required('Organizing Secretary')
def mark_individual_attendance(request, pk, attendee_id):
    event = get_object_or_404(Event, pk=pk)
    attendee = get_object_or_404(User, id=attendee_id)
    
    attendance, created = EventAttendance.objects.get_or_create(
        event=event,
        attendee=attendee,
        defaults={
            'present': True,
            'recorded_by': request.user
        }
    )
    
    if not created:
        attendance.present = not attendance.present
        attendance.save()
    
    if attendance.present:
        messages.success(request, f'{attendee.get_full_name()} marked as present.')
    else:
        messages.info(request, f'{attendee.get_full_name()} marked as absent.')
    
    return redirect('events:event_detail', pk=event.pk)


@login_required
def view_attendance_logs(request):
    all_attendances = EventAttendance.objects.filter(present=True).select_related('event', 'attendee', 'recorded_by').order_by('-recorded_at')[:50]
    
    context = {
        'attendances': all_attendances,
    }
    
    return render(request, 'events/attendance_logs.html', context)


@specific_role_required('General Secretary')
def create_meeting_minutes(request, pk):
    event = get_object_or_404(Event, pk=pk)
    
    try:
        minutes = event.minutes
        messages.info(request, 'Minutes already exist for this event. Redirecting to edit page.')
        return redirect('events:edit_meeting_minutes', pk=event.pk)
    except MeetingMinutes.DoesNotExist:
        pass
    
    if request.method == 'POST':
        form = MeetingMinutesForm(request.POST)
        if form.is_valid():
            minutes = form.save(commit=False)
            minutes.event = event
            minutes.recorded_by = request.user
            
            if minutes.is_published:
                minutes.published_at = timezone.now()
            
            minutes.save()
            form.save_m2m()
            
            messages.success(request, 'Meeting minutes recorded successfully!')
            return redirect('events:view_meeting_minutes', pk=event.pk)
    else:
        attendees = event.attendances.filter(present=True).values_list('attendee', flat=True)
        form = MeetingMinutesForm(initial={'attendees_present': attendees})
    
    context = {
        'event': event,
        'form': form,
    }
    
    return render(request, 'events/create_meeting_minutes.html', context)


@specific_role_required('General Secretary')
def edit_meeting_minutes(request, pk):
    event = get_object_or_404(Event, pk=pk)
    minutes = get_object_or_404(MeetingMinutes, event=event)
    
    if request.method == 'POST':
        form = MeetingMinutesForm(request.POST, instance=minutes)
        if form.is_valid():
            minutes = form.save(commit=False)
            
            if minutes.is_published and not minutes.published_at:
                minutes.published_at = timezone.now()
            elif not minutes.is_published:
                minutes.published_at = None
            
            minutes.save()
            form.save_m2m()
            
            messages.success(request, 'Meeting minutes updated successfully!')
            return redirect('events:view_meeting_minutes', pk=event.pk)
    else:
        form = MeetingMinutesForm(instance=minutes)
    
    context = {
        'event': event,
        'minutes': minutes,
        'form': form,
    }
    
    return render(request, 'events/edit_meeting_minutes.html', context)


@login_required
def view_meeting_minutes(request, pk):
    event = get_object_or_404(Event, pk=pk)
    minutes = get_object_or_404(MeetingMinutes, event=event)
    
    context = {
        'event': event,
        'minutes': minutes,
    }
    
    return render(request, 'events/view_meeting_minutes.html', context)


@login_required
def all_meeting_minutes(request):
    all_minutes = MeetingMinutes.objects.filter(is_published=True).select_related('event', 'recorded_by').order_by('-recorded_at')
    
    context = {
        'all_minutes': all_minutes,
    }
    
    return render(request, 'events/all_meeting_minutes.html', context)
