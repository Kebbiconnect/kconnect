"""
Auto-duty logging system for staff management actions
Automatically logs promotions, demotions, approvals, dismissals, etc.
"""

from models import db, StaffActionLog, StaffActionType, User, DutyLog, ApprovalStatus, RoleType, StaffStatus
from datetime import datetime, timedelta
from flask import current_app
from flask_login import current_user


def log_staff_action(action_type: StaffActionType, target_user: User, 
                    performed_by: User = None, reason: str = None,
                    old_role_type: str = None, new_role_type: str = None,
                    old_role_title: str = None, new_role_title: str = None,
                    old_approval_status: str = None, new_approval_status: str = None,
                    old_zone_id: int = None, new_zone_id: int = None,
                    old_lga_id: int = None, new_lga_id: int = None,
                    old_ward_id: int = None, new_ward_id: int = None,
                    auto_generated: bool = True) -> StaffActionLog:
    """
    Log a staff management action to the database
    
    Args:
        action_type: Type of action performed
        target_user: User who was affected by the action
        performed_by: User who performed the action (defaults to current_user)
        reason: Optional reason for the action
        old_role_type: Previous role type (for role changes)
        new_role_type: New role type (for role changes)
        old_role_title: Previous role title
        new_role_title: New role title
        old_approval_status: Previous approval status
        new_approval_status: New approval status
        old_zone_id: Previous zone assignment
        new_zone_id: New zone assignment
        old_lga_id: Previous LGA assignment
        new_lga_id: New LGA assignment
        old_ward_id: Previous ward assignment
        new_ward_id: New ward assignment
        auto_generated: Whether this log was automatically generated
        
    Returns:
        StaffActionLog: The created log entry
    """
    try:
        if performed_by is None:
            performed_by = current_user
        
        # Generate action description
        action_description = _generate_action_description(
            action_type, target_user, performed_by, 
            old_role_type, new_role_type, old_approval_status, new_approval_status
        )
        
        # Create the log entry
        staff_action_log = StaffActionLog(
            action_type=action_type,
            action_description=action_description,
            performed_by_id=performed_by.id,
            target_user_id=target_user.id,
            old_role_type=old_role_type,
            new_role_type=new_role_type,
            old_role_title=old_role_title,
            new_role_title=new_role_title,
            old_approval_status=old_approval_status,
            new_approval_status=new_approval_status,
            old_zone_id=old_zone_id,
            new_zone_id=new_zone_id,
            old_lga_id=old_lga_id,
            new_lga_id=new_lga_id,
            old_ward_id=old_ward_id,
            new_ward_id=new_ward_id,
            reason=reason,
            auto_generated=auto_generated
        )
        
        db.session.add(staff_action_log)
        
        # Also create a duty log entry for the target user
        duty_description = f"Staff Action: {action_description}"
        if reason:
            duty_description += f" - Reason: {reason}"
        
        duty_log = DutyLog(
            user_id=target_user.id,
            duty_description=duty_description,
            completion_status='completed',  # Administrative actions are automatically completed
            completed_date=datetime.utcnow()
        )
        
        db.session.add(duty_log)
        
        # Update user activity and status (but not for punitive actions)
        if action_type not in [StaffActionType.REJECTION, StaffActionType.DISMISSAL]:
            target_user.update_activity_date()
            target_user.update_staff_status()
        
        db.session.commit()
        
        current_app.logger.info(
            f"Staff action logged: {action_type.value} performed by {performed_by.full_name} "
            f"on {target_user.full_name}. Description: {action_description}"
        )
        
        return staff_action_log
        
    except Exception as e:
        current_app.logger.error(f"Error logging staff action: {e}")
        db.session.rollback()
        return None


def log_promotion(target_user: User, old_role: str, new_role: str, 
                 performed_by: User = None, reason: str = None) -> StaffActionLog:
    """Log a user promotion"""
    return log_staff_action(
        action_type=StaffActionType.PROMOTION,
        target_user=target_user,
        performed_by=performed_by,
        reason=reason,
        old_role_type=old_role,
        new_role_type=new_role
    )


def log_demotion(target_user: User, old_role: str, new_role: str, 
                performed_by: User = None, reason: str = None) -> StaffActionLog:
    """Log a user demotion"""
    return log_staff_action(
        action_type=StaffActionType.DEMOTION,
        target_user=target_user,
        performed_by=performed_by,
        reason=reason,
        old_role_type=old_role,
        new_role_type=new_role
    )


