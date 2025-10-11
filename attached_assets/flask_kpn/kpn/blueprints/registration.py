from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models import *
from werkzeug.utils import secure_filename
import os
import requests
from datetime import datetime
from utils.activity_tracker import log_activity, auto_track_facebook_follow

# Define valid positions for each role type (server-side validation)
VALID_ROLE_POSITIONS = {
    'executive': [
        'State Coordinator', 'Deputy State Coordinator', 'General Secretary',
        'Assistant General Secretary', 'State Supervisor', 'Legal & Ethics Adviser',
        'Treasurer', 'Financial Secretary', 'Director of Mobilization',
        'Assistant Director of Mobilization', 'Organizing Secretary',
        'Assistant Organizing Secretary', 'Auditor General',
        'Welfare Officer', 'Youth Development & Empowerment Officer',
        'Women Leader', 'Assistant Women Leader', 'Director of Media & Publicity',
        'Assistant Director of Media & Publicity', 'Public Relations & Community Engagement Officer'
    ],
    'zonal_coordinator': [
        'Zonal Coordinator', 'Zonal Secretary', 'Zonal Publicity'
    ],
    'lga_leader': [
        'LGA Coordinator', 'Secretary', 'Organizing Secretary', 'Treasurer',
        'Publicity', 'LGA Supervisor', 'Women Leader', 'Welfare Officer',
        'Director Contact and Mobilization', 'LGA Adviser'
    ],
    'ward_leader': [
        'Ward Coordinator', 'Secretary', 'Organizing Secretary', 'Treasurer',
        'Publicity', 'Financial Secretary', 'Ward Supervisor', 'Ward Adviser'
    ]
}

registration = Blueprint('registration', __name__)

# Facebook App Configuration (secure environment variables)
FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET')
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID', '')  # KPN Official Page ID removed

# Validate Facebook configuration
if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
    print("Warning: Facebook integration requires FACEBOOK_APP_ID and FACEBOOK_APP_SECRET environment variables")

