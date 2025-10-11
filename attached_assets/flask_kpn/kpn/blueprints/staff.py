from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import secrets
import hashlib
import requests
from requests_oauthlib import OAuth2Session
from models import *
from utils.email_service import email_service

staff = Blueprint('staff', __name__)

# Facebook OAuth Configuration
FACEBOOK_CLIENT_ID = os.environ.get('FACEBOOK_APP_ID')
FACEBOOK_CLIENT_SECRET = os.environ.get('FACEBOOK_APP_SECRET')
FACEBOOK_AUTHORIZATION_BASE_URL = 'https://www.facebook.com/dialog/oauth'
FACEBOOK_TOKEN_URL = 'https://graph.facebook.com/oauth/access_token'
FACEBOOK_SCOPE = ['email', 'public_profile']

# Validate Facebook configuration
if not FACEBOOK_CLIENT_ID or not FACEBOOK_CLIENT_SECRET:
    print("Warning: Facebook OAuth requires FACEBOOK_APP_ID and FACEBOOK_APP_SECRET environment variables")

@staff.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # Check if user account is rejected
            if user.approval_status == ApprovalStatus.REJECTED:
                flash('Your account has been rejected. Please contact KPN administration for assistance.', 'error')
                return render_template('staff/login.html')
            
            # Check if user account is pending approval
            elif user.approval_status == ApprovalStatus.PENDING:
                flash('Your account is still pending approval. Please wait for approval from the appropriate authority.', 'info')
                return render_template('staff/login.html')
            
            # Only allow approved users to login
            elif user.approval_status == ApprovalStatus.APPROVED:
                if user.role_type != RoleType.GENERAL_MEMBER:
                    login_user(user, remember=True)
                    user.last_login = datetime.utcnow()
                    db.session.commit()
                    
                    # Redirect to appropriate dashboard
                    if user.role_type == RoleType.ADMIN:
                        return redirect(url_for('staff.admin_dashboard'))
                    elif user.role_type == RoleType.EXECUTIVE:
                        # Route executives based on their role_title
                        if user.role_title == 'State Coordinator':
                            return redirect(url_for('staff.executive_dashboard'))  # State Coordinator dashboard
                        elif user.role_title == 'Director, Media & Publicity':
                            return redirect(url_for('staff.media_director_dashboard'))
                        elif user.role_title == 'Deputy State Coordinator':
                            return redirect(url_for('staff.women_leader_dashboard'))
                        else:
                            # Default executive dashboard for other executive roles
                            return redirect(url_for('staff.general_executive_dashboard'))
                    elif user.role_type == RoleType.AUDITOR_GENERAL:
                        return redirect(url_for('staff.auditor_general_dashboard'))
                    elif user.role_type == RoleType.ZONAL_COORDINATOR:
                        return redirect(url_for('staff.zonal_dashboard'))
                    elif user.role_type == RoleType.LGA_LEADER:
                        return redirect(url_for('staff.lga_dashboard'))
                    elif user.role_type == RoleType.WARD_LEADER:
                        return redirect(url_for('staff.ward_dashboard'))
                else:
                    flash('General members do not have dashboard access.', 'error')
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('staff/login.html')

