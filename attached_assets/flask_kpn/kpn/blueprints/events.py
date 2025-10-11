from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import *
from datetime import datetime

events = Blueprint('events', __name__)

@events.route('/')
@login_required
def list_events():
    """List events based on user's access level"""
    if current_user.role_type == RoleType.GENERAL_MEMBER:
        flash('Access denied. Events are for staff members only.', 'error')
        return redirect(url_for('core.home'))
    
    # Filter events based on user's jurisdiction
    query = Event.query
    
    if current_user.role_type == RoleType.WARD_LEADER:
        query = query.filter(
            (Event.scope == 'state') |
            (Event.zone_id == current_user.zone_id) |
            (Event.lga_id == current_user.lga_id) |
            (Event.ward_id == current_user.ward_id)
        )
    elif current_user.role_type == RoleType.LGA_LEADER:
        query = query.filter(
            (Event.scope == 'state') |
            (Event.zone_id == current_user.zone_id) |
            (Event.lga_id == current_user.lga_id)
        )
    elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
        query = query.filter(
            (Event.scope == 'state') |
            (Event.zone_id == current_user.zone_id)
        )
    
    events = query.order_by(Event.event_date.desc()).all()
    
    # Categorize events
    upcoming_events = [e for e in events if e.event_date >= datetime.utcnow()]
    past_events = [e for e in events if e.event_date < datetime.utcnow()]
    
    return render_template('events/list.html', 
                         upcoming_events=upcoming_events, 
                         past_events=past_events)

@events.route('/manage')
@login_required
def manage():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get events based on user's scope
    query = Event.query
    
    if current_user.role_type == RoleType.ZONAL_COORDINATOR:
        query = query.filter_by(zone_id=current_user.zone_id)
    elif current_user.role_type == RoleType.LGA_LEADER:
        query = query.filter_by(lga_id=current_user.lga_id)
    elif current_user.role_type == RoleType.WARD_LEADER:
        query = query.filter_by(ward_id=current_user.ward_id)
    
    events = query.order_by(Event.event_date.desc()).all()
    return render_template('events/manage.html', events=events)

@events.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    if request.method == 'POST':
        meeting_type = request.form.get('meeting_type', 'in_person')
        meeting_url = request.form.get('meeting_url', '').strip()
        location = request.form.get('location', '').strip()
        
        # Server-side validation for meeting types
        if meeting_type not in ['in_person', 'zoom', 'whatsapp', 'hybrid']:
            flash('Invalid meeting type selected.', 'error')
            zones = Zone.query.all()
            return render_template('events/create.html', zones=zones)
        
        # Validate required fields based on meeting type
        if meeting_type in ['zoom', 'whatsapp', 'hybrid']:
            if not meeting_url:
                flash('Meeting link is required for online and hybrid events.', 'error')
                zones = Zone.query.all()
                return render_template('events/create.html', zones=zones)
            
            # Basic URL validation
            if not (meeting_url.startswith('http://') or meeting_url.startswith('https://')):
                flash('Meeting link must be a valid URL (starting with http:// or https://).', 'error')
                zones = Zone.query.all()
                return render_template('events/create.html', zones=zones)
        
        if meeting_type in ['in_person', 'hybrid']:
            if not location:
                flash('Location is required for in-person and hybrid events.', 'error')
                zones = Zone.query.all()
                return render_template('events/create.html', zones=zones)
        
        event = Event(
            title=request.form['title'],
            description=request.form.get('description', ''),
            location=location,
            event_date=datetime.strptime(request.form['event_date'], '%Y-%m-%dT%H:%M'),
            created_by_id=current_user.id,
            scope=request.form['scope'],
            meeting_type=meeting_type,
            meeting_url=meeting_url,
            meeting_id=request.form.get('meeting_id', '').strip(),
            meeting_password=request.form.get('meeting_password', '').strip()
        )
        
        # Set scope-specific IDs based on current user's role and scope
        if event.scope == 'zone' and current_user.zone_id:
            event.zone_id = current_user.zone_id
        elif event.scope == 'lga' and current_user.lga_id:
            event.lga_id = current_user.lga_id
        elif event.scope == 'ward' and current_user.ward_id:
            event.ward_id = current_user.ward_id
        
        db.session.add(event)
        db.session.commit()
        
        flash('Event created successfully.', 'success')
        return redirect(url_for('events.manage'))
    
    # Pass zones data for the location dropdowns
    zones = Zone.query.all()
    return render_template('events/create.html', zones=zones)

