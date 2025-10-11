from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from models import db, User, DisciplinaryAction, RoleType
from datetime import datetime

disciplinary = Blueprint('disciplinary', __name__)

def can_manage_action(user, action):
    """Check if user can manage a disciplinary action"""
    if user.role_type == RoleType.ADMIN:
        return True
    elif user.role_type == RoleType.EXECUTIVE:
        return True
    elif user.id == action.issued_by_id:
        return True
    else:
        return False

def determine_scope(user):
    """Determine the scope of disciplinary action based on user role"""
    if user.role_type == RoleType.ADMIN:
        return 'STATE'
    elif user.role_type == RoleType.EXECUTIVE:
        return 'STATE'
    elif user.role_type == RoleType.ZONAL_COORDINATOR:
        return 'ZONE'
    elif user.role_type == RoleType.LGA_LEADER:
        return 'LGA'
    elif user.role_type == RoleType.WARD_LEADER:
        return 'WARD'
    else:
        return 'GENERAL'

@disciplinary.route('/')
@login_required
def view_actions():
    """View disciplinary actions"""
    # Only certain roles can view disciplinary actions
    if current_user.role_type == RoleType.GENERAL_MEMBER:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get actions based on user's role and jurisdiction
    if current_user.role_type == RoleType.ADMIN:
        # Admins see all actions
        actions = DisciplinaryAction.query.order_by(DisciplinaryAction.created_at.desc()).all()
    elif current_user.role_type == RoleType.EXECUTIVE:
        # Executives see state-level actions
        actions = DisciplinaryAction.query.order_by(DisciplinaryAction.created_at.desc()).all()
    elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
        # Zonal coordinators see actions in their zone
        actions = DisciplinaryAction.query.join(User).filter(
            User.zone_id == current_user.zone_id
        ).order_by(DisciplinaryAction.created_at.desc()).all()
    elif current_user.role_type == RoleType.LGA_LEADER:
        # LGA leaders see actions in their LGA
        actions = DisciplinaryAction.query.join(User).filter(
            User.lga_id == current_user.lga_id
        ).order_by(DisciplinaryAction.created_at.desc()).all()
    elif current_user.role_type == RoleType.WARD_LEADER:
        # Ward leaders see actions in their ward
        actions = DisciplinaryAction.query.join(User).filter(
            User.ward_id == current_user.ward_id
        ).order_by(DisciplinaryAction.created_at.desc()).all()
    else:
        actions = []
    
    # Calculate statistics
    stats = {
        'total': len(actions),
        'warnings': len([a for a in actions if a.action_type == 'warning']),
        'suspensions': len([a for a in actions if a.action_type == 'suspension']),
        'dismissals': len([a for a in actions if a.action_type == 'dismissal']),
        'active': len([a for a in actions if a.status == 'active']),
        'resolved': len([a for a in actions if a.status == 'resolved'])
    }
    
    return render_template('disciplinary/list.html', disciplinary_actions=actions, stats=stats)

@disciplinary.route('/create', methods=['GET', 'POST'])
@login_required
def create_action():
    """Create a new disciplinary action"""
    # Expand roles that can create disciplinary actions to include supervisors
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]:
        flash('You do not have permission to create disciplinary actions.', 'error')
        return redirect(url_for('disciplinary.view_actions'))
    
    if request.method == 'POST':
        user_id = request.form['user_id']
        action_type = request.form['action_type']
        reason = request.form['reason']
        
        # Validate jurisdiction - ensure user can only target users in their jurisdiction
        from auth_helpers import can_manage_user
        target_user = User.query.get(user_id)
        if not target_user or not can_manage_user(current_user, target_user):
            flash('You do not have permission to take disciplinary action against this user.', 'error')
            return redirect(url_for('disciplinary.create_action'))
        
        # Create disciplinary action
        action = DisciplinaryAction(
            user_id=user_id,
            issued_by_id=current_user.id,
            action_type=action_type,
            reason=reason
        )
        
        # Set approval requirements for dismissals
        if action_type == 'dismissal':
            # Check if dismissal requires approval based on current user's role
            if current_user.role_type != RoleType.ADMIN:
                action.approval_required = True
                action.approval_status = 'pending_approval'
                action.status = 'pending_dismissal'
            else:
                # Admin dismissals don't need approval
                action.approval_required = False
                action.approval_status = 'not_required'
                action.status = 'active'
        else:
            # Warnings and suspensions don't need approval
            action.approval_required = False
            action.approval_status = 'not_required'
            action.status = 'active'
        
        db.session.add(action)
        db.session.commit()
        
        if action_type == 'dismissal' and action.approval_required:
            flash('Dismissal proposal created and sent for approval.', 'info')
        else:
            flash('Disciplinary action created successfully.', 'success')
        
        return redirect(url_for('disciplinary.view_actions'))
    
    # GET request - show form
    # Get users based on current user's jurisdiction
    from auth_helpers import get_users_in_jurisdiction
    users = get_users_in_jurisdiction(current_user)
    
    return render_template('disciplinary/create.html', users=users)

