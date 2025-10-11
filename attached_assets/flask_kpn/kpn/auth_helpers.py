"""
Authorization and jurisdiction helper functions for KPN platform
"""
from models import User, RoleType, ApprovalStatus


def get_users_in_jurisdiction(current_user):
    """Get users that the current user can manage based on their role and jurisdiction"""
    if current_user.role_type == RoleType.ADMIN:
        # Admin can manage everyone (including state coordinators)
        return User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED
        ).all()
    
    elif current_user.role_type == RoleType.EXECUTIVE:
        # Executives can manage auditor general, zonal coordinators, and below including general members
        return User.query.filter(
            User.role_type.in_([RoleType.AUDITOR_GENERAL, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER, RoleType.GENERAL_MEMBER]),
            User.approval_status == ApprovalStatus.APPROVED
        ).all()
    
    elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
        # Zonal coordinators can manage LGA and ward leaders in their zone only
        if not current_user.zone_id:
            return []
        return User.query.filter(
            User.role_type.in_([RoleType.LGA_LEADER, RoleType.WARD_LEADER]),
            User.zone_id == current_user.zone_id,
            User.approval_status == ApprovalStatus.APPROVED
        ).all()
    
    elif current_user.role_type == RoleType.LGA_LEADER:
        # LGA leaders can manage ward leaders in their LGA only
        if not current_user.lga_id:
            return []
        return User.query.filter(
            User.role_type == RoleType.WARD_LEADER,
            User.lga_id == current_user.lga_id,
            User.approval_status == ApprovalStatus.APPROVED
        ).all()
    
    else:
        # Ward leaders and general members cannot manage others
        return []


def can_manage_user(current_user, target_user):
    """Check if current user can manage the target user based on jurisdiction"""
    if current_user.role_type == RoleType.ADMIN:
        # Admin can manage everyone (including state coordinators)
        return True
    
    elif current_user.role_type == RoleType.EXECUTIVE:
        # Executives can manage auditor general, zonal coordinators, and below including general members
        return target_user.role_type in [RoleType.AUDITOR_GENERAL, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER, RoleType.GENERAL_MEMBER]
    
    elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
        if not current_user.zone_id:
            return False
        return (target_user.role_type in [RoleType.LGA_LEADER, RoleType.WARD_LEADER] and 
                target_user.zone_id == current_user.zone_id)
    
    elif current_user.role_type == RoleType.LGA_LEADER:
        if not current_user.lga_id:
            return False
        return (target_user.role_type == RoleType.WARD_LEADER and 
                target_user.lga_id == current_user.lga_id)
    
    else:
        return False


def get_duties_in_jurisdiction(current_user):
    """Get duties that the current user can view based on their role and jurisdiction"""
    from models import DutyLog
    
    if current_user.role_type == RoleType.ADMIN:
        # Admin can see all duties
        return DutyLog.query.order_by(DutyLog.created_at.desc())
    
    elif current_user.role_type == RoleType.EXECUTIVE:
        # Executives can see duties for zonal, LGA, and ward leaders
        return DutyLog.query.join(User).filter(
            User.role_type.in_([RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]),
            User.approval_status == ApprovalStatus.APPROVED
        ).order_by(DutyLog.created_at.desc())
    
    elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
        # Zonal coordinators can see duties for users in their zone
        if not current_user.zone_id:
            return DutyLog.query.filter_by(user_id=current_user.id)
        return DutyLog.query.join(User).filter(
            User.role_type.in_([RoleType.LGA_LEADER, RoleType.WARD_LEADER]),
            User.zone_id == current_user.zone_id,
            User.approval_status == ApprovalStatus.APPROVED
        ).order_by(DutyLog.created_at.desc())
    
    elif current_user.role_type == RoleType.LGA_LEADER:
        # LGA leaders can see duties for ward leaders in their LGA
        if not current_user.lga_id:
            return DutyLog.query.filter_by(user_id=current_user.id)
        return DutyLog.query.join(User).filter(
            User.role_type == RoleType.WARD_LEADER,
            User.lga_id == current_user.lga_id,
            User.approval_status == ApprovalStatus.APPROVED
        ).order_by(DutyLog.created_at.desc())
    
    else:
        # Ward leaders and general members can only see their own duties
        return DutyLog.query.filter_by(user_id=current_user.id).order_by(DutyLog.created_at.desc())


def validate_duty_assignment(current_user, target_user_id):
    """Validate if current user can assign duties to the target user"""
    target_user = User.query.get(target_user_id)
    if not target_user:
        return False, "Target user not found"
    
    if not can_manage_user(current_user, target_user):
        return False, "You do not have permission to assign duties to this user"
    
    if target_user.approval_status != ApprovalStatus.APPROVED:
        return False, "Cannot assign duties to unapproved users"
    
    return True, "Valid assignment"