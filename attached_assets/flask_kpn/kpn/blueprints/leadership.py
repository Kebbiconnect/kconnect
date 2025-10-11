from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import *

leadership = Blueprint('leadership', __name__)

@leadership.route('/manage')
@login_required
def manage():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    zones = Zone.query.all()
    lgas = LGA.query.all()
    wards = Ward.query.all()
    
    return render_template('leadership/manage.html', zones=zones, lgas=lgas, wards=wards)

@leadership.route('/approvals')
@login_required
def approvals():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get pending approvals that this user can handle
    query = User.query.filter_by(approval_status=ApprovalStatus.PENDING)
    
    if current_user.role_type == RoleType.ZONAL_COORDINATOR:
        query = query.filter_by(zone_id=current_user.zone_id, role_type=RoleType.LGA_LEADER)
    elif current_user.role_type == RoleType.LGA_LEADER:
        query = query.filter_by(lga_id=current_user.lga_id, role_type=RoleType.WARD_LEADER)
    
    pending_approvals = query.all()
    
    return render_template('leadership/approvals.html', pending_approvals=pending_approvals)

@leadership.route('/approve/<int:user_id>')
@login_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if current_user.can_approve_user(user):
        # Capture old status BEFORE changing it
        old_status = user.approval_status.value
        
        user.approval_status = ApprovalStatus.APPROVED
        db.session.commit()
        
        # Auto-log the approval action with correct old status
        try:
            from utils.staff_action_logger import log_approval
            log_approval(user, old_status=old_status, reason="User registration approved")
        except Exception as e:
            current_app.logger.error(f"Error auto-logging approval: {e}")
        
        flash(f'{user.full_name} has been approved successfully.', 'success')
    else:
        flash('You do not have permission to approve this user.', 'error')
    
    return redirect(url_for('leadership.approvals'))

@leadership.route('/reject/<int:user_id>')
@login_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if current_user.can_approve_user(user):
        # Capture old status BEFORE changing it
        old_status = user.approval_status.value
        
        user.approval_status = ApprovalStatus.REJECTED
        db.session.commit()
        
        # Auto-log the rejection action with correct old status
        try:
            from utils.staff_action_logger import log_rejection
            log_rejection(user, old_status=old_status, reason="User registration rejected")
        except Exception as e:
            current_app.logger.error(f"Error auto-logging rejection: {e}")
        
        flash(f'{user.full_name} has been rejected.', 'info')
    else:
        flash('You do not have permission to reject this user.', 'error')
    
    return redirect(url_for('leadership.approvals'))