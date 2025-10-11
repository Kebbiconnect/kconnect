from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import *
from utils.activity_tracker import log_activity, auto_track_duty_completion
from utils.enhanced_reminder_system import reminder_system, daily_reminder_job
from datetime import datetime, timedelta
from auth_helpers import get_users_in_jurisdiction, get_duties_in_jurisdiction, validate_duty_assignment

duty_logs = Blueprint('duty_logs', __name__)

@duty_logs.route('/')
@login_required
def view_duties():
    """View duties assigned to current user"""
    if current_user.role_type == RoleType.GENERAL_MEMBER:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get user's duties
    user_duties = DutyLog.query.filter_by(user_id=current_user.id).order_by(DutyLog.created_at.desc()).all()
    
    # Statistics
    total_duties = len(user_duties)
    completed_duties = sum(1 for duty in user_duties if duty.completion_status == 'completed')
    pending_duties = sum(1 for duty in user_duties if duty.completion_status == 'pending')
    overdue_duties = sum(1 for duty in user_duties if duty.completion_status == 'overdue')
    
    stats = {
        'total': total_duties,
        'completed': completed_duties,
        'pending': pending_duties,
        'overdue': overdue_duties,
        'completion_rate': round((completed_duties / total_duties * 100) if total_duties > 0 else 0, 1)
    }
    
    return render_template('duty_logs/view_duties.html', duties=user_duties, stats=stats)

@duty_logs.route('/create', methods=['GET', 'POST'])
@login_required
def create_duty():
    """Create a new duty assignment"""
    # Check if user has anyone they can assign duties to
    manageable_users = get_users_in_jurisdiction(current_user)
    if not manageable_users:
        flash('You do not have permission to create duties.', 'error')
        return redirect(url_for('duty_logs.view_duties'))
    
    if request.method == 'POST':
        user_id = request.form['user_id']
        duty_description = request.form['duty_description']
        due_date_str = request.form.get('due_date')
        
        # Validate assignment authorization
        is_valid, message = validate_duty_assignment(current_user, user_id)
        if not is_valid:
            flash(message, 'error')
            return redirect(url_for('duty_logs.create_duty'))
        
        due_date = None
        if due_date_str:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
        
        duty = DutyLog(
            user_id=user_id,
            duty_description=duty_description,
            due_date=due_date,
            completion_status='pending'
        )
        
        db.session.add(duty)
        db.session.commit()
        
        flash('Duty assigned successfully.', 'success')
        return redirect(url_for('duty_logs.manage_duties'))
    
    # Get users to assign duties to based on jurisdiction
    users = get_users_in_jurisdiction(current_user)
    
    return render_template('duty_logs/create_duty.html', users=users)

@duty_logs.route('/manage')
@login_required
def manage_duties():
    """Manage all duty assignments"""
    # Check if user has permission to manage duties (can assign to others)
    manageable_users = get_users_in_jurisdiction(current_user)
    if not manageable_users and current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied. You do not have permission to manage duties.', 'error')
        return redirect(url_for('duty_logs.view_duties'))
    
    # Get all duties based on user's role and jurisdiction
    duties = get_duties_in_jurisdiction(current_user).all()
    
    return render_template('duty_logs/manage_duties.html', duties=duties)

@duty_logs.route('/complete/<int:duty_id>', methods=['POST'])
@login_required
def complete_duty(duty_id):
    """Mark a duty as completed"""
    duty = DutyLog.query.get_or_404(duty_id)
    
    # Only the assigned user can complete their duty
    if duty.user_id != current_user.id:
        flash('You can only complete your own duties.', 'error')
        return redirect(url_for('duty_logs.view_duties'))
    
    duty.completion_status = 'completed'
    duty.completed_date = datetime.utcnow()
    db.session.commit()
    
    # Track duty completion activity
    try:
        auto_track_duty_completion(duty_id)
    except Exception as e:
        print(f"Error tracking duty completion: {str(e)}")
    
    flash('Duty marked as completed.', 'success')
    return redirect(url_for('duty_logs.view_duties'))

@duty_logs.route('/discipline')
@login_required
def view_discipline():
    """View disciplinary actions for current user"""
    if current_user.role_type == RoleType.GENERAL_MEMBER:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get user's disciplinary actions
    user_actions = DisciplinaryAction.query.filter_by(user_id=current_user.id).order_by(DisciplinaryAction.created_at.desc()).all()
    
    return render_template('duty_logs/discipline.html', actions=user_actions)

