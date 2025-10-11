from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import enum
import secrets
import hashlib
from cryptography.fernet import Fernet
import base64
import os

class RoleType(enum.Enum):
    ADMIN = "admin"
    EXECUTIVE = "executive"
    AUDITOR_GENERAL = "auditor_general"
    ZONAL_COORDINATOR = "zonal_coordinator"
    LGA_LEADER = "lga_leader"
    WARD_LEADER = "ward_leader"
    GENERAL_MEMBER = "general_member"

class ApprovalStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class StaffStatus(enum.Enum):
    ACTIVE = "active"
    IRREGULAR = "irregular"
    INACTIVE = "inactive"

class EngagementStatus(enum.Enum):
    ENGAGED = "engaged"
    PARTIALLY_ENGAGED = "partially_engaged"
    NOT_ENGAGED = "not_engaged"

class ActionType(enum.Enum):
    WARNING = "warning"
    SUSPENSION = "suspension"
    DISMISSAL = "dismissal"
    REPRIMAND = "reprimand"

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20))
    whatsapp_number = db.Column(db.String(20), nullable=False)  # Required WhatsApp number
    bio = db.Column(db.Text)
    photo = db.Column(db.String(255))
    
    # Role and hierarchy
    role_type = db.Column(db.Enum(RoleType), default=RoleType.GENERAL_MEMBER)
    role_title = db.Column(db.String(100))
    approval_status = db.Column(db.Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    
    # Location assignment
    zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'))
    lga_id = db.Column(db.Integer, db.ForeignKey('lgas.id'))
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'))
    
    # Facebook integration
    facebook_user_id = db.Column(db.String(100))
    facebook_verified = db.Column(db.Boolean, default=False)
    facebook_follow_date = db.Column(db.DateTime)
    facebook_access_token = db.Column(db.Text)  # Encrypted Facebook token
    facebook_token_expires = db.Column(db.DateTime)  # Token expiration
    
    # Password reset fields
    reset_token = db.Column(db.String(255))
    reset_token_expires = db.Column(db.DateTime)
    
    # Profile edit tracking
    profile_edit_count = db.Column(db.Integer, default=0)
    
    # Staff status and engagement tracking
    staff_status = db.Column(db.Enum(StaffStatus), default=StaffStatus.ACTIVE)
    engagement_status = db.Column(db.Enum(EngagementStatus), default=EngagementStatus.NOT_ENGAGED)
    last_activity_date = db.Column(db.DateTime)
    last_engagement_check = db.Column(db.DateTime)
    missed_duties_count = db.Column(db.Integer, default=0)
    ignored_reminders_count = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    zone = db.relationship('Zone', backref='users')
    lga = db.relationship('LGA', backref='users')
    ward = db.relationship('Ward', backref='users')
    duty_logs = db.relationship('DutyLog', backref='user', lazy='dynamic')
    disciplinary_actions = db.relationship('DisciplinaryAction', foreign_keys='DisciplinaryAction.user_id', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_reset_token(self):
        """Generate a secure password reset token"""
        token = secrets.token_urlsafe(32)
        # Hash the token for security
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self.reset_token = token_hash
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        return token  # Return unhashed token for email
    
    def verify_reset_token(self, token):
        """Verify password reset token"""
        if not self.reset_token or not self.reset_token_expires:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token_hash == self.reset_token
    
    def clear_reset_token(self):
        """Clear password reset token after use"""
        self.reset_token = None
        self.reset_token_expires = None
    
    def _get_encryption_key(self):
        """Get encryption key for Facebook token encryption"""
        key = os.environ.get('SECRET_KEY', 'default-key-for-development').encode()
        # Pad or truncate to 32 bytes for Fernet
        key = key[:32].ljust(32, b'0')
        return base64.urlsafe_b64encode(key)
    
    def encrypt_facebook_token(self, token, expires_in=None):
        """Encrypt and store Facebook access token"""
        try:
            if not token:
                return
            
            fernet = Fernet(self._get_encryption_key())
            encrypted_token = fernet.encrypt(token.encode())
            self.facebook_access_token = base64.urlsafe_b64encode(encrypted_token).decode()
            
            if expires_in:
                # expires_in is in seconds
                self.facebook_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
            
        except Exception as e:
            print(f"Error encrypting Facebook token: {e}")
    
    def decrypt_facebook_token(self):
        """Decrypt and return Facebook access token"""
        try:
            if not self.facebook_access_token:
                return None
            
            # Check if token is expired
            if self.facebook_token_expires and datetime.utcnow() > self.facebook_token_expires:
                return None
            
            fernet = Fernet(self._get_encryption_key())
            encrypted_token = base64.urlsafe_b64decode(self.facebook_access_token.encode())
            decrypted_token = fernet.decrypt(encrypted_token)
            return decrypted_token.decode()
            
        except Exception as e:
            print(f"Error decrypting Facebook token: {e}")
            return None
    
    def clear_facebook_token(self):
        """Clear stored Facebook token"""
        self.facebook_access_token = None
        self.facebook_token_expires = None
    
    def get_location_hierarchy(self):
        """Get the full location hierarchy for this user"""
        location = []
        if self.ward:
            location.append(f"Ward: {self.ward.name}")
        if self.lga:
            location.append(f"LGA: {self.lga.name}")
        if self.zone:
            location.append(f"Zone: {self.zone.name}")
        return " | ".join(reversed(location))
    
    def can_edit_profile(self):
        """Check if user can still edit their profile (max 3 edits)"""
        return self.profile_edit_count < 3
    
    def increment_edit_count(self):
        """Increment the profile edit count"""
        self.profile_edit_count += 1
    
    def can_approve_user(self, target_user):
        """Check if this user can approve another user"""
        if self.role_type == RoleType.ADMIN:
            return True
        
        # State executives can approve zonal coordinators
        if (self.role_type == RoleType.EXECUTIVE and 
            target_user.role_type == RoleType.ZONAL_COORDINATOR):
            return True
        
        # Zonal coordinators can approve LGA leaders in their zone
        if (self.role_type == RoleType.ZONAL_COORDINATOR and 
            target_user.role_type == RoleType.LGA_LEADER and
            target_user.zone_id == self.zone_id):
            return True
        
        # LGA leaders can approve ward leaders in their LGA
        if (self.role_type == RoleType.LGA_LEADER and 
            target_user.role_type == RoleType.WARD_LEADER and
            target_user.lga_id == self.lga_id):
            return True
        
        return False
    
    def update_activity_date(self):
        """Update last activity date to current time"""
        self.last_activity_date = datetime.utcnow()
    
    def update_staff_status(self):
        """Auto-update staff status based on activity and duties"""
        now = datetime.utcnow()
        
        # If no activity in 30 days, mark as inactive
        if self.last_activity_date and (now - self.last_activity_date).days > 30:
            self.staff_status = StaffStatus.INACTIVE
        # If ignored 3+ reminders, mark as inactive
        elif self.ignored_reminders_count >= 3:
            self.staff_status = StaffStatus.INACTIVE
        # If missed 3+ duties, mark as irregular
        elif self.missed_duties_count >= 3:
            self.staff_status = StaffStatus.IRREGULAR
        # If activity within 7 days, mark as active
        elif self.last_activity_date and (now - self.last_activity_date).days <= 7:
            self.staff_status = StaffStatus.ACTIVE
        else:
            self.staff_status = StaffStatus.IRREGULAR
    
    def update_engagement_status(self):
        """Update engagement status based on Facebook interactions"""
        # This will be called after checking Facebook engagement
        # Include both verified API records AND manual overrides
        recent_engagements = FacebookEngagement.query.filter(
            FacebookEngagement.user_id == self.id,
            FacebookEngagement.last_checked >= datetime.utcnow() - timedelta(days=30)
        ).filter(
            (FacebookEngagement.verified == True) | 
            (FacebookEngagement.verified == False)  # Include manual overrides
        ).count()
        
        if recent_engagements >= 5:
            self.engagement_status = EngagementStatus.ENGAGED
        elif recent_engagements >= 2:
            self.engagement_status = EngagementStatus.PARTIALLY_ENGAGED
        else:
            self.engagement_status = EngagementStatus.NOT_ENGAGED
    
    def get_whatsapp_url(self, message=""):
        """Generate WhatsApp URL for direct messaging"""
        import urllib.parse
        whatsapp_number = self.whatsapp_number.replace('+', '').replace(' ', '').replace('-', '')
        if whatsapp_number.startswith('0'):
            whatsapp_number = '234' + whatsapp_number[1:]  # Convert Nigerian format
        
        encoded_message = urllib.parse.quote(message)
        return f"https://wa.me/{whatsapp_number}?text={encoded_message}"
    
    def increment_missed_duties(self):
        """Increment missed duties count and update status"""
        self.missed_duties_count += 1
        self.update_staff_status()
    
    def increment_ignored_reminders(self):
        """Increment ignored reminders count and update status"""
        self.ignored_reminders_count += 1
        self.update_staff_status()
    
    def reset_duty_counters(self):
        """Reset duty and reminder counters (when user becomes active again)"""
        self.missed_duties_count = 0
        self.ignored_reminders_count = 0
        self.staff_status = StaffStatus.ACTIVE
        self.update_activity_date()
    
    def get_status_display(self):
        """Get display-friendly status information"""
        status_map = {
            StaffStatus.ACTIVE: {"color": "success", "text": "Active"},
            StaffStatus.IRREGULAR: {"color": "warning", "text": "Irregular"},
            StaffStatus.INACTIVE: {"color": "danger", "text": "Inactive"}
        }
        return status_map.get(self.staff_status, {"color": "secondary", "text": "Unknown"})
    
    def get_engagement_display(self):
        """Get display-friendly engagement information"""
        engagement_map = {
            EngagementStatus.ENGAGED: {"color": "success", "text": "Highly Engaged"},
            EngagementStatus.PARTIALLY_ENGAGED: {"color": "warning", "text": "Partially Engaged"},
            EngagementStatus.NOT_ENGAGED: {"color": "danger", "text": "Not Engaged"}
        }
        return engagement_map.get(self.engagement_status, {"color": "secondary", "text": "Unknown"})

class Zone(db.Model):
    __tablename__ = 'zones'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True)
    description = db.Column(db.Text)
    
    # Relationships
    lgas = db.relationship('LGA', backref='zone', lazy='dynamic')
    
    def get_coordinator(self):
        return User.query.filter_by(
            zone_id=self.id, 
            role_type=RoleType.ZONAL_COORDINATOR,
            role_title='Zonal Coordinator',
            approval_status=ApprovalStatus.APPROVED
        ).first()

class LGA(db.Model):
    __tablename__ = 'lgas'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'), nullable=False)
    
    # Relationships
    wards = db.relationship('Ward', backref='lga', lazy='dynamic')
    
    def get_coordinator(self):
        return User.query.filter_by(
            lga_id=self.id, 
            role_type=RoleType.LGA_LEADER,
            role_title='LGA Coordinator',
            approval_status=ApprovalStatus.APPROVED
        ).first()

class Ward(db.Model):
    __tablename__ = 'wards'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True)
    lga_id = db.Column(db.Integer, db.ForeignKey('lgas.id'), nullable=False)
    
    def get_coordinator(self):
        return User.query.filter_by(
            ward_id=self.id, 
            role_type=RoleType.WARD_LEADER,
            role_title='Ward Coordinator',
            approval_status=ApprovalStatus.APPROVED
        ).first()

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    featured_image = db.Column(db.String(255))
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    published = db.Column(db.Boolean, default=False)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Approval workflow fields
    approval_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    
    # Facebook integration fields
    facebook_post_id = db.Column(db.String(100))  # Facebook post ID for tracking
    facebook_post_url = db.Column(db.String(500))  # Full Facebook post URL
    engagement_required = db.Column(db.Boolean, default=False)  # Whether staff must engage
    engagement_deadline = db.Column(db.DateTime)  # Deadline for engagement
    
    # Relationships
    author = db.relationship('User', backref='campaigns', foreign_keys=[author_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

class Event(db.Model):
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    event_date = db.Column(db.DateTime, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Scope (state, zone, lga, ward)
    scope = db.Column(db.String(20), default='state')
    zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'))
    lga_id = db.Column(db.Integer, db.ForeignKey('lgas.id'))
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'))
    
    # Online meeting support
    meeting_type = db.Column(db.String(20), default='in_person')  # in_person, zoom, whatsapp, hybrid
    meeting_url = db.Column(db.String(500))  # Zoom link or WhatsApp group link
    meeting_id = db.Column(db.String(100))  # Zoom meeting ID
    meeting_password = db.Column(db.String(100))  # Zoom meeting password
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    created_by = db.relationship('User', backref='events_created')
    
    def get_attendance_count(self):
        """Get count of attending members"""
        return EventAttendance.query.filter_by(event_id=self.id, attendance_status='attending').count()
    
    def get_non_attendance_count(self):
        """Get count of non-attending members"""
        return EventAttendance.query.filter_by(event_id=self.id, attendance_status='not_attending').count()
    
    def user_attendance_status(self, user_id):
        """Get attendance status for a specific user"""
        attendance = EventAttendance.query.filter_by(event_id=self.id, user_id=user_id).first()
        return attendance.attendance_status if attendance else None

class EventAttendance(db.Model):
    __tablename__ = 'event_attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    attendance_status = db.Column(db.String(20), nullable=False)  # attending, not_attending, maybe
    marked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # Who marked the attendance (self or supervisor)
    notes = db.Column(db.Text)  # Optional reason/notes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint to prevent duplicate attendance records
    __table_args__ = (db.UniqueConstraint('event_id', 'user_id', name='unique_event_attendance'),)
    
    # Relationships
    event = db.relationship('Event', backref='attendance_records')
    user = db.relationship('User', foreign_keys=[user_id], backref='event_attendance')
    marked_by = db.relationship('User', foreign_keys=[marked_by_id], backref='attendance_marks_made')

class Media(db.Model):
    __tablename__ = 'media'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)  # photo, video
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    public = db.Column(db.Boolean, default=False)  # Default to False - requires approval
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Approval workflow fields
    approval_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    
    # Relationships
    uploaded_by = db.relationship('User', backref='media_uploads', foreign_keys=[uploaded_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

class DutyLog(db.Model):
    __tablename__ = 'duty_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    duty_description = db.Column(db.Text, nullable=False)
    completion_status = db.Column(db.String(20), default='pending')  # pending, completed, overdue
    due_date = db.Column(db.DateTime)
    completed_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DisciplinaryAction(db.Model):
    __tablename__ = 'disciplinary_actions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)  # warning, suspension, dismissal
    reason = db.Column(db.Text, nullable=False)
    issued_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active, resolved, pending_dismissal
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    # Dismissal approval hierarchy fields
    approval_status = db.Column(db.String(20), default='not_required')  # not_required, pending_approval, approved, rejected
    approval_required = db.Column(db.Boolean, default=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)  # Notes from approver
    
    # Relationships
    issued_by = db.relationship('User', foreign_keys=[issued_by_id], backref='disciplinary_actions_issued')
    approved_by = db.relationship('User', foreign_keys=[approved_by_id], backref='disciplinary_approvals_given')
    
    def requires_approval(self):
        """Check if this disciplinary action requires approval based on type and issuer role"""
        if self.action_type != 'dismissal':
            return False
        
        # Dismissals always require approval except when issued by Admin
        issuer_role = self.issued_by.role_type if self.issued_by else None
        return issuer_role != RoleType.ADMIN
    
    def get_required_approver_role(self):
        """Get the role type that can approve this dismissal based on hierarchy"""
        if not self.requires_approval():
            return None
        
        issuer_role = self.issued_by.role_type if self.issued_by else None
        
        # Approval hierarchy: Ward → LGA → Zonal → Executive → State Coordinator
        if issuer_role == RoleType.WARD_LEADER:
            return RoleType.LGA_LEADER
        elif issuer_role == RoleType.LGA_LEADER:
            return RoleType.ZONAL_COORDINATOR
        elif issuer_role == RoleType.ZONAL_COORDINATOR:
            return RoleType.EXECUTIVE
        elif issuer_role == RoleType.EXECUTIVE:
            # For executives, need State Coordinator (specific executive role)
            return RoleType.EXECUTIVE  # Will check for State Coordinator role_title
        
        return None
    
    def can_approve(self, user):
        """Check if given user can approve this dismissal"""
        if not self.requires_approval() or self.approval_status != 'pending_approval':
            return False
        
        required_role = self.get_required_approver_role()
        if not required_role:
            return False
        
        # Admin can approve anything
        if user.role_type == RoleType.ADMIN:
            return True
        
        issuer = self.issued_by
        issuer_role = issuer.role_type if issuer else None
        
        # For Executive-origin dismissals needing State Coordinator approval
        if required_role == RoleType.EXECUTIVE and issuer_role == RoleType.EXECUTIVE:
            return (user.role_type == RoleType.EXECUTIVE and 
                    user.role_title == 'State Coordinator')
        
        # Check role match
        if user.role_type != required_role:
            return False
        
        # Check jurisdiction (same zone/LGA for appropriate levels)
        if required_role == RoleType.LGA_LEADER:
            return user.lga_id == issuer.lga_id
        elif required_role == RoleType.ZONAL_COORDINATOR:
            return user.zone_id == issuer.zone_id
        elif required_role == RoleType.EXECUTIVE:
            return True  # Any Executive can approve Zonal-origin dismissals
        
        return False

class Donation(db.Model):
    __tablename__ = 'donations'
    
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), nullable=False)
    account_name = db.Column(db.String(200), nullable=False)
    account_number = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    """Comprehensive activity tracking for all member actions"""
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # facebook_like, duty_completed, event_attended, etc.
    activity_description = db.Column(db.Text, nullable=False)
    points_earned = db.Column(db.Integer, default=0)  # Scoring system for activities
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Optional foreign keys for related objects
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    media_id = db.Column(db.Integer, db.ForeignKey('media.id'))
    duty_log_id = db.Column(db.Integer, db.ForeignKey('duty_logs.id'))
    
    # Relationships
    user = db.relationship('User', backref='activity_logs')
    campaign = db.relationship('Campaign', backref='activity_logs')
    event = db.relationship('Event', backref='activity_logs')
    media = db.relationship('Media', backref='activity_logs')
    duty_log = db.relationship('DutyLog', backref='activity_logs')

class StaffActionType(enum.Enum):
    PROMOTION = "promotion"
    DEMOTION = "demotion"
    ROLE_CHANGE = "role_change"
    POSITION_SWAP = "position_swap"
    APPROVAL = "approval"
    REJECTION = "rejection"
    DISMISSAL = "dismissal"
    LOCATION_CHANGE = "location_change"

class StaffActionLog(db.Model):
    """Auto-logging system for all staff management actions"""
    __tablename__ = 'staff_action_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Action details
    action_type = db.Column(db.Enum(StaffActionType), nullable=False)
    action_description = db.Column(db.Text, nullable=False)
    
    # Who performed the action
    performed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Who was affected by the action
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Before and after states for audit trail
    old_role_type = db.Column(db.String(50))
    new_role_type = db.Column(db.String(50))
    old_role_title = db.Column(db.String(100))
    new_role_title = db.Column(db.String(100))
    old_approval_status = db.Column(db.String(20))
    new_approval_status = db.Column(db.String(20))
    old_zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'))
    new_zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'))
    old_lga_id = db.Column(db.Integer, db.ForeignKey('lgas.id'))
    new_lga_id = db.Column(db.Integer, db.ForeignKey('lgas.id'))
    old_ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'))
    new_ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'))
    
    # Additional metadata
    reason = db.Column(db.Text)  # Optional reason for the action
    auto_generated = db.Column(db.Boolean, default=True)  # Whether this was automatically generated
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    performed_by = db.relationship('User', foreign_keys=[performed_by_id], backref='staff_actions_performed')
    target_user = db.relationship('User', foreign_keys=[target_user_id], backref='staff_actions_received')
    old_zone = db.relationship('Zone', foreign_keys=[old_zone_id])
    new_zone = db.relationship('Zone', foreign_keys=[new_zone_id])
    old_lga = db.relationship('LGA', foreign_keys=[old_lga_id])
    new_lga = db.relationship('LGA', foreign_keys=[new_lga_id])
    old_ward = db.relationship('Ward', foreign_keys=[old_ward_id])
    new_ward = db.relationship('Ward', foreign_keys=[new_ward_id])
    
    def get_action_summary(self):
        """Get a human-readable summary of the action"""
        action_map = {
            StaffActionType.PROMOTION: f"Promoted from {self.old_role_type} to {self.new_role_type}",
            StaffActionType.DEMOTION: f"Demoted from {self.old_role_type} to {self.new_role_type}",
            StaffActionType.ROLE_CHANGE: f"Role changed from {self.old_role_type} to {self.new_role_type}",
            StaffActionType.POSITION_SWAP: f"Position swapped",
            StaffActionType.APPROVAL: f"Registration approved - status changed to {self.new_approval_status}",
            StaffActionType.REJECTION: f"Registration rejected - status changed to {self.new_approval_status}",
            StaffActionType.DISMISSAL: f"Dismissed from organization",
            StaffActionType.LOCATION_CHANGE: f"Location assignment changed"
        }
        return action_map.get(self.action_type, self.action_description)

class FacebookEngagement(db.Model):
    """Track Facebook engagement activities"""
    __tablename__ = 'facebook_engagements'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    facebook_post_id = db.Column(db.String(100))  # Facebook post ID
    post_url = db.Column(db.String(255))
    liked = db.Column(db.Boolean, default=False)
    shared = db.Column(db.Boolean, default=False)
    commented = db.Column(db.Boolean, default=False)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    verified = db.Column(db.Boolean, default=False)  # Whether engagement was verified via API
    
    # Relationships
    user = db.relationship('User', backref='facebook_engagements')
    campaign = db.relationship('Campaign', backref='facebook_engagements')

class MemberStats(db.Model):
    """Pre-calculated member statistics for performance"""
    __tablename__ = 'member_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    total_points = db.Column(db.Integer, default=0)
    duties_completed = db.Column(db.Integer, default=0)
    duties_overdue = db.Column(db.Integer, default=0)
    facebook_engagements = db.Column(db.Integer, default=0)
    events_attended = db.Column(db.Integer, default=0)
    campaigns_participated = db.Column(db.Integer, default=0)
    last_activity_date = db.Column(db.DateTime)
    activity_score = db.Column(db.Float, default=0.0)  # Overall activity rating
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('member_stats', uselist=False))

class Message(db.Model):
    """Internal messaging system for member-to-member communication"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    # Message type and priority
    message_type = db.Column(db.String(20), default='personal')  # personal, announcement, system
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, urgent
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')
    
    def mark_as_read(self):
        """Mark message as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()
    
    def get_formatted_date(self):
        """Get formatted creation date"""
        return self.created_at.strftime('%B %d, %Y at %I:%M %p')
    
    def get_excerpt(self, length=100):
        """Get message body excerpt"""
        if len(self.body) <= length:
            return self.body
        return self.body[:length] + '...'