# Search functionality for staff management
@staff.route('/search')
@login_required
def search_staff():
    """Search staff members"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    query = request.args.get('q', '').strip()
    if not query:
        flash('Please enter a search term.', 'warning')
        return redirect(url_for('staff.dashboard'))
    
    # Import here to avoid circular imports
    from auth_helpers import get_users_in_jurisdiction
    
    # Get users in jurisdiction first, then filter by search
    manageable_users = get_users_in_jurisdiction(current_user)
    user_ids = [user.id for user in manageable_users]
    
    # Search in name, username, email, role_title
    search_results = User.query.filter(
        User.id.in_(user_ids),
        db.or_(
            User.full_name.ilike(f'%{query}%'),
            User.username.ilike(f'%{query}%'),
            User.email.ilike(f'%{query}%'),
            User.role_title.ilike(f'%{query}%')
        )
    ).all()
    
    return render_template('staff/search_results.html', users=search_results, query=query)

@staff.route('/login/facebook')
def facebook_login():
    """Initiate Facebook OAuth login"""
    if not FACEBOOK_CLIENT_ID or not FACEBOOK_CLIENT_SECRET:
        flash('Facebook login is not configured.', 'error')
        return redirect(url_for('staff.login'))
    
    facebook = OAuth2Session(
        FACEBOOK_CLIENT_ID,
        scope=FACEBOOK_SCOPE,
        redirect_uri=url_for('staff.facebook_callback', _external=True)
    )
    authorization_url, state = facebook.authorization_url(FACEBOOK_AUTHORIZATION_BASE_URL)
    session['oauth_state'] = state
    return redirect(authorization_url)

@staff.route('/login/facebook/callback')
def facebook_callback():
    """Handle Facebook OAuth callback"""
    if not FACEBOOK_CLIENT_ID or not FACEBOOK_CLIENT_SECRET:
        flash('Facebook login is not configured.', 'error')
        return redirect(url_for('staff.login'))
    
    facebook = OAuth2Session(
        FACEBOOK_CLIENT_ID,
        state=session.get('oauth_state'),
        redirect_uri=url_for('staff.facebook_callback', _external=True)
    )
    
    try:
        token = facebook.fetch_token(
            FACEBOOK_TOKEN_URL,
            client_secret=FACEBOOK_CLIENT_SECRET,
            authorization_response=request.url
        )
        
        # Get user data from Facebook
        user_data = facebook.get('https://graph.facebook.com/me?fields=id,name,email,picture').json()
        facebook_user_id = user_data.get('id')
        
        if not facebook_user_id:
            flash('Failed to get Facebook user information.', 'error')
            return redirect(url_for('staff.login'))
        
        # Find user by Facebook ID
        user = User.query.filter_by(facebook_user_id=facebook_user_id).first()
        
        if user and user.approval_status == ApprovalStatus.APPROVED:
            if user.role_type != RoleType.GENERAL_MEMBER:
                login_user(user, remember=True)
                user.last_login = datetime.utcnow()
                
                # Store Facebook token securely on server-side
                access_token = token.get('access_token')
                expires_in = token.get('expires_in')
                if access_token:
                    user.encrypt_facebook_token(access_token, expires_in)
                
                # Commit all changes together
                db.session.commit()
                
                # Redirect to appropriate dashboard
                return redirect_to_dashboard(user)
            else:
                flash('General members do not have dashboard access.', 'error')
        elif user and user.approval_status == ApprovalStatus.PENDING:
            flash('Your account is still pending approval.', 'warning')
        elif user and user.approval_status == ApprovalStatus.REJECTED:
            flash('Your account has been rejected.', 'error')
        else:
            flash('No account found with this Facebook profile. Please register first.', 'error')
            
    except Exception as e:
        current_app.logger.error(f'Facebook OAuth error: {str(e)}')
        flash('Facebook login failed. Please try again.', 'error')
    
    # Clear OAuth state
    session.pop('oauth_state', None)
    return redirect(url_for('staff.login'))

def redirect_to_dashboard(user):
    """Helper function to redirect user to appropriate dashboard"""
    if user.role_type == RoleType.ADMIN:
        return redirect(url_for('staff.admin_dashboard'))
    elif user.role_type == RoleType.EXECUTIVE:
        # Route executives based on their role_title
        if user.role_title == 'State Coordinator':
            return redirect(url_for('staff.executive_dashboard'))
        elif user.role_title == 'Director, Media & Publicity':
            return redirect(url_for('staff.media_director_dashboard'))
        elif user.role_title == 'Deputy State Coordinator':
            return redirect(url_for('staff.women_leader_dashboard'))
        else:
            return redirect(url_for('staff.general_executive_dashboard'))
    elif user.role_type == RoleType.AUDITOR_GENERAL:
        return redirect(url_for('staff.auditor_general_dashboard'))
    elif user.role_type == RoleType.ZONAL_COORDINATOR:
        return redirect(url_for('staff.zonal_dashboard'))
    elif user.role_type == RoleType.LGA_LEADER:
        return redirect(url_for('staff.lga_dashboard'))
    elif user.role_type == RoleType.WARD_LEADER:
        return redirect(url_for('staff.ward_dashboard'))
    else:
        return redirect(url_for('staff.login'))

@staff.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password request"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email address is required.', 'error')
            return render_template('staff/forgot_password.html')
        
        # Always show the same message to prevent email enumeration attacks
        try:
            user = User.query.filter_by(email=email).first()
            
            if user:
                # Generate reset token and send email
                token = user.generate_reset_token()
                db.session.commit()
                
                # Create reset link
                reset_link = url_for('staff.reset_password', token=token, _external=True)
                
                # Send reset email
                email_service.send_password_reset_email(
                    to=user.email,
                    reset_link=reset_link,
                    user_name=user.full_name
                )
                
        except Exception as e:
            current_app.logger.error(f'Failed to send reset email: {str(e)}')
            # Still show success message for security
        
        # Always show the same generic message regardless of whether email exists
        flash('If that email address is in our system, we have sent you a password reset link.', 'info')
        return redirect(url_for('staff.login'))
    
    return render_template('staff/forgot_password.html')

@staff.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset with token"""
    # Find user with valid reset token (more efficient approach)
    import hashlib
    from datetime import datetime
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = User.query.filter_by(reset_token=token_hash).first()
    
    # Additional validation for token expiry
    if user and (user.reset_token_expires is None or user.reset_token_expires <= datetime.utcnow()):
        user = None
    
    if not user:
        flash('Invalid or expired password reset token.', 'error')
        return redirect(url_for('staff.forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validate passwords
        if not new_password or not confirm_password:
            flash('Both password fields are required.', 'error')
            return render_template('staff/reset_password.html', token=token)
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('staff/reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('staff/reset_password.html', token=token)
        
        try:
            # Update password and clear reset token
            user.set_password(new_password)
            user.clear_reset_token()
            db.session.commit()
            
            flash('Your password has been successfully reset. You can now log in with your new password.', 'success')
            return redirect(url_for('staff.login'))
            
        except Exception as e:
            current_app.logger.error(f'Failed to reset password: {str(e)}')
            flash('An error occurred while resetting your password. Please try again.', 'error')
    
    return render_template('staff/reset_password.html', token=token)

@staff.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('core.home'))

@staff.route('/dashboard')
@login_required
def dashboard():
    # Redirect to appropriate dashboard based on role
    if current_user.role_type == RoleType.ADMIN:
        return redirect(url_for('staff.admin_dashboard'))
    elif current_user.role_type == RoleType.EXECUTIVE:
        # Route executives based on their role_title
        if current_user.role_title == 'State Coordinator':
            return redirect(url_for('staff.executive_dashboard'))  # State Coordinator dashboard
        elif current_user.role_title == 'Director, Media & Publicity':
            return redirect(url_for('staff.media_director_dashboard'))
        elif current_user.role_title == 'Deputy State Coordinator':
            return redirect(url_for('staff.women_leader_dashboard'))
        else:
            # Default executive dashboard for other executive roles
            return redirect(url_for('staff.general_executive_dashboard'))
    elif current_user.role_type == RoleType.AUDITOR_GENERAL:
        return redirect(url_for('staff.auditor_general_dashboard'))
    elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
        return redirect(url_for('staff.zonal_dashboard'))
    elif current_user.role_type == RoleType.LGA_LEADER:
        return redirect(url_for('staff.lga_dashboard'))
    elif current_user.role_type == RoleType.WARD_LEADER:
        return redirect(url_for('staff.ward_dashboard'))
    
    flash('Access denied.', 'error')
    return redirect(url_for('core.home'))

@staff.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role_type != RoleType.ADMIN:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Use cached statistics for better performance
    from utils.cache_utils import (
        get_user_statistics, get_campaign_statistics, get_event_statistics,
        get_role_statistics, get_zone_statistics
    )
    
    # Get all cached statistics
    user_stats = get_user_statistics()
    campaign_stats = get_campaign_statistics()
    event_stats = get_event_statistics()
    role_stats = get_role_statistics()
    zone_data = get_zone_statistics()
    
    # Extract individual values
    total_users = user_stats['total_users']
    total_members = user_stats['total_members']
    pending_approvals = user_stats['pending_approvals']
    new_members_this_month = user_stats['new_members_this_month']
    active_campaigns = campaign_stats['active_campaigns']
    upcoming_events = event_stats['upcoming_events']
    
    # Define thirty_days_ago for recent activities
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Recent activities (mock data for now - could be replaced with actual activity tracking)
    recent_activities = []
    recent_users = User.query.filter(User.created_at >= thirty_days_ago).order_by(User.created_at.desc()).limit(10).all()
    for user in recent_users:
        recent_activities.append({
            'description': f'New {user.role_type.value.replace("_", " ").title()} registration',
            'user': user,
            'created_at': user.created_at,
            'type': 'registration'
        })
    
    # Get pending users for admin review
    pending_users = User.query.filter_by(approval_status=ApprovalStatus.PENDING).order_by(User.created_at.desc()).limit(10).all()
    
    # Monthly growth data (last 6 months)
    monthly_data = []
    for i in range(6):
        month_start = (datetime.utcnow() - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        month_users = User.query.filter(
            User.created_at >= month_start,
            User.created_at <= month_end
        ).count()
        monthly_data.insert(0, {
            'month': month_start.strftime('%B %Y'),
            'users': month_users
        })
    
    return render_template('staff/admin_dashboard.html', 
                         total_users=total_users,
                         total_members=total_members,
                         pending_approvals=pending_approvals,
                         active_campaigns=active_campaigns,
                         upcoming_events=upcoming_events,
                         new_members_this_month=new_members_this_month,
                         role_stats=role_stats,
                         zones=zone_data,
                         recent_activities=recent_activities,
                         pending_users=pending_users,
                         monthly_data=monthly_data)

@staff.route('/executive')
@login_required
def executive_dashboard():
    if current_user.role_type != RoleType.EXECUTIVE:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # State-wide statistics for State Coordinator
    total_users = User.query.count()
    total_members = User.query.filter_by(approval_status=ApprovalStatus.APPROVED).count()
    pending_approvals = User.query.filter_by(approval_status=ApprovalStatus.PENDING).count()
    
    # Get campaign data
    try:
        active_campaigns = Campaign.query.filter_by(published=True).count()
        recent_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
    except:
        active_campaigns = 0
        recent_campaigns = []
    
    # Get event data
    try:
        total_events = Event.query.count()
        upcoming_events = Event.query.filter(Event.event_date >= datetime.utcnow()).count()
    except:
        total_events = 0
        upcoming_events = 0
    
    # Get duty logs data
    try:
        total_duties = DutyLog.query.count()
        pending_duties = DutyLog.query.filter_by(completion_status='pending').count()
        completed_duties = DutyLog.query.filter_by(completion_status='completed').count()
    except:
        total_duties = 0
        pending_duties = 0
        completed_duties = 0
    
    # Role distribution for state overview
    role_stats = {}
    for role in RoleType:
        if role != RoleType.GENERAL_MEMBER:  # Skip general members
            count = User.query.filter_by(role_type=role, approval_status=ApprovalStatus.APPROVED).count()
            role_stats[role.value] = count
    
    # Geographic distribution
    zones = Zone.query.all()
    zone_data = []
    for zone in zones:
        zone_users = User.query.filter_by(zone_id=zone.id, approval_status=ApprovalStatus.APPROVED).count()
        zone_lgas = LGA.query.filter_by(zone_id=zone.id).count()
        zone_data.append({
            'id': zone.id,
            'name': zone.name,
            'users': zone_users,
            'lgas': zone_lgas,
            'performance': min(100, (zone_users / 100) * 100) if zone_users else 0
        })
    
    # Recent activities
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_activities = []
    recent_users = User.query.filter(User.created_at >= thirty_days_ago).order_by(User.created_at.desc()).limit(15).all()
    for user in recent_users:
        recent_activities.append({
            'description': f'New {user.role_type.value.replace("_", " ").title()} registration',
            'user': user,
            'created_at': user.created_at,
            'type': 'registration',
            'status': user.approval_status.value
        })
    
    # Get pending users for State Coordinator review
    pending_users = User.query.filter_by(approval_status=ApprovalStatus.PENDING).order_by(User.created_at.desc()).limit(20).all()
    
    # State coordination metrics
    new_members_this_month = User.query.filter(User.created_at >= thirty_days_ago).count()
    
    # Get leadership distribution by zones
    leadership_distribution = []
    for zone in zones:
        coordinators = User.query.filter_by(zone_id=zone.id, role_type=RoleType.ZONAL_COORDINATOR, approval_status=ApprovalStatus.APPROVED).count()
        lga_leaders = User.query.filter_by(zone_id=zone.id, role_type=RoleType.LGA_LEADER, approval_status=ApprovalStatus.APPROVED).count()
        ward_leaders = User.query.filter_by(zone_id=zone.id, role_type=RoleType.WARD_LEADER, approval_status=ApprovalStatus.APPROVED).count()
        
        leadership_distribution.append({
            'zone_name': zone.name,
            'coordinators': coordinators,
            'lga_leaders': lga_leaders,
            'ward_leaders': ward_leaders,
            'total_leaders': coordinators + lga_leaders + ward_leaders
        })
    
    return render_template('staff/executive_dashboard.html',
                         total_users=total_users,
                         total_members=total_members,
                         pending_approvals=pending_approvals,
                         active_campaigns=active_campaigns,
                         recent_campaigns=recent_campaigns,
                         total_events=total_events,
                         upcoming_events=upcoming_events,
                         total_duties=total_duties,
                         pending_duties=pending_duties,
                         completed_duties=completed_duties,
                         role_stats=role_stats,
                         zones=zone_data,
                         recent_activities=recent_activities,
                         pending_users=pending_users,
                         new_members_this_month=new_members_this_month,
                         leadership_distribution=leadership_distribution)

@staff.route('/media-director')
@login_required
def media_director_dashboard():
    if current_user.role_type != RoleType.EXECUTIVE or current_user.role_title != 'Director, Media & Publicity':
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    
    # Media-specific statistics
    try:
        total_media = Media.query.count()
        public_media = Media.query.filter_by(public=True).count()
        recent_media = Media.query.filter(Media.created_at >= datetime.utcnow() - timedelta(days=30)).count()
    except:
        total_media = 0
        public_media = 0
        recent_media = 0
    
    # Campaign statistics relevant to media director
    try:
        total_campaigns = Campaign.query.count()
        active_campaigns = Campaign.query.filter_by(published=True).count()
        recent_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
    except:
        total_campaigns = 0
        active_campaigns = 0
        recent_campaigns = []
    
    # Media engagement metrics
    total_users = User.query.filter_by(approval_status=ApprovalStatus.APPROVED).count()
    
    return render_template('staff/media_director_dashboard.html',
                         total_media=total_media,
                         public_media=public_media,
                         recent_media=recent_media,
                         total_campaigns=total_campaigns,
                         active_campaigns=active_campaigns,
                         recent_campaigns=recent_campaigns,
                         total_users=total_users)

@staff.route('/women-leader')
@login_required
def women_leader_dashboard():
    if current_user.role_type != RoleType.EXECUTIVE or current_user.role_title != 'Women Leader':
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    
    # Women-focused statistics
    total_users = User.query.filter_by(approval_status=ApprovalStatus.APPROVED).count()
    pending_approvals = User.query.filter_by(approval_status=ApprovalStatus.PENDING).count()
    
    # Events relevant to women's activities
    try:
        total_events = Event.query.count()
        upcoming_events = Event.query.filter(Event.event_date >= datetime.utcnow()).count()
        recent_events = Event.query.order_by(Event.event_date.desc()).limit(5).all()
    except:
        total_events = 0
        upcoming_events = 0
        recent_events = []
    
    # Campaign data
    try:
        active_campaigns = Campaign.query.filter_by(published=True).count()
    except:
        active_campaigns = 0
    
    # Recent member activities
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_members_this_month = User.query.filter(User.created_at >= thirty_days_ago).count()
    
    return render_template('staff/women_leader_dashboard.html',
                         total_users=total_users,
                         pending_approvals=pending_approvals,
                         total_events=total_events,
                         upcoming_events=upcoming_events,
                         recent_events=recent_events,
                         active_campaigns=active_campaigns,
                         new_members_this_month=new_members_this_month)

@staff.route('/general-executive')
@login_required
def general_executive_dashboard():
    if current_user.role_type != RoleType.EXECUTIVE:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    
    # General executive statistics
    total_users = User.query.count()
    total_members = User.query.filter_by(approval_status=ApprovalStatus.APPROVED).count()
    pending_approvals = User.query.filter_by(approval_status=ApprovalStatus.PENDING).count()
    
    # Campaign data
    try:
        active_campaigns = Campaign.query.filter_by(published=True).count()
        recent_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
    except:
        active_campaigns = 0
        recent_campaigns = []
    
    # Event data
    try:
        total_events = Event.query.count()
        upcoming_events = Event.query.filter(Event.event_date >= datetime.utcnow()).count()
    except:
        total_events = 0
        upcoming_events = 0
    
    # Recent activities
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_members_this_month = User.query.filter(User.created_at >= thirty_days_ago).count()
    
    return render_template('staff/general_executive_dashboard.html',
                         total_users=total_users,
                         total_members=total_members,
                         pending_approvals=pending_approvals,
                         active_campaigns=active_campaigns,
                         recent_campaigns=recent_campaigns,
                         total_events=total_events,
                         upcoming_events=upcoming_events,
                         new_members_this_month=new_members_this_month)

@staff.route('/zonal')
@login_required
def zonal_dashboard():
    if current_user.role_type != RoleType.ZONAL_COORDINATOR:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    
    # Get zonal-specific data
    zone_lgas = LGA.query.filter_by(zone_id=current_user.zone_id).all()
    zone_users = User.query.filter_by(zone_id=current_user.zone_id, approval_status=ApprovalStatus.APPROVED).all()
    
    # Zone performance metrics
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_members_this_month = User.query.filter(
        User.zone_id == current_user.zone_id,
        User.created_at >= thirty_days_ago,
        User.approval_status == ApprovalStatus.APPROVED
    ).count()
    
    # LGA performance data
    lga_performance = []
    for lga in zone_lgas:
        lga_users = User.query.filter_by(lga_id=lga.id, approval_status=ApprovalStatus.APPROVED).count()
        lga_performance.append({
            'id': lga.id,
            'name': lga.name,
            'users': lga_users,
            'performance': min(100, (lga_users / 50) * 100) if lga_users else 0  # Performance based on target of 50 members per LGA
        })
    
    # Zone statistics
    total_lgas = len(zone_lgas)
    total_members = len(zone_users)
    pending_lga_approvals = User.query.filter_by(
        zone_id=current_user.zone_id,
        approval_status=ApprovalStatus.PENDING,
        role_type=RoleType.LGA_LEADER
    ).count()
    
    # Zone events and activities
    try:
        zone_events = Event.query.filter_by(zone_id=current_user.zone_id).count()
    except:
        zone_events = 0
    
    # Recent zone activities
    recent_activities = []
    recent_users = User.query.filter(
        User.zone_id == current_user.zone_id,
        User.created_at >= thirty_days_ago
    ).order_by(User.created_at.desc()).limit(10).all()
    
    for user in recent_users:
        recent_activities.append({
            'description': f'New {user.role_type.value.replace("_", " ").title()} from {user.lga.name if user.lga else "Unknown LGA"}',
            'timestamp': user.created_at,
            'type': 'registration'
        })
    
    return render_template('staff/zonal_dashboard.html', 
                         zone_lgas=zone_lgas,
                         zone_users=zone_users,
                         total_lgas=total_lgas,
                         total_members=total_members,
                         pending_lga_approvals=pending_lga_approvals,
                         zone_events=zone_events,
                         new_members_this_month=new_members_this_month,
                         lga_performance=lga_performance,
                         recent_activities=recent_activities)

@staff.route('/lga')
@login_required
def lga_dashboard():
    if current_user.role_type != RoleType.LGA_LEADER:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    
    # Get LGA-specific data
    lga_wards = Ward.query.filter_by(lga_id=current_user.lga_id).all()
    lga_users = User.query.filter_by(lga_id=current_user.lga_id, approval_status=ApprovalStatus.APPROVED).all()
    
    # LGA performance metrics
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_members_this_month = User.query.filter(
        User.lga_id == current_user.lga_id,
        User.created_at >= thirty_days_ago,
        User.approval_status == ApprovalStatus.APPROVED
    ).count()
    
    # Ward performance data
    ward_performance = []
    for ward in lga_wards:
        ward_users = User.query.filter_by(ward_id=ward.id, approval_status=ApprovalStatus.APPROVED).count()
        ward_performance.append({
            'id': ward.id,
            'name': ward.name,
            'users': ward_users,
            'performance': min(100, (ward_users / 20) * 100) if ward_users else 0  # Performance based on target of 20 members per ward
        })
    
    # LGA statistics
    total_wards = len(lga_wards)
    total_members = len(lga_users)
    pending_ward_approvals = User.query.filter_by(
        lga_id=current_user.lga_id,
        approval_status=ApprovalStatus.PENDING,
        role_type=RoleType.WARD_LEADER
    ).count()
    
    # LGA events and activities
    try:
        lga_events = Event.query.filter_by(lga_id=current_user.lga_id).count()
    except:
        lga_events = 0
    
    # Recent LGA activities
    recent_activities = []
    recent_users = User.query.filter(
        User.lga_id == current_user.lga_id,
        User.created_at >= thirty_days_ago
    ).order_by(User.created_at.desc()).limit(10).all()
    
    for user in recent_users:
        recent_activities.append({
            'description': f'New {user.role_type.value.replace("_", " ").title()} from {user.ward.name if user.ward else "Unknown Ward"}',
            'timestamp': user.created_at,
            'type': 'registration'
        })
    
    return render_template('staff/lga_dashboard.html', 
                         lga_wards=lga_wards,
                         lga_users=lga_users,
                         total_wards=total_wards,
                         total_members=total_members,
                         pending_ward_approvals=pending_ward_approvals,
                         lga_events=lga_events,
                         new_members_this_month=new_members_this_month,
                         ward_performance=ward_performance,
                         recent_activities=recent_activities)

@staff.route('/ward')
@login_required
def ward_dashboard():
    if current_user.role_type != RoleType.WARD_LEADER:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    # Get ward-specific data
    ward_users = User.query.filter_by(ward_id=current_user.ward_id).all()
    
    return render_template('staff/ward_dashboard.html', ward_users=ward_users)

# Enhanced Member Management Routes for Admin
@staff.route('/executive/manage-members')
@login_required
def manage_members():
    """State Coordinator member management page with promote/demote/swap functionality"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'State Coordinator') and current_user.role_type != RoleType.ADMIN:
        flash('Access denied. Only State Coordinator and Admin can manage members.', 'error')
        return redirect(url_for('core.home'))
    
    # Get all manageable users including approved, pending, and rejected
    all_manageable_users = User.query.filter(
        User.id != current_user.id  # Don't include self
    ).order_by(User.full_name).all()
    
    # Organize users by role type
    users_by_role = {}
    manageable_roles = [RoleType.EXECUTIVE, RoleType.AUDITOR_GENERAL, RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER, RoleType.GENERAL_MEMBER]
    
    for role in manageable_roles:
        users = [user for user in all_manageable_users if user.role_type == role]
        if users:  # Only add if there are users in this role
            users_by_role[role.value] = users
    
    # Get zones, LGAs, and wards for position assignments
    zones = Zone.query.all()
    lgas = LGA.query.all() 
    wards = Ward.query.all()
    
    return render_template('staff/manage_members.html',
                         users_by_role=users_by_role,
                         zones=zones,
                         lgas=lgas,
                         wards=wards,
                         role_types=RoleType)

@staff.route('/executive/promote-user/<int:user_id>', methods=['POST'])
@login_required
def promote_user(user_id):
    """Promote a user to a higher role"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'State Coordinator') and current_user.role_type != RoleType.ADMIN:
        flash('Access denied. Only State Coordinator and Admin can promote users.', 'error')
        return redirect(url_for('core.home'))
    
    user = User.query.get_or_404(user_id)
    
    
    # Define promotion hierarchy (EXECUTIVE is the highest authority role)
    promotion_map = {
        RoleType.GENERAL_MEMBER: RoleType.WARD_LEADER,
        RoleType.WARD_LEADER: RoleType.LGA_LEADER,
        RoleType.LGA_LEADER: RoleType.ZONAL_COORDINATOR,
        RoleType.ZONAL_COORDINATOR: RoleType.AUDITOR_GENERAL,
        RoleType.AUDITOR_GENERAL: RoleType.EXECUTIVE,
    }
    
    if user.role_type in promotion_map:
        old_role = user.role_type.value
        user.role_type = promotion_map[user.role_type]
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'{user.full_name} has been promoted from {old_role.replace("_", " ").title()} to {user.role_type.value.replace("_", " ").title()}.', 'success')
        
        # Auto-log the promotion action
        try:
            from utils.staff_action_logger import log_promotion
            log_promotion(user, old_role, user.role_type.value, reason="Promotion by supervisor")
        except Exception as e:
            current_app.logger.error(f"Error auto-logging promotion: {e}")
        
        # Log the action (could be expanded to a proper audit trail)
        current_app.logger.info(f'{current_user.role_type.value.title()} {current_user.full_name} promoted user {user.full_name} from {old_role} to {user.role_type.value}')
    else:
        flash(f'{user.full_name} cannot be promoted further or promotion path not defined.', 'warning')
    
    return redirect(request.referrer or url_for('staff.manage_members'))

@staff.route('/executive/demote-user/<int:user_id>', methods=['POST'])
@login_required
def demote_user(user_id):
    """Demote a user to a lower role"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'State Coordinator') and current_user.role_type != RoleType.ADMIN:
        flash('Access denied. Only State Coordinator and Admin can demote users.', 'error')
        return redirect(url_for('core.home'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent self-demotion
    if user.id == current_user.id:
        flash('You cannot demote yourself.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Prevent demoting Executives
    if user.role_type in [RoleType.EXECUTIVE]:
        flash(f'Cannot demote {user.role_type.value.replace("_", " ").title()}. This role is protected.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Define demotion hierarchy (EXECUTIVE is highest authority, cannot be demoted)
    demotion_map = {
        RoleType.AUDITOR_GENERAL: RoleType.ZONAL_COORDINATOR,
        RoleType.ZONAL_COORDINATOR: RoleType.LGA_LEADER,
        RoleType.LGA_LEADER: RoleType.WARD_LEADER,
        RoleType.WARD_LEADER: RoleType.GENERAL_MEMBER,
    }
    
    if user.role_type in demotion_map:
        old_role = user.role_type.value
        user.role_type = demotion_map[user.role_type]
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'{user.full_name} has been demoted from {old_role.replace("_", " ").title()} to {user.role_type.value.replace("_", " ").title()}.', 'warning')
        
        # Auto-log the demotion action
        try:
            from utils.staff_action_logger import log_demotion
            log_demotion(user, old_role, user.role_type.value, reason="Demotion by supervisor")
        except Exception as e:
            current_app.logger.error(f"Error auto-logging demotion: {e}")
        
        # Log the action
        current_app.logger.info(f'{current_user.role_type.value.title()} {current_user.full_name} demoted user {user.full_name} from {old_role} to {user.role_type.value}')
    else:
        flash(f'{user.full_name} cannot be demoted further.', 'warning')
    
    return redirect(request.referrer or url_for('staff.manage_members'))

@staff.route('/executive/swap-positions', methods=['POST'])
@login_required
def swap_positions():
    """Swap positions between two users"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'State Coordinator') and current_user.role_type != RoleType.ADMIN:
        flash('Access denied. Only State Coordinator and Admin can swap positions.', 'error')
        return redirect(url_for('core.home'))
    
    user1_id = request.form.get('user1_id', type=int)
    user2_id = request.form.get('user2_id', type=int)
    
    if not user1_id or not user2_id:
        flash('Both users must be selected for position swap.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    if user1_id == user2_id:
        flash('Cannot swap positions with the same user.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    user1 = User.query.get_or_404(user1_id)
    user2 = User.query.get_or_404(user2_id)
    
    # Prevent swapping with State Coordinator
    if current_user.id in [user1_id, user2_id]:
        flash('You cannot swap positions with yourself.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Prevent swapping protected roles (EXECUTIVE)
    if user1.role_type in [RoleType.EXECUTIVE] or user2.role_type in [RoleType.EXECUTIVE]:
        flash('Cannot swap positions involving protected roles (State Coordinator).', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Perform the swap
    user1_old_role = user1.role_type
    user1_old_zone = user1.zone_id
    user1_old_lga = user1.lga_id
    user1_old_ward = user1.ward_id
    user1_old_title = user1.role_title
    
    user2_old_role = user2.role_type
    user2_old_zone = user2.zone_id
    user2_old_lga = user2.lga_id
    user2_old_ward = user2.ward_id
    user2_old_title = user2.role_title
    
    # Swap roles and locations
    user1.role_type = user2_old_role
    user1.zone_id = user2_old_zone
    user1.lga_id = user2_old_lga
    user1.ward_id = user2_old_ward
    user1.role_title = user2_old_title
    user1.updated_at = datetime.utcnow()
    
    user2.role_type = user1_old_role
    user2.zone_id = user1_old_zone
    user2.lga_id = user1_old_lga
    user2.ward_id = user1_old_ward
    user2.role_title = user1_old_title
    user2.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Positions swapped successfully between {user1.full_name} and {user2.full_name}.', 'success')
    
    # Log the action
    current_app.logger.info(f'{current_user.role_type.value.title()} {current_user.full_name} swapped positions between {user1.full_name} and {user2.full_name}')
    
    return redirect(request.referrer or url_for('staff.manage_members'))

@staff.route('/executive/assign-duty-to-member', methods=['POST'])
@login_required
def assign_duty_to_member():
    """Assign duty to a member from State Coordinator dashboard"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'State Coordinator') and current_user.role_type != RoleType.ADMIN:
        flash('Access denied. Only State Coordinator and Admin can assign duties.', 'error')
        return redirect(url_for('core.home'))
    
    user_id = request.form.get('user_id', type=int)
    duty_description = request.form.get('duty_description', '').strip()
    due_date_str = request.form.get('due_date', '').strip()
    
    if not user_id or not duty_description:
        flash('User and duty description are required.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    user = User.query.get_or_404(user_id)
    
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format.', 'error')
            return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Create the duty log
    duty = DutyLog()
    duty.user_id = user_id
    duty.duty_description = duty_description
    duty.due_date = due_date
    duty.completion_status = 'pending'
    
    db.session.add(duty)
    db.session.commit()
    
    flash(f'Duty assigned to {user.full_name} successfully.', 'success')
    
    # Log the action
    current_app.logger.info(f'{current_user.role_type.value.title()} {current_user.full_name} assigned duty to {user.full_name}: {duty_description}')
    
    return redirect(request.referrer or url_for('staff.manage_members'))

@staff.route('/executive/change-user-role/<int:user_id>', methods=['POST'])
@login_required
def change_user_role(user_id):
    """Change a user's role to a specific role"""
    if current_user.role_type != RoleType.EXECUTIVE:
        flash('Access denied. Only State Coordinator can change user roles.', 'error')
        return redirect(url_for('core.home'))
    
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role')
    new_zone_id = request.form.get('zone_id', type=int)
    new_lga_id = request.form.get('lga_id', type=int)
    new_ward_id = request.form.get('ward_id', type=int)
    
    # Prevent changing own role
    if user.id == current_user.id:
        flash('You cannot change your own role.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Prevent changing protected roles and validate new role is manageable
    if user.role_type in [RoleType.EXECUTIVE]:
        flash('Cannot change protected roles (State Coordinator).', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Prevent assigning protected roles
    if new_role in ['ict_admin', 'executive']:
        flash('Cannot assign users to protected roles (ICT Admin or State Coordinator).', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    # Ensure new role is in manageable roles list
    manageable_role_values = ['auditor_general', 'zonal_coordinator', 'lga_leader', 'ward_leader', 'general_member']
    if new_role not in manageable_role_values:
        flash('Invalid role selection.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    try:
        old_role = user.role_type.value
        old_zone_id = user.zone_id
        old_lga_id = user.lga_id
        old_ward_id = user.ward_id
        old_role_title = user.role_title
        
        user.role_type = RoleType(new_role)
        
        # Update location assignments based on role
        if user.role_type == RoleType.ZONAL_COORDINATOR:
            user.zone_id = new_zone_id
            user.lga_id = None
            user.ward_id = None
        elif user.role_type == RoleType.LGA_LEADER:
            user.zone_id = new_zone_id
            user.lga_id = new_lga_id
            user.ward_id = None
        elif user.role_type == RoleType.WARD_LEADER:
            user.zone_id = new_zone_id
            user.lga_id = new_lga_id
            user.ward_id = new_ward_id
        else:
            # For higher roles, clear location assignments
            user.zone_id = None
            user.lga_id = None
            user.ward_id = None
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'{user.full_name} role changed from {old_role.replace("_", " ").title()} to {new_role.replace("_", " ").title() if new_role else "Unknown"}.', 'success')
        
        # Log the action
        current_app.logger.info(f'{current_user.role_type.value.title()} {current_user.full_name} changed {user.full_name} role from {old_role} to {new_role}')
        
    except ValueError:
        flash('Invalid role selected.', 'error')
    except Exception as e:
        flash(f'Error changing role: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(request.referrer or url_for('staff.manage_members'))

@staff.route('/executive/dismiss-user/<int:user_id>', methods=['POST'])
@login_required
def dismiss_user(user_id):
    """Dismiss a user from the organization"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'State Coordinator') and current_user.role_type != RoleType.ADMIN:
        flash('Access denied. Only State Coordinator and Admin can dismiss users.', 'error')
        return redirect(url_for('core.home'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent self-dismissal
    if user.id == current_user.id:
        flash('You cannot dismiss yourself.', 'error')
        return redirect(request.referrer or url_for('staff.manage_members'))
    
    
    try:
        # Set user approval status to rejected (dismissed)
        old_role = user.role_type.value
        user.approval_status = ApprovalStatus.REJECTED
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'{user.full_name} has been dismissed from the organization.', 'warning')
        
        # Log the action
        current_app.logger.info(f'{current_user.role_type.value.title()} {current_user.full_name} dismissed user {user.full_name} ({old_role})')
        
    except Exception as e:
        flash(f'Error dismissing user: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(request.referrer or url_for('staff.manage_members'))


@staff.route('/auditor-general')
@login_required
def auditor_general_dashboard():
    if current_user.role_type != RoleType.AUDITOR_GENERAL:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Financial oversight data for auditor general
    try:
        total_donations = Donation.query.filter_by(active=True).count()
        inactive_donations = Donation.query.filter_by(active=False).count()
        recent_donations = Donation.query.filter(
            Donation.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
    except:
        total_donations = 0
        inactive_donations = 0
        recent_donations = 0
    
    # Member audit statistics
    total_users = User.query.count()
    approved_members = User.query.filter_by(approval_status=ApprovalStatus.APPROVED).count()
    pending_approvals = User.query.filter_by(approval_status=ApprovalStatus.PENDING).count()
    rejected_users = User.query.filter_by(approval_status=ApprovalStatus.REJECTED).count()
    
    # Role distribution audit
    role_audit = {}
    for role in RoleType:
        count = User.query.filter_by(role_type=role, approval_status=ApprovalStatus.APPROVED).count()
        role_audit[role.value] = count
    
    # Geographic audit - Zone analysis
    zones = Zone.query.all()
    zone_audit = []
    for zone in zones:
        zone_users = User.query.filter_by(zone_id=zone.id, approval_status=ApprovalStatus.APPROVED).count()
        zone_lgas = LGA.query.filter_by(zone_id=zone.id).count()
        zone_audit.append({
            'id': zone.id,
            'name': zone.name,
            'approved_users': zone_users,
            'total_lgas': zone_lgas,
            'compliance_rate': min(100, (zone_users / max(zone_lgas * 10, 1)) * 100)  # Target 10 members per LGA
        })
    
    # Disciplinary audit
    try:
        total_disciplinary = DisciplinaryAction.query.count()
        active_disciplinary = DisciplinaryAction.query.filter_by(status='active').count()
        resolved_disciplinary = DisciplinaryAction.query.filter_by(status='resolved').count()
        recent_disciplinary = DisciplinaryAction.query.filter(
            DisciplinaryAction.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
    except:
        total_disciplinary = 0
        active_disciplinary = 0
        resolved_disciplinary = 0
        recent_disciplinary = 0
    
    # Campaign and event audit
    try:
        total_campaigns = Campaign.query.count()
        published_campaigns = Campaign.query.filter_by(published=True).count()
        total_events = Event.query.count()
        recent_events = Event.query.filter(
            Event.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
    except:
        total_campaigns = 0
        published_campaigns = 0
        total_events = 0
        recent_events = 0
    
    # Compliance summary for the auditor general
    compliance_metrics = {
        'member_approval_rate': round((approved_members / max(total_users, 1)) * 100, 2),
        'disciplinary_resolution_rate': round((resolved_disciplinary / max(total_disciplinary, 1)) * 100, 2),
        'campaign_publication_rate': round((published_campaigns / max(total_campaigns, 1)) * 100, 2),
        'zones_above_target': len([z for z in zone_audit if z['compliance_rate'] >= 80])
    }
    
    # Recent audit activities (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_activities = []
    
    # Add recent user registrations to audit trail
    recent_users = User.query.filter(User.created_at >= thirty_days_ago).order_by(User.created_at.desc()).limit(10).all()
    for user in recent_users:
        recent_activities.append({
            'description': f'New {user.role_type.value.replace("_", " ").title()} registration: {user.full_name}',
            'timestamp': user.created_at,
            'type': 'registration',
            'status': user.approval_status.value
        })
    
    # Add recent disciplinary actions to audit trail
    try:
        recent_disc = DisciplinaryAction.query.filter(
            DisciplinaryAction.created_at >= thirty_days_ago
        ).order_by(DisciplinaryAction.created_at.desc()).limit(5).all()
        for action in recent_disc:
            recent_activities.append({
                'description': f'Disciplinary action: {action.action_type} issued',
                'timestamp': action.created_at,
                'type': 'disciplinary',
                'status': action.status
            })
    except:
        pass
    
    # Sort activities by timestamp
    recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('staff/auditor_general_dashboard.html',
                         total_donations=total_donations,
                         inactive_donations=inactive_donations,
                         recent_donations=recent_donations,
                         total_users=total_users,
                         approved_members=approved_members,
                         pending_approvals=pending_approvals,
                         rejected_users=rejected_users,
                         role_audit=role_audit,
                         zone_audit=zone_audit,
                         total_disciplinary=total_disciplinary,
                         active_disciplinary=active_disciplinary,
                         resolved_disciplinary=resolved_disciplinary,
                         recent_disciplinary=recent_disciplinary,
                         total_campaigns=total_campaigns,
                         published_campaigns=published_campaigns,
                         total_events=total_events,
                         recent_events=recent_events,
                         compliance_metrics=compliance_metrics,
                         recent_activities=recent_activities)

@staff.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        try:
            # Get form data
            full_name = request.form.get('full_name', '').strip()
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            bio = request.form.get('bio', '').strip()
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Basic validation
            if not full_name:
                flash('Full name is required.', 'error')
                return render_template('staff/edit_profile.html', user=current_user)
            
            if not username:
                flash('Username is required.', 'error')
                return render_template('staff/edit_profile.html', user=current_user)
            
            if not email:
                flash('Email address is required.', 'error')
                return render_template('staff/edit_profile.html', user=current_user)
            
            # Username validation and uniqueness check
            import re
            if not re.match(r'^[a-zA-Z0-9_]{3,}$', username):
                flash('Username must be at least 3 characters and contain only letters, numbers, and underscores.', 'error')
                return render_template('staff/edit_profile.html', user=current_user)
            
            # Check if username is already taken by another user
            if username != current_user.username:
                existing_user = User.query.filter_by(username=username).first()
                if existing_user:
                    flash('Username is already taken. Please choose a different one.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
            
            # Email validation and uniqueness check
            email_regex = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
            if not email_regex.match(email):
                flash('Please enter a valid email address.', 'error')
                return render_template('staff/edit_profile.html', user=current_user)
            
            # Check if email is already taken by another user
            if email != current_user.email:
                existing_user = User.query.filter_by(email=email).first()
                if existing_user:
                    flash('Email address is already taken. Please choose a different one.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
            
            # Password change validation (only if user is trying to change password)
            if current_password or new_password or confirm_password:
                if not current_password:
                    flash('Current password is required to change password.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
                
                if not current_user.check_password(current_password):
                    flash('Current password is incorrect.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
                
                if not new_password:
                    flash('New password is required.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
                
                if len(new_password) < 8:
                    flash('New password must be at least 8 characters long.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
                
                if new_password != confirm_password:
                    flash('New password and confirmation do not match.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
                
                # Update password
                current_user.set_password(new_password)
            
            # Update user data
            current_user.full_name = full_name
            current_user.username = username
            current_user.email = email
            current_user.phone = phone if phone else None
            current_user.bio = bio if bio else None
            current_user.updated_at = datetime.utcnow()
            
            # Handle photo upload
            photo = request.files.get('photo')
            if photo and photo.filename:
                # Validate file type and content
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                if '.' in photo.filename and photo.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    # Additional MIME type validation
                    from werkzeug.utils import secure_filename
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(photo.filename)
                    allowed_mimes = {'image/png', 'image/jpeg', 'image/jpg', 'image/gif'}
                    
                    if mime_type not in allowed_mimes:
                        flash('Invalid file type. Please upload a valid image file.', 'error')
                        return render_template('staff/edit_profile.html', user=current_user)
                    filename = secure_filename(f"{current_user.username}_{photo.filename}")
                    upload_path = os.path.join('static/uploads/photos', filename)
                    
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                    
                    # Delete old photo if exists
                    if current_user.photo:
                        old_photo_path = os.path.join('static', current_user.photo)
                        if os.path.exists(old_photo_path):
                            try:
                                os.remove(old_photo_path)
                            except Exception as e:
                                # Log error but don't fail the update
                                pass
                    
                    photo.save(upload_path)
                    current_user.photo = f'uploads/photos/{filename}'
                else:
                    flash('Invalid file type. Please upload PNG, JPG, JPEG, or GIF files only.', 'error')
                    return render_template('staff/edit_profile.html', user=current_user)
            
            db.session.commit()
            
            # Success message
            flash('Profile updated successfully!', 'success')
            
            # Redirect back to appropriate dashboard
            if current_user.role_type == RoleType.ADMIN:
                return redirect(url_for('staff.admin_dashboard'))
            elif current_user.role_type == RoleType.EXECUTIVE:
                return redirect(url_for('staff.executive_dashboard'))
            elif current_user.role_type == RoleType.AUDITOR_GENERAL:
                return redirect(url_for('staff.auditor_general_dashboard'))
            elif current_user.role_type == RoleType.ZONAL_COORDINATOR:
                return redirect(url_for('staff.zonal_dashboard'))
            elif current_user.role_type == RoleType.LGA_LEADER:
                return redirect(url_for('staff.lga_dashboard'))
            elif current_user.role_type == RoleType.WARD_LEADER:
                return redirect(url_for('staff.ward_dashboard'))
            else:
                return redirect(url_for('core.home'))
        
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile. Please try again.', 'error')
    
    return render_template('staff/edit_profile.html', user=current_user)

# Zone Management Routes
@staff.route('/zones/<int:zone_id>/details')
@login_required
def zone_details(zone_id):
    """Get zone details for the modal view"""
    # Check permissions - only admin and executives can view zone details
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get the zone with related data
        zone = Zone.query.get_or_404(zone_id)
        
        # Get zone statistics
        total_lgas = zone.lgas.count()
        total_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.APPROVED).count()
        pending_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.PENDING).count()
        
        # Get zone coordinator
        coordinator = zone.get_coordinator()
        
        # Get LGAs in the zone
        lgas = zone.lgas.all()
        lga_data = []
        for lga in lgas:
            lga_users = User.query.filter_by(lga_id=lga.id, approval_status=ApprovalStatus.APPROVED).count()
            lga_coordinator = lga.get_coordinator()
            lga_data.append({
                'name': lga.name,
                'users_count': lga_users,
                'coordinator': lga_coordinator.full_name if lga_coordinator else 'Not Assigned'
            })
        
        # Recent activities (messages sent to zone)
        recent_messages = Message.query.join(User, Message.recipient_id == User.id)\
                                      .filter(User.zone_id == zone_id)\
                                      .filter(Message.message_type == 'announcement')\
                                      .order_by(Message.created_at.desc())\
                                      .limit(5).all()
        
        zone_data = {
            'id': zone.id,
            'name': zone.name,
            'description': zone.description or 'No description available',
            'total_lgas': total_lgas,
            'total_users': total_users,
            'pending_users': pending_users,
            'coordinator': {
                'name': coordinator.full_name if coordinator else 'Not Assigned',
                'email': coordinator.email if coordinator else None,
                'phone': coordinator.phone if coordinator else None
            },
            'lgas': lga_data,
            'recent_messages': [
                {
                    'subject': msg.subject,
                    'date': msg.get_formatted_date(),
                    'sender': msg.sender.full_name
                } for msg in recent_messages
            ]
        }
        
        return jsonify(zone_data)
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch zone details: {str(e)}'}), 500

@staff.route('/zones/<int:zone_id>/manage')
@login_required
def zone_management(zone_id):
    """Zone management interface"""
    # Check permissions - only admin and executives can manage zones
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied. Only admin and executives can manage zones.', 'error')
        return redirect(url_for('staff.dashboard'))
    
    try:
        zone = Zone.query.get_or_404(zone_id)
        
        # Get zone statistics
        total_lgas = zone.lgas.count()
        total_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.APPROVED).count()
        pending_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.PENDING).count()
        
        # Get zone coordinator
        coordinator = zone.get_coordinator()
        
        # Get users in the zone
        zone_users = User.query.filter_by(zone_id=zone_id)\
                              .order_by(User.approval_status, User.role_type, User.full_name)\
                              .all()
        
        # Get LGAs in the zone
        lgas = zone.lgas.all()
        
        return render_template('staff/zone_management.html',
                             zone=zone,
                             coordinator=coordinator,
                             total_lgas=total_lgas,
                             total_users=total_users,
                             pending_users=pending_users,
                             zone_users=zone_users,
                             lgas=lgas)
        
    except Exception as e:
        flash(f'Error loading zone management: {str(e)}', 'error')
        return redirect(url_for('staff.admin_dashboard'))

@staff.route('/zones/<int:zone_id>/reports')
@login_required
def zone_reports(zone_id):
    """Zone reporting interface"""
    # Check permissions - only admin and executives can view zone reports
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied. Only admin and executives can view zone reports.', 'error')
        return redirect(url_for('staff.dashboard'))
    
    try:
        zone = Zone.query.get_or_404(zone_id)
        
        # Zone Performance Metrics
        total_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.APPROVED).count()
        pending_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.PENDING).count()
        rejected_users = User.query.filter_by(zone_id=zone_id, approval_status=ApprovalStatus.REJECTED).count()
        
        # User distribution by role
        role_distribution = db.session.query(User.role_type, func.count(User.id))\
                                     .filter_by(zone_id=zone_id, approval_status=ApprovalStatus.APPROVED)\
                                     .group_by(User.role_type).all()
        
        # Monthly user registration trends
        from sqlalchemy import extract, func
        monthly_registrations = db.session.query(
            extract('month', User.created_at).label('month'),
            extract('year', User.created_at).label('year'),
            func.count(User.id).label('count')
        ).filter_by(zone_id=zone_id)\
         .group_by(extract('year', User.created_at), extract('month', User.created_at))\
         .order_by(extract('year', User.created_at), extract('month', User.created_at))\
         .limit(12).all()
        
        # LGA Performance within the zone
        lga_performance = []
        for lga in zone.lgas:
            lga_users = User.query.filter_by(lga_id=lga.id, approval_status=ApprovalStatus.APPROVED).count()
            lga_pending = User.query.filter_by(lga_id=lga.id, approval_status=ApprovalStatus.PENDING).count()
            lga_coordinator = lga.get_coordinator()
            
            lga_performance.append({
                'name': lga.name,
                'users': lga_users,
                'pending': lga_pending,
                'coordinator': lga_coordinator.full_name if lga_coordinator else 'Not Assigned',
                'performance_score': min(100, (lga_users / max(1, lga_users + lga_pending)) * 100)
            })
        
        # Recent activity summary
        recent_messages = Message.query.join(User, Message.recipient_id == User.id)\
                                      .filter(User.zone_id == zone_id)\
                                      .filter(Message.message_type == 'announcement')\
                                      .order_by(Message.created_at.desc())\
                                      .limit(10).all()
        
        return render_template('staff/zone_reports.html',
                             zone=zone,
                             total_users=total_users,
                             pending_users=pending_users,
                             rejected_users=rejected_users,
                             role_distribution=role_distribution,
                             monthly_registrations=monthly_registrations,
                             lga_performance=lga_performance,
                             recent_messages=recent_messages)
        
    except Exception as e:
        flash(f'Error loading zone reports: {str(e)}', 'error')
        return redirect(url_for('staff.admin_dashboard'))