@duty_logs.route('/discipline/create', methods=['GET', 'POST'])
@login_required
def create_disciplinary_action():
    """Create a disciplinary action"""
    # Only admins and executives can create disciplinary actions
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('You do not have permission to create disciplinary actions.', 'error')
        return redirect(url_for('duty_logs.view_discipline'))
    
    if request.method == 'POST':
        user_id = request.form['user_id']
        action_type = request.form['action_type']
        reason = request.form['reason']
        
        action = DisciplinaryAction(
            user_id=user_id,
            action_type=action_type,
            reason=reason,
            issued_by_id=current_user.id,
            status='active'
        )
        
        db.session.add(action)
        db.session.commit()
        
        flash(f'Disciplinary action ({action_type}) issued successfully.', 'success')
        return redirect(url_for('duty_logs.manage_discipline'))
    
    # Get users for disciplinary action
    users = User.query.filter(User.role_type != RoleType.GENERAL_MEMBER).all()
    
    return render_template('duty_logs/create_disciplinary_action.html', users=users)

@duty_logs.route('/discipline/manage')
@login_required
def manage_discipline():
    """Manage all disciplinary actions"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('duty_logs.view_discipline'))
    
    actions = DisciplinaryAction.query.order_by(DisciplinaryAction.created_at.desc()).all()
    
    return render_template('duty_logs/manage_discipline.html', actions=actions)

@duty_logs.route('/api/check-overdue')
@login_required
def check_overdue_duties():
    """API endpoint to check and update overdue duties"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'error': 'Access denied'}), 403
    
    # Find overdue duties
    today = datetime.utcnow().date()
    overdue_duties = DutyLog.query.filter(
        DutyLog.due_date < today,
        DutyLog.completion_status == 'pending'
    ).all()
    
    # Update to overdue status
    for duty in overdue_duties:
        duty.completion_status = 'overdue'
    
    db.session.commit()
    
    return jsonify({
        'updated': len(overdue_duties),
        'message': f'{len(overdue_duties)} duties marked as overdue'
    })

@duty_logs.route('/api/send-reminders', methods=['POST'])
@login_required
def send_duty_reminders():
    """API endpoint to send email reminders for overdue duties"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Process overdue duties and send reminders
        stats = reminder_system.process_overdue_duties()
        
        return jsonify({
            'success': True,
            'message': f'Processed {stats["overdue_found"]} overdue duties, sent {stats["reminders_sent"]} email reminders',
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@duty_logs.route('/api/run-daily-review', methods=['POST'])
@login_required
def run_daily_staff_review():
    """API endpoint to run comprehensive daily staff review"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Run comprehensive staff review
        stats = daily_reminder_job()
        
        return jsonify({
            'success': True,
            'message': f'Daily review completed: {stats.get("total_staff", 0)} staff checked, {stats.get("status_changes", 0)} status changes',
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@duty_logs.route('/api/send-announcement', methods=['POST'])
@login_required
def send_bulk_announcement():
    """API endpoint to send bulk announcements to staff"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        subject = data.get('subject', '')
        message = data.get('message', '')
        target_roles = data.get('roles', [])
        
        if not subject or not message:
            return jsonify({'error': 'Subject and message are required'}), 400
        
        # Convert role strings to RoleType enums
        role_types = []
        for role_str in target_roles:
            try:
                # RoleType enum values are lowercase
                role_types.append(RoleType(role_str.lower()))
            except ValueError:
                return jsonify({'error': f'Invalid role: {role_str}'}), 400
        
        # Send bulk announcements
        stats = reminder_system.send_bulk_announcements(
            staff_roles=role_types,
            subject=subject,
            message=message
        )
        
        return jsonify({
            'success': True,
            'message': f'Announcement sent to {stats["emails_sent"]} recipients',
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@duty_logs.route('/admin/reminder-dashboard')
@login_required
def reminder_dashboard():
    """Admin dashboard for reminder system management"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get recent reminder statistics
    today = datetime.utcnow().date()
    
    # Count overdue duties
    overdue_duties = DutyLog.query.filter(
        DutyLog.due_date < today,
        DutyLog.completion_status.in_(['pending', 'overdue'])
    ).count()
    
    # Count upcoming duties (next 7 days)
    upcoming_duties = DutyLog.query.filter(
        DutyLog.due_date.between(today, today + timedelta(days=7)),
        DutyLog.completion_status == 'pending'
    ).count()
    
    # Staff status breakdown
    staff_stats = {
        'total': User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER
        ).count(),
        'active': User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.staff_status == StaffStatus.ACTIVE
        ).count(),
        'irregular': User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.staff_status == StaffStatus.IRREGULAR
        ).count(),
        'inactive': User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.staff_status == StaffStatus.INACTIVE
        ).count()
    }
    
    return render_template('duty_logs/reminder_dashboard.html', 
                         overdue_duties=overdue_duties,
                         upcoming_duties=upcoming_duties,
                         staff_stats=staff_stats)