@events.route('/<int:event_id>')
@login_required
def view_event(event_id):
    """View event details with attendance marking interface"""
    if current_user.role_type == RoleType.GENERAL_MEMBER:
        flash('Access denied. Events are for staff members only.', 'error')
        return redirect(url_for('core.home'))
    
    event = Event.query.get_or_404(event_id)
    
    # Check if user can see this event based on scope and jurisdiction
    can_see_event = False
    if event.scope == 'state':
        can_see_event = True
    elif event.scope == 'zone' and current_user.zone_id == event.zone_id:
        can_see_event = True
    elif event.scope == 'lga' and current_user.lga_id == event.lga_id:
        can_see_event = True
    elif event.scope == 'ward' and current_user.ward_id == event.ward_id:
        can_see_event = True
    elif current_user.role_type in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        can_see_event = True
    
    if not can_see_event:
        flash('You do not have permission to view this event.', 'error')
        return redirect(url_for('events.list_events'))
    
    # Get user's attendance status
    user_attendance = event.user_attendance_status(current_user.id)
    
    # Get attendance statistics
    attending_count = event.get_attendance_count()
    not_attending_count = event.get_non_attendance_count()
    
    return render_template('events/view.html', 
                         event=event, 
                         user_attendance=user_attendance,
                         attending_count=attending_count,
                         not_attending_count=not_attending_count)

@events.route('/<int:event_id>/mark_attendance', methods=['POST'])
@login_required
def mark_attendance(event_id):
    """Mark attendance for an event"""
    if current_user.role_type == RoleType.GENERAL_MEMBER:
        flash('Access denied. Events are for staff members only.', 'error')
        return redirect(url_for('core.home'))
    
    event = Event.query.get_or_404(event_id)
    
    # Check if user can see this event based on scope and jurisdiction (same as view_event)
    can_see_event = False
    if event.scope == 'state':
        can_see_event = True
    elif event.scope == 'zone' and current_user.zone_id == event.zone_id:
        can_see_event = True
    elif event.scope == 'lga' and current_user.lga_id == event.lga_id:
        can_see_event = True
    elif event.scope == 'ward' and current_user.ward_id == event.ward_id:
        can_see_event = True
    elif current_user.role_type in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        can_see_event = True
    
    if not can_see_event:
        flash('You do not have permission to mark attendance for this event.', 'error')
        return redirect(url_for('events.list_events'))
    
    attendance_status = request.form.get('attendance_status')
    notes = request.form.get('notes', '')
    
    if attendance_status not in ['attending', 'not_attending', 'maybe']:
        flash('Invalid attendance status.', 'error')
        return redirect(url_for('events.view_event', event_id=event_id))
    
    # Check or create attendance record
    attendance = EventAttendance.query.filter_by(
        event_id=event_id, 
        user_id=current_user.id
    ).first()
    
    if attendance:
        # Update existing record
        attendance.attendance_status = attendance_status
        attendance.notes = notes
        attendance.marked_by_id = current_user.id
        attendance.updated_at = datetime.utcnow()
    else:
        # Create new record
        attendance = EventAttendance(
            event_id=event_id,
            user_id=current_user.id,
            attendance_status=attendance_status,
            marked_by_id=current_user.id,
            notes=notes
        )
        db.session.add(attendance)
    
    db.session.commit()
    
    # Log activity
    activity = ActivityLog(
        user_id=current_user.id,
        activity_type='event_attendance_marked',
        activity_description=f"Marked attendance as '{attendance_status}' for event: {event.title}",
        event_id=event_id,
        points_earned=5 if attendance_status == 'attending' else 0
    )
    db.session.add(activity)
    db.session.commit()
    
    # Update member stats
    if current_user.member_stats:
        if attendance_status == 'attending':
            current_user.member_stats.events_attended += 1
        current_user.member_stats.updated_at = datetime.utcnow()
        db.session.commit()
    
    status_text = {
        'attending': 'attending',
        'not_attending': 'not attending',
        'maybe': 'maybe attending'
    }
    
    flash(f'Your attendance has been marked as {status_text[attendance_status]}.', 'success')
    return redirect(url_for('events.view_event', event_id=event_id))