@registration.route('/', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        full_name = request.form['full_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form.get('phone')
        bio = request.form.get('bio')
        zone_id = request.form.get('zone_id')
        lga_id = request.form.get('lga_id')
        ward_id = request.form.get('ward_id')
        role_type = request.form.get('role_type')
        role_title = request.form.get('role_title')
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('registration.register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('registration.register'))
        
        # Validate role_title for leadership roles
        if role_type and role_type != 'general_member' and role_title:
            valid_positions = VALID_ROLE_POSITIONS.get(role_type, [])
            if role_title not in valid_positions:
                flash(f'Invalid position selected for {role_type.replace("_", " ").title()}. Please select a valid position.', 'error')
                zones = Zone.query.all()
                return render_template('registration/register.html', zones=zones)
        elif role_type and role_type != 'general_member':
            flash('Please select a specific position for your leadership role.', 'error')
            zones = Zone.query.all()
            return render_template('registration/register.html', zones=zones)

        # Normalize role_type to RoleType enum for consistent handling
        role_enum = RoleType.GENERAL_MEMBER  # Default
        if role_type and role_type != 'general_member':
            try:
                role_enum = RoleType[role_type.upper()]
            except KeyError:
                role_enum = RoleType.GENERAL_MEMBER
                flash('Invalid role type. You have been registered as a General Member.', 'warning')
        
        # Check seat availability for leadership roles
        seat_available = True
        if role_enum != RoleType.GENERAL_MEMBER:
            seat_available = check_seat_availability(role_enum.name, role_title, zone_id, lga_id, ward_id)
        
        if not seat_available:
            flash('The selected leadership position is no longer available. You have been registered as a General Member.', 'warning')
            role_enum = RoleType.GENERAL_MEMBER
            role_title = None
        
        # Create user
        user = User(
            full_name=full_name,
            username=username,
            email=email,
            phone=phone,
            whatsapp_number=phone or '08000000000',  # Default WhatsApp number
            bio=bio,
            zone_id=zone_id if zone_id else None,
            lga_id=lga_id if lga_id else None,
            ward_id=ward_id if ward_id else None,
            role_type=role_enum,
            role_title=role_title,
            approval_status=ApprovalStatus.PENDING
        )
        user.set_password(password)
        
        # Handle photo upload
        photo = request.files.get('photo')
        if photo and photo.filename:
            filename = secure_filename(f"{username}_{photo.filename}")
            upload_path = os.path.join('static/uploads/photos', filename)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)
            photo.save(upload_path)
            user.photo = filename
        
        db.session.add(user)
        db.session.commit()
        
        # Store user ID in session for Facebook verification
        session['pending_user_id'] = user.id
        session['facebook_verification_required'] = True
        
        flash('Registration successful! Please complete Facebook verification to activate your account.', 'success')
        return redirect(url_for('registration.facebook_verification'))
    
    # GET request - show registration form
    zones = Zone.query.all()
    return render_template('registration/register.html', zones=zones)

@registration.route('/facebook-verification')
def facebook_verification():
    if 'pending_user_id' not in session:
        flash('No pending registration found.', 'error')
        return redirect(url_for('core.home'))
    
    user = User.query.get(session['pending_user_id'])
    if not user:
        flash('Registration not found.', 'error')
        return redirect(url_for('core.home'))
    
    return render_template('registration/facebook_verification.html', 
                         user=user, 
                         facebook_app_id=FACEBOOK_APP_ID,
                         facebook_page_id=FACEBOOK_PAGE_ID)

@registration.route('/verify-facebook', methods=['POST'])
def verify_facebook():
    if 'pending_user_id' not in session:
        return jsonify({'success': False, 'message': 'No pending registration'})
    
    user_id = session['pending_user_id']
    facebook_user_id = request.json.get('facebook_user_id') if request.json else None
    access_token = request.json.get('access_token') if request.json else None
    
    if not facebook_user_id or not access_token:
        return jsonify({'success': False, 'message': 'Missing Facebook data'})
    
    # Verify the user follows the KPN page
    follows_page = verify_facebook_page_follow(facebook_user_id, access_token)
    
    user = User.query.get(user_id)
    if user:
        user.facebook_user_id = facebook_user_id
        user.facebook_verified = follows_page
        user.facebook_follow_date = datetime.utcnow() if follows_page else None
        
        # Auto-approve general members who verify Facebook
        if user.role_type == RoleType.GENERAL_MEMBER and follows_page:
            user.approval_status = ApprovalStatus.APPROVED
        
        db.session.commit()
        
        # Track Facebook follow activity if successful
        if follows_page:
            try:
                # Log the Facebook follow activity
                auto_track_facebook_follow(user.id)
                
                # Log profile completion activity
                log_activity(
                    user_id=user.id,
                    activity_type='profile_completed',
                    description=f"Completed registration and Facebook verification for {user.role_type.value} role"
                )
            except Exception as e:
                print(f"Error tracking Facebook verification activity: {str(e)}")
        
        # Clear session
        session.pop('pending_user_id', None)
        session.pop('facebook_verification_required', None)
        
        if follows_page:
            return jsonify({
                'success': True, 
                'message': 'Facebook verification successful! Your registration is complete.',
                'approved': user.approval_status == ApprovalStatus.APPROVED
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Please follow our official Facebook page to complete registration.'
            })
    
    return jsonify({'success': False, 'message': 'User not found'})

def verify_facebook_page_follow(facebook_user_id, access_token):
    """Verify if user follows the KPN Facebook page"""
    # Check if Facebook is properly configured
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET or not FACEBOOK_PAGE_ID:
        print("Facebook integration not properly configured")
        return False
        
    try:
        # Validate access token first
        token_url = f"https://graph.facebook.com/v18.0/me"
        token_params = {'access_token': access_token, 'fields': 'id'}
        token_response = requests.get(token_url, params=token_params, timeout=10)
        
        if token_response.status_code != 200:
            print("Invalid Facebook access token")
            return False
            
        token_data = token_response.json()
        if token_data.get('id') != facebook_user_id:
            print("Access token does not match user ID")
            return False
        
        # Check if user likes/follows the page
        url = f"https://graph.facebook.com/v18.0/{FACEBOOK_PAGE_ID}/likes"
        params = {
            'access_token': access_token,
            'fields': 'id,name',
            'limit': 100  # Limit response size
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Check if user is in the likes data
            if 'data' in data:
                for like in data['data']:
                    if like.get('id') == facebook_user_id:
                        return True
        elif response.status_code == 400:
            error_data = response.json()
            print(f"Facebook API error: {error_data.get('error', {}).get('message', 'Unknown error')}")
        else:
            print(f"Facebook API returned status code: {response.status_code}")
        
        return False
    except requests.exceptions.Timeout:
        print("Facebook API request timed out")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Facebook API request error: {e}")
        return False
    except Exception as e:
        print(f"Facebook verification error: {e}")
        return False

def check_seat_availability(role_type, role_title, zone_id, lga_id, ward_id):
    """Check if a leadership seat is available"""
    
    # Convert role_type to RoleType enum for consistent comparison
    try:
        role_enum = RoleType[role_type] if isinstance(role_type, str) else role_type
    except KeyError:
        return True  # Unknown role type, allow registration
    
    # Executive seats (State level) - 20 total
    if role_enum == RoleType.EXECUTIVE:
        current_executives = User.query.filter_by(
            role_type=RoleType.EXECUTIVE,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return current_executives < 20
    
    # Zonal Coordinator seats - 3 per zone
    elif role_enum == RoleType.ZONAL_COORDINATOR and zone_id:
        current_zonal = User.query.filter_by(
            role_type=RoleType.ZONAL_COORDINATOR,
            zone_id=zone_id,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return current_zonal < 3
    
    # LGA Leader seats - 10 per LGA
    elif role_enum == RoleType.LGA_LEADER and lga_id:
        current_lga = User.query.filter_by(
            role_type=RoleType.LGA_LEADER,
            lga_id=lga_id,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return current_lga < 10
    
    # Ward Leader seats - 8 per ward
    elif role_enum == RoleType.WARD_LEADER and ward_id:
        current_ward = User.query.filter_by(
            role_type=RoleType.WARD_LEADER,
            ward_id=ward_id,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return current_ward < 8
    
    return True

@registration.route('/api/lgas/<int:zone_id>')
def get_lgas(zone_id):
    """API endpoint to get LGAs for a zone"""
    lgas = LGA.query.filter_by(zone_id=zone_id).all()
    return jsonify([{'id': lga.id, 'name': lga.name} for lga in lgas])

@registration.route('/api/wards/<int:lga_id>')
def get_wards(lga_id):
    """API endpoint to get wards for an LGA"""
    wards = Ward.query.filter_by(lga_id=lga_id).all()
    return jsonify([{'id': ward.id, 'name': ward.name} for ward in wards])

@registration.route('/api/available-positions')
def get_available_positions():
    """API endpoint to get available positions based on role level and location"""
    role_level = request.args.get('role_level')
    zone_id = request.args.get('zone_id', type=int)
    lga_id = request.args.get('lga_id', type=int)
    ward_id = request.args.get('ward_id', type=int)
    
    if not role_level:
        return jsonify({'error': 'Role level is required'}), 400
    
    # Get all positions for this role level
    all_positions = VALID_ROLE_POSITIONS.get(role_level.lower(), [])
    available_positions = []
    
    for position in all_positions:
        # Check if this specific position is available
        # Convert role_level to uppercase for checking
        role_level_upper = role_level.upper()
        is_available = check_position_availability(role_level_upper, position, zone_id, lga_id, ward_id)
        if is_available:
            available_positions.append(position)
    
    # Get seat limits and current counts for display
    seat_info = get_seat_info(role_level, zone_id, lga_id, ward_id)
    
    return jsonify({
        'available_positions': available_positions,
        'seat_info': seat_info
    })

def check_position_availability(role_type, role_title, zone_id, lga_id, ward_id):
    """Check if a specific position is available"""
    # First check general seat availability
    if not check_seat_availability(role_type, role_title, zone_id, lga_id, ward_id):
        return False
    
    # Convert role_type to RoleType enum for consistent comparison
    try:
        role_enum = RoleType[role_type] if isinstance(role_type, str) else role_type
    except KeyError:
        return True  # Unknown role type, allow registration
    
    # Then check if this specific title is already taken
    query_filters = {
        'role_type': role_enum,
        'role_title': role_title,
        'approval_status': ApprovalStatus.APPROVED
    }
    
    # Add location filters based on role type
    if role_enum == RoleType.ZONAL_COORDINATOR and zone_id:
        query_filters['zone_id'] = zone_id
    elif role_enum == RoleType.LGA_LEADER and lga_id:
        query_filters['lga_id'] = lga_id
    elif role_enum == RoleType.WARD_LEADER and ward_id:
        query_filters['ward_id'] = ward_id
    
    # Check if position is already filled
    existing_user = User.query.filter_by(**query_filters).first()
    return existing_user is None

def get_seat_info(role_type, zone_id, lga_id, ward_id):
    """Get seat information for display"""
    if role_type == 'EXECUTIVE':
        current_count = User.query.filter_by(
            role_type=RoleType.EXECUTIVE,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return {'current': current_count, 'total': 20, 'available': 20 - current_count}
    
    elif role_type == 'ZONAL_COORDINATOR' and zone_id:
        current_count = User.query.filter_by(
            role_type=RoleType.ZONAL_COORDINATOR,
            zone_id=zone_id,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return {'current': current_count, 'total': 3, 'available': 3 - current_count}
    
    elif role_type == 'LGA_LEADER' and lga_id:
        current_count = User.query.filter_by(
            role_type=RoleType.LGA_LEADER,
            lga_id=lga_id,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return {'current': current_count, 'total': 10, 'available': 10 - current_count}
    
    elif role_type == 'WARD_LEADER' and ward_id:
        current_count = User.query.filter_by(
            role_type=RoleType.WARD_LEADER,
            ward_id=ward_id,
            approval_status=ApprovalStatus.APPROVED
        ).count()
        return {'current': current_count, 'total': 8, 'available': 8 - current_count}
    
    return {'current': 0, 'total': 0, 'available': 0}