def log_approval(target_user: User, old_status: str = None, performed_by: User = None, 
                reason: str = None) -> StaffActionLog:
    """Log a user approval"""
    # Capture the real old status if not provided
    if old_status is None:
        old_status = target_user.approval_status.value if target_user.approval_status else "PENDING"
    
    return log_staff_action(
        action_type=StaffActionType.APPROVAL,
        target_user=target_user,
        performed_by=performed_by,
        reason=reason,
        old_approval_status=old_status,
        new_approval_status="APPROVED"
    )


def log_rejection(target_user: User, old_status: str = None, performed_by: User = None, 
                 reason: str = None) -> StaffActionLog:
    """Log a user rejection/dismissal"""
    # Capture the real old status if not provided
    if old_status is None:
        old_status = target_user.approval_status.value if target_user.approval_status else "PENDING"
    
    return log_staff_action(
        action_type=StaffActionType.REJECTION,
        target_user=target_user,
        performed_by=performed_by,
        reason=reason,
        old_approval_status=old_status,
        new_approval_status="REJECTED"
    )


def log_role_change(target_user: User, old_role: str, new_role: str,
                   old_role_title: str = None, new_role_title: str = None,
                   old_zone_id: int = None, new_zone_id: int = None,
                   old_lga_id: int = None, new_lga_id: int = None,
                   old_ward_id: int = None, new_ward_id: int = None,
                   performed_by: User = None, reason: str = None) -> StaffActionLog:
    """Log a comprehensive role change including location assignments"""
    return log_staff_action(
        action_type=StaffActionType.ROLE_CHANGE,
        target_user=target_user,
        performed_by=performed_by,
        reason=reason,
        old_role_type=old_role,
        new_role_type=new_role,
        old_role_title=old_role_title,
        new_role_title=new_role_title,
        old_zone_id=old_zone_id,
        new_zone_id=new_zone_id,
        old_lga_id=old_lga_id,
        new_lga_id=new_lga_id,
        old_ward_id=old_ward_id,
        new_ward_id=new_ward_id
    )


def log_position_swap(user1: User, user2: User, performed_by: User = None, 
                     reason: str = None) -> tuple[StaffActionLog, StaffActionLog]:
    """Log a position swap between two users"""
    # Log for user 1
    log1 = log_staff_action(
        action_type=StaffActionType.POSITION_SWAP,
        target_user=user1,
        performed_by=performed_by,
        reason=f"Position swapped with {user2.full_name}. {reason}" if reason else f"Position swapped with {user2.full_name}"
    )
    
    # Log for user 2
    log2 = log_staff_action(
        action_type=StaffActionType.POSITION_SWAP,
        target_user=user2,
        performed_by=performed_by,
        reason=f"Position swapped with {user1.full_name}. {reason}" if reason else f"Position swapped with {user1.full_name}"
    )
    
    return log1, log2


def get_staff_action_history(user_id: int, limit: int = 50) -> list[StaffActionLog]:
    """Get staff action history for a user"""
    return StaffActionLog.query.filter_by(target_user_id=user_id).order_by(
        StaffActionLog.created_at.desc()
    ).limit(limit).all()


def get_actions_performed_by(user_id: int, limit: int = 50) -> list[StaffActionLog]:
    """Get actions performed by a specific user"""
    return StaffActionLog.query.filter_by(performed_by_id=user_id).order_by(
        StaffActionLog.created_at.desc()
    ).limit(limit).all()


def get_recent_staff_actions(limit: int = 100) -> list[StaffActionLog]:
    """Get recent staff actions across the system"""
    return StaffActionLog.query.order_by(
        StaffActionLog.created_at.desc()
    ).limit(limit).all()