@events.route('/<int:event_id>/attendance')
@login_required
def view_attendance(event_id):
    """View attendance list for an event (organizers and supervisors only)"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]:
        flash('Access denied. Only organizers and supervisors can view attendance lists.', 'error')
        return redirect(url_for('events.view_event', event_id=event_id))
    
    event = Event.query.get_or_404(event_id)
    
    # Get all attendance records for this event
    attendance_records = EventAttendance.query.filter_by(event_id=event_id).join(User).order_by(User.full_name).all()
    
    # Group by attendance status
    attending = [a for a in attendance_records if a.attendance_status == 'attending']
    not_attending = [a for a in attendance_records if a.attendance_status == 'not_attending']
    maybe_attending = [a for a in attendance_records if a.attendance_status == 'maybe']
    
    # Get users that the current user can manage for marking attendance
    from auth_helpers import get_users_in_jurisdiction
    manageable_users = get_users_in_jurisdiction(current_user)
    
    return render_template('events/attendance.html',
                         event=event,
                         attending=attending,
                         not_attending=not_attending,
                         maybe_attending=maybe_attending,
                         manageable_users=manageable_users)

@events.route('/<int:event_id>/attendance/mark', methods=['POST'])
@login_required
def mark_member_attendance(event_id):
    """Mark attendance for a member (supervisors only)"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]:
        flash('Access denied. Only supervisors can mark attendance for members.', 'error')
        return redirect(url_for('events.view_event', event_id=event_id))
    
    event = Event.query.get_or_404(event_id)
    user_id = request.form.get('user_id')
    attendance_status = request.form.get('attendance_status')
    notes = request.form.get('notes', '')
    
    if not user_id or attendance_status not in ['attending', 'not_attending']:
        flash('Invalid attendance data.', 'error')
        return redirect(url_for('events.view_attendance', event_id=event_id))
    
    # Verify supervisor can manage this user
    from auth_helpers import can_manage_user
    target_user = User.query.get(user_id)
    if not target_user or not can_manage_user(current_user, target_user):
        flash('You do not have permission to mark attendance for this user.', 'error')
        return redirect(url_for('events.view_attendance', event_id=event_id))
    
    # Check or create attendance record
    attendance = EventAttendance.query.filter_by(
        event_id=event_id, 
        user_id=user_id
    ).first()
    
    if attendance:
        attendance.attendance_status = attendance_status
        attendance.notes = notes
        attendance.marked_by_id = current_user.id
        attendance.updated_at = datetime.utcnow()
    else:
        attendance = EventAttendance(
            event_id=event_id,
            user_id=user_id,
            attendance_status=attendance_status,
            marked_by_id=current_user.id,
            notes=notes
        )
        db.session.add(attendance)
    
    db.session.commit()
    
    # Log activity for the attended user
    activity = ActivityLog(
        user_id=user_id,
        activity_type='event_attendance_marked',
        activity_description=f"Attendance marked as '{attendance_status}' for event: {event.title} (marked by {current_user.full_name})",
        event_id=event_id,
        points_earned=5 if attendance_status == 'attending' else 0
    )
    db.session.add(activity)
    db.session.commit()
    
    flash(f'Attendance marked for {target_user.full_name}.', 'success')
    return redirect(url_for('events.view_attendance', event_id=event_id))

# API endpoints for location dropdowns
@events.route('/api/lgas/<int:zone_id>')
def get_lgas(zone_id):
    """API endpoint to get LGAs for a zone"""
    lgas = LGA.query.filter_by(zone_id=zone_id).all()
    return jsonify([{'id': lga.id, 'name': lga.name} for lga in lgas])

@events.route('/api/wards/<int:lga_id>')
def get_wards(lga_id):
    """API endpoint to get wards for an LGA"""
    wards = Ward.query.filter_by(lga_id=lga_id).all()
    return jsonify([{'id': ward.id, 'name': ward.name} for ward in wards])