@disciplinary.route('/resolve/<int:action_id>', methods=['POST'])
@login_required
def resolve_action(action_id):
    """Mark a disciplinary action as resolved"""
    action = DisciplinaryAction.query.get_or_404(action_id)
    
    # Check if user can resolve this action
    if not can_manage_action(current_user, action):
        flash('You do not have permission to resolve this action.', 'error')
        return redirect(url_for('disciplinary.view_actions'))
    
    action.status = 'resolved'
    action.resolved_at = datetime.utcnow()
    
    db.session.commit()
    
    flash('Disciplinary action marked as resolved.', 'success')
    return redirect(url_for('disciplinary.view_actions'))

@disciplinary.route('/pending_approvals')
@login_required
def pending_approvals():
    """View dismissals pending approval that current user can approve"""
    # Get dismissals that this user can approve
    pending_dismissals = []
    
    all_pending = DisciplinaryAction.query.filter_by(
        action_type='dismissal',
        approval_status='pending_approval'
    ).all()
    
    # Filter to only those this user can approve
    for action in all_pending:
        if action.can_approve(current_user):
            pending_dismissals.append(action)
    
    return render_template('disciplinary/pending_approvals.html', 
                         pending_dismissals=pending_dismissals)

@disciplinary.route('/approve/<int:action_id>', methods=['POST'])
@login_required
def approve_dismissal(action_id):
    """Approve a dismissal proposal"""
    action = DisciplinaryAction.query.get_or_404(action_id)
    
    if not action.can_approve(current_user):
        flash('You do not have permission to approve this dismissal.', 'error')
        return redirect(url_for('disciplinary.pending_approvals'))
    
    approval_notes = request.form.get('approval_notes', '').strip()
    
    # Approve the dismissal
    action.approval_status = 'approved'
    action.approved_by_id = current_user.id
    action.approved_at = datetime.utcnow()
    action.approval_notes = approval_notes
    action.status = 'active'  # Now becomes an active dismissal
    
    db.session.commit()
    
    # Log the approval action
    from utils.staff_action_logger import log_staff_action, StaffActionType
    try:
        log_staff_action(
            action_type=StaffActionType.DISMISSAL,
            target_user=action.user,
            performed_by=current_user,
            reason=f"Approved dismissal: {action.reason}",
            auto_generated=True
        )
    except Exception as e:
        current_app.logger.error(f"Error logging dismissal approval: {e}")
    
    flash(f'Dismissal of {action.user.full_name} has been approved.', 'success')
    return redirect(url_for('disciplinary.pending_approvals'))

@disciplinary.route('/reject/<int:action_id>', methods=['POST'])
@login_required
def reject_dismissal(action_id):
    """Reject a dismissal proposal"""
    action = DisciplinaryAction.query.get_or_404(action_id)
    
    if not action.can_approve(current_user):
        flash('You do not have permission to reject this dismissal.', 'error')
        return redirect(url_for('disciplinary.pending_approvals'))
    
    approval_notes = request.form.get('approval_notes', '').strip()
    
    # Reject the dismissal
    action.approval_status = 'rejected'
    action.approved_by_id = current_user.id
    action.approved_at = datetime.utcnow()
    action.approval_notes = approval_notes
    action.status = 'resolved'  # Mark as resolved since it's rejected
    action.resolved_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Dismissal proposal for {action.user.full_name} has been rejected.', 'info')
    return redirect(url_for('disciplinary.pending_approvals'))