def _generate_action_description(action_type: StaffActionType, target_user: User, 
                               performed_by: User, old_role: str = None, 
                               new_role: str = None, old_approval: str = None, 
                               new_approval: str = None) -> str:
    """Generate a human-readable description of the action"""
    performer_info = f"{performed_by.role_type.value.replace('_', ' ').title()} {performed_by.full_name}"
    target_info = target_user.full_name
    
    if action_type == StaffActionType.PROMOTION:
        return f"{performer_info} promoted {target_info} from {old_role.replace('_', ' ').title()} to {new_role.replace('_', ' ').title()}"
    elif action_type == StaffActionType.DEMOTION:
        return f"{performer_info} demoted {target_info} from {old_role.replace('_', ' ').title()} to {new_role.replace('_', ' ').title()}"
    elif action_type == StaffActionType.ROLE_CHANGE:
        return f"{performer_info} changed {target_info}'s role from {old_role.replace('_', ' ').title()} to {new_role.replace('_', ' ').title()}"
    elif action_type == StaffActionType.APPROVAL:
        return f"{performer_info} approved {target_info}'s registration"
    elif action_type == StaffActionType.REJECTION:
        return f"{performer_info} rejected {target_info}'s registration"
    elif action_type == StaffActionType.DISMISSAL:
        return f"{performer_info} dismissed {target_info} from the organization"
    elif action_type == StaffActionType.POSITION_SWAP:
        return f"{performer_info} facilitated a position swap involving {target_info}"
    elif action_type == StaffActionType.LOCATION_CHANGE:
        return f"{performer_info} updated {target_info}'s location assignment"
    else:
        return f"{performer_info} performed {action_type.value} action on {target_info}"


def create_reminder_for_missed_duty(user: User, duty_description: str, 
                                   due_date: datetime = None) -> DutyLog:
    """Create a reminder duty log for missed obligations"""
    reminder_text = f"REMINDER: {duty_description}"
    if due_date and due_date < datetime.utcnow():
        reminder_text += f" (Originally due: {due_date.strftime('%Y-%m-%d')})"
    
    duty_log = DutyLog(
        user_id=user.id,
        duty_description=reminder_text,
        completion_status='pending',
        due_date=datetime.utcnow() + timedelta(days=7)  # Give 7 days to acknowledge
    )
    
    db.session.add(duty_log)
    
    # Increment missed duties counter
    user.increment_missed_duties()
    
    try:
        db.session.commit()
        current_app.logger.info(f"Reminder duty created for {user.full_name}: {duty_description}")
        return duty_log
    except Exception as e:
        current_app.logger.error(f"Error creating reminder duty: {e}")
        db.session.rollback()
        return None


def auto_flag_inactive_staff() -> dict[str, int]:
    """Automatically flag staff as inactive based on missed duties and ignored reminders"""
    stats = {
        'flagged_inactive': 0,
        'flagged_irregular': 0,
        'total_checked': 0,
        'errors': 0
    }
    
    try:
        # Get all approved staff members
        staff_members = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER
        ).all()
        
        stats['total_checked'] = len(staff_members)
        
        for user in staff_members:
            try:
                old_status = user.staff_status
                user.update_staff_status()
                
                # Track status changes
                if old_status != user.staff_status:
                    if user.staff_status == StaffStatus.INACTIVE:
                        stats['flagged_inactive'] += 1
                        
                        # Create a duty log for the status change
                        duty_log = DutyLog(
                            user_id=user.id,
                            duty_description=f"Status automatically changed to INACTIVE due to inactivity. "
                                           f"Missed duties: {user.missed_duties_count}, "
                                           f"Ignored reminders: {user.ignored_reminders_count}",
                            completion_status='completed',
                            completed_date=datetime.utcnow()
                        )
                        db.session.add(duty_log)
                        
                    elif user.staff_status == StaffStatus.IRREGULAR:
                        stats['flagged_irregular'] += 1
                        
                        # Create a duty log for the status change
                        duty_log = DutyLog(
                            user_id=user.id,
                            duty_description=f"Status automatically changed to IRREGULAR due to missed duties: {user.missed_duties_count}",
                            completion_status='completed',
                            completed_date=datetime.utcnow()
                        )
                        db.session.add(duty_log)
                        
            except Exception as e:
                stats['errors'] += 1
                current_app.logger.error(f"Error auto-flagging user {user.id}: {e}")
        
        db.session.commit()
        
        current_app.logger.info(
            f"Auto-flagged staff status: {stats['flagged_inactive']} inactive, "
            f"{stats['flagged_irregular']} irregular out of {stats['total_checked']} staff members"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in auto-flagging inactive staff: {e}")
        db.session.rollback()
        stats['errors'] += 1
    
    return stats