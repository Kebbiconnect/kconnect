from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from .models import User, DisciplinaryAction, WomensProgram, YouthProgram, WelfareProgram, CommunityOutreach, WardMeeting, WardMeetingAttendance
from .decorators import specific_role_required, role_required, approved_leader_required
from .forms import MemberMobilizationFilterForm, CommunityOutreachForm, WardMeetingForm, WardMeetingAttendanceForm
from leadership.models import Zone, LGA, Ward, RoleDefinition
from core.models import Report
from campaigns.models import Campaign
from media.models import MediaItem
from events.models import Event

def login_view(request):
    if request.user.is_authenticated:
        return redirect('staff:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.status == 'APPROVED':
                login(request, user)
                messages.success(request, f'Welcome back, {user.get_full_name()}!')
                return redirect('staff:dashboard')
            elif user.status == 'PENDING':
                messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
            elif user.status == 'SUSPENDED':
                messages.error(request, 'Your account has been suspended. Contact admin for more information.')
            elif user.status == 'DISMISSED':
                messages.error(request, 'Your account has been dismissed.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'staff/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('core:home')

@ratelimit(key='ip', rate='5/h', method='POST', block=True)
def register(request):
    if request.user.is_authenticated:
        return redirect('staff:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        bio = request.POST.get('bio', '')
        gender = request.POST.get('gender', '')
        
        zone_id = request.POST.get('zone')
        lga_id = request.POST.get('lga')
        ward_id = request.POST.get('ward')
        role_definition_id = request.POST.get('role_definition')
        
        facebook_verified = request.POST.get('facebook_verified') == 'on'
        
        if not facebook_verified:
            messages.error(request, 'You must follow our Facebook page to complete registration.')
            return redirect('staff:register')
        
        if password1 != password2:
            messages.error(request, 'Passwords do not match.')
            return redirect('staff:register')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return redirect('staff:register')
        
        try:
            zone = Zone.objects.get(id=zone_id) if zone_id else None
            lga = LGA.objects.get(id=lga_id) if lga_id else None
            ward = Ward.objects.get(id=ward_id) if ward_id else None
        except (Zone.DoesNotExist, LGA.DoesNotExist, Ward.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Invalid location selection.')
            return redirect('staff:register')
        
        role = 'GENERAL'
        role_definition = None
        status = 'APPROVED'
        
        if role_definition_id:
            try:
                role_definition = RoleDefinition.objects.get(id=role_definition_id)
            except (RoleDefinition.DoesNotExist, ValueError, TypeError):
                messages.error(request, 'Invalid role selection.')
                return redirect('staff:register')
            
            role = role_definition.tier
            status = 'PENDING'
            
            if role == 'STATE':
                if not zone or not lga:
                    messages.error(request, 'Zone and LGA are required for State Executive roles.')
                    return redirect('staff:register')
            elif role == 'ZONAL':
                if not zone:
                    messages.error(request, 'Zone is required for Zonal Coordinator roles.')
                    return redirect('staff:register')
            elif role == 'LGA':
                if not lga:
                    messages.error(request, 'LGA is required for LGA Coordinator roles.')
                    return redirect('staff:register')
            elif role == 'WARD':
                if not ward:
                    messages.error(request, 'Ward is required for Ward Leader roles.')
                    return redirect('staff:register')
            
            existing_holder = User.objects.filter(
                role_definition=role_definition,
                status='APPROVED'
            )
            
            if role == 'ZONAL':
                existing_holder = existing_holder.filter(zone=zone)
            elif role == 'LGA':
                existing_holder = existing_holder.filter(lga=lga)
            elif role == 'WARD':
                existing_holder = existing_holder.filter(ward=ward)
            
            if existing_holder.exists():
                messages.error(request, 'This position is already filled.')
                return redirect('staff:register')
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            bio=bio,
            gender=gender,
            zone=zone,
            lga=lga,
            ward=ward,
            role=role,
            role_definition=role_definition,
            status=status,
            facebook_verified=facebook_verified
        )
        
        if status == 'APPROVED':
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to KPN.')
            return redirect('staff:dashboard')
        else:
            messages.success(request, 'Registration successful! Your application is pending approval.')
            return redirect('staff:login')
    
    zones = Zone.objects.all()
    lgas = LGA.objects.all()
    wards = Ward.objects.all()
    role_definitions = RoleDefinition.objects.all()
    
    context = {
        'zones': zones,
        'lgas': lgas,
        'wards': wards,
        'role_definitions': role_definitions,
    }
    return render(request, 'staff/register.html', context)

@login_required
def dashboard(request):
    user = request.user
    
    if user.status != 'APPROVED':
        messages.warning(request, 'Your account is pending approval.')
        return render(request, 'staff/pending_approval.html')
    
    if user.role == 'GENERAL':
        return redirect('staff:profile')
    
    if user.role_definition:
        role_title = user.role_definition.title
        
        role_mapping = {
            'President': 'president_dashboard',
            'Vice President': 'vice_president_dashboard',
            'General Secretary': 'general_secretary_dashboard',
            'Assistant General Secretary': 'assistant_general_secretary_dashboard',
            'State Supervisor': 'state_supervisor_dashboard',
            'Legal & Ethics Adviser': 'legal_ethics_adviser_dashboard',
            'Treasurer': 'treasurer_dashboard' if user.role == 'STATE' else 'lga_treasurer_dashboard' if user.role == 'LGA' else 'ward_treasurer_dashboard',
            'Financial Secretary': 'financial_secretary_dashboard' if user.role == 'STATE' else 'ward_financial_secretary_dashboard',
            'Director of Mobilization': 'director_of_mobilization_dashboard',
            'Assistant Director of Mobilization': 'assistant_director_of_mobilization_dashboard',
            'Organizing Secretary': 'organizing_secretary_dashboard' if user.role == 'STATE' else 'lga_organizing_secretary_dashboard' if user.role == 'LGA' else 'ward_organizing_secretary_dashboard',
            'Assistant Organizing Secretary': 'assistant_organizing_secretary_dashboard',
            'Auditor General': 'auditor_general_dashboard',
            'Welfare Officer': 'welfare_officer_dashboard' if user.role == 'STATE' else 'lga_welfare_officer_dashboard',
            'Youth Development & Empowerment Officer': 'youth_empowerment_officer_dashboard',
            'Women Leader': 'women_leader_dashboard' if user.role == 'STATE' else 'lga_women_leader_dashboard',
            'Assistant Women Leader': 'assistant_women_leader_dashboard',
            'Director of Media & Publicity': 'media_director_dashboard',
            'Assistant Director of Media & Publicity': 'assistant_media_director_dashboard',
            'Public Relations & Community Engagement Officer': 'pr_officer_dashboard',
            'Zonal Coordinator': 'zonal_coordinator_dashboard',
            'Zonal Secretary': 'zonal_secretary_dashboard',
            'Zonal Publicity Officer': 'zonal_publicity_officer_dashboard',
            'LGA Coordinator': 'lga_coordinator_dashboard',
            'Secretary': 'lga_secretary_dashboard' if user.role == 'LGA' else 'ward_secretary_dashboard',
            'Publicity Officer': 'lga_publicity_officer_dashboard' if user.role == 'LGA' else 'ward_publicity_officer_dashboard',
            'LGA Supervisor': 'lga_supervisor_dashboard',
            'Director of Contact and Mobilization': 'lga_contact_mobilization_dashboard',
            'LGA Adviser': 'lga_adviser_dashboard',
            'Ward Coordinator': 'ward_coordinator_dashboard',
            'Ward Supervisor': 'ward_supervisor_dashboard',
            'Ward Adviser': 'ward_adviser_dashboard',
        }
        
        dashboard_name = role_mapping.get(role_title)
        if dashboard_name:
            return redirect(f'staff:{dashboard_name}')
    
    context = {
        'user': user,
        'role_title': user.role_definition.title if user.role_definition else 'Leader',
    }
    
    return render(request, 'staff/dashboard.html', context)

@login_required
def profile(request):
    user = request.user
    can_upload_photo = user.status == 'APPROVED' and user.role in ['STATE', 'ZONAL']
    
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name')
        request.user.last_name = request.POST.get('last_name')
        request.user.email = request.POST.get('email')
        request.user.phone = request.POST.get('phone')
        request.user.bio = request.POST.get('bio', '')
        request.user.gender = request.POST.get('gender', '')
        
        if request.FILES.get('photo'):
            if can_upload_photo:
                request.user.photo = request.FILES['photo']
            else:
                messages.warning(request, 'Profile photo upload is only available for State Executive and Zonal Coordinator roles.')
        
        request.user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('staff:profile')
    
    context = {
        'can_upload_photo': can_upload_photo
    }
    return render(request, 'staff/profile.html', context)

@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect.')
            return redirect('staff:change_password')
        
        if new_password1 != new_password2:
            messages.error(request, 'New passwords do not match.')
            return redirect('staff:change_password')
        
        if len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('staff:change_password')
        
        request.user.set_password(new_password1)
        request.user.save()
        
        login(request, request.user)
        
        messages.success(request, 'Your password has been changed successfully!')
        return redirect('staff:profile')
    
    return render(request, 'staff/change_password.html')

@ratelimit(key='ip', rate='3/h', method='POST', block=True)
def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        try:
            user = User.objects.get(email=email)
            
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            reset_link = request.build_absolute_uri(
                f'/account/reset-password/{uid}/{token}/'
            )
            
            message = f'''
Hello {user.get_full_name()},

You have requested to reset your password for your KPN account.

Please click the link below to reset your password:
{reset_link}

If you did not request this password reset, please ignore this email.

This link will expire in 24 hours.

Best regards,
Kebbi Progressive Network Team
            '''
            
            try:
                send_mail(
                    'KPN Password Reset Request',
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                messages.success(request, 'Password reset instructions have been sent to your email.')
            except Exception as e:
                messages.error(request, 'Unable to send email. Please contact support.')
            
            return redirect('staff:login')
            
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return redirect('staff:forgot_password')
    
    return render(request, 'staff/forgot_password.html')

@ratelimit(key='ip', rate='5/h', method='POST', block=True)
def reset_password(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if password1 != password2:
                messages.error(request, 'Passwords do not match.')
                return redirect('staff:reset_password', uidb64=uidb64, token=token)
            
            if len(password1) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
                return redirect('staff:reset_password', uidb64=uidb64, token=token)
            
            user.set_password(password1)
            user.save()
            
            messages.success(request, 'Your password has been reset successfully! You can now login.')
            return redirect('staff:login')
        
        return render(request, 'staff/reset_password.html', {'validlink': True})
    else:
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('staff:forgot_password')

def get_lgas_by_zone(request):
    zone_id = request.GET.get('zone_id')
    
    if not zone_id:
        return JsonResponse({'lgas': []})
    
    try:
        zone = Zone.objects.get(id=zone_id)
        lgas = LGA.objects.filter(zone=zone).values('id', 'name')
        return JsonResponse({'lgas': list(lgas)})
    except (Zone.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'lgas': []})

def get_wards_by_lga(request):
    lga_id = request.GET.get('lga_id')
    
    if not lga_id:
        return JsonResponse({'wards': []})
    
    try:
        lga = LGA.objects.get(id=lga_id)
        wards = Ward.objects.filter(lga=lga).values('id', 'name')
        return JsonResponse({'wards': list(wards)})
    except (LGA.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'wards': []})

def check_vacant_roles(request):
    zone_id = request.GET.get('zone_id')
    lga_id = request.GET.get('lga_id')
    ward_id = request.GET.get('ward_id')
    
    vacant_roles = []
    
    try:
        zone = Zone.objects.get(id=zone_id) if zone_id else None
    except (Zone.DoesNotExist, ValueError, TypeError):
        zone = None
    
    try:
        lga = LGA.objects.get(id=lga_id) if lga_id else None
    except (LGA.DoesNotExist, ValueError, TypeError):
        lga = None
    
    try:
        ward = Ward.objects.get(id=ward_id) if ward_id else None
    except (Ward.DoesNotExist, ValueError, TypeError):
        ward = None
    
    if zone and lga:
        state_roles = RoleDefinition.objects.filter(tier='STATE')
        for role in state_roles:
            existing = User.objects.filter(
                role_definition=role,
                status='APPROVED'
            ).exists()
            if not existing:
                vacant_roles.append({
                    'id': role.id,
                    'title': role.title,
                    'tier': role.tier
                })
    
    if zone:
        zonal_roles = RoleDefinition.objects.filter(tier='ZONAL')
        for role in zonal_roles:
            existing = User.objects.filter(
                role_definition=role,
                zone=zone,
                status='APPROVED'
            ).exists()
            if not existing:
                vacant_roles.append({
                    'id': role.id,
                    'title': role.title,
                    'tier': role.tier
                })
    
    if lga:
        lga_roles = RoleDefinition.objects.filter(tier='LGA')
        for role in lga_roles:
            existing = User.objects.filter(
                role_definition=role,
                lga=lga,
                status='APPROVED'
            ).exists()
            if not existing:
                vacant_roles.append({
                    'id': role.id,
                    'title': role.title,
                    'tier': role.tier
                })
    
    if ward:
        ward_roles = RoleDefinition.objects.filter(tier='WARD')
        for role in ward_roles:
            existing = User.objects.filter(
                role_definition=role,
                ward=ward,
                status='APPROVED'
            ).exists()
            if not existing:
                vacant_roles.append({
                    'id': role.id,
                    'title': role.title,
                    'tier': role.tier
                })
    
    return JsonResponse({
        'vacant_roles': vacant_roles
    })

@specific_role_required('President')
def president_dashboard(request):
    from leadership.models import Zone
    from campaigns.models import Campaign
    from events.models import Event
    from donations.models import Donation, Expense
    from core.models import FAQ
    from staff.models import WomensProgram, YouthProgram, WelfareProgram
    from django.db.models import Sum
    
    # Member statistics
    pending_approvals = User.objects.filter(status='PENDING').count()
    total_members = User.objects.filter(status='APPROVED').count()
    total_leaders = User.objects.filter(status='APPROVED').exclude(role='GENERAL').count()
    male_members = User.objects.filter(status='APPROVED', gender='M').count()
    female_members = User.objects.filter(status='APPROVED', gender='F').count()
    
    # Campaign statistics
    total_campaigns = Campaign.objects.count()
    active_campaigns = Campaign.objects.filter(status='PUBLISHED').count()
    pending_campaigns = Campaign.objects.filter(status='PENDING').count()
    
    # Event statistics  
    upcoming_events = Event.objects.filter(start_date__gte=timezone.now()).count()
    total_events = Event.objects.count()
    
    # Financial statistics
    total_donations = Donation.objects.filter(status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
    pending_donations = Donation.objects.filter(status='UNVERIFIED').count()
    total_expenses = Expense.objects.aggregate(total=Sum('amount'))['total'] or 0
    
    # Disciplinary actions
    pending_disciplinary = DisciplinaryAction.objects.filter(is_approved=False).count()
    
    # Reporting statistics
    pending_reports = Report.objects.filter(is_reviewed=False).count()
    total_reports = Report.objects.count()
    
    # Organizational structure
    total_zones = Zone.objects.count()
    total_lgas = LGA.objects.count()
    total_wards = Ward.objects.count()
    
    # Programs statistics
    total_womens_programs = WomensProgram.objects.count()
    total_youth_programs = YouthProgram.objects.count()
    total_welfare_programs = WelfareProgram.objects.count()
    
    # Content
    total_faqs = FAQ.objects.count()
    
    pending_applicants = User.objects.filter(status='PENDING').order_by('-created_at')[:10]
    
    context = {
        'pending_approvals': pending_approvals,
        'total_members': total_members,
        'total_leaders': total_leaders,
        'male_members': male_members,
        'female_members': female_members,
        'total_campaigns': total_campaigns,
        'active_campaigns': active_campaigns,
        'pending_campaigns': pending_campaigns,
        'upcoming_events': upcoming_events,
        'total_events': total_events,
        'total_donations': total_donations,
        'pending_donations': pending_donations,
        'total_expenses': total_expenses,
        'pending_disciplinary': pending_disciplinary,
        'pending_reports': pending_reports,
        'total_reports': total_reports,
        'total_zones': total_zones,
        'total_lgas': total_lgas,
        'total_wards': total_wards,
        'total_womens_programs': total_womens_programs,
        'total_youth_programs': total_youth_programs,
        'total_welfare_programs': total_welfare_programs,
        'total_faqs': total_faqs,
        'pending_applicants': pending_applicants,
        'recent_activities': [],
    }
    
    return render(request, 'staff/dashboards/president.html', context)

@role_required('STATE', 'ZONAL', 'LGA')
def approve_members(request):
    if request.user.role == 'STATE':
        pending_users = User.objects.filter(status='PENDING').order_by('-created_at')
        
        zone_filter = request.GET.get('zone')
        lga_filter = request.GET.get('lga')
        ward_filter = request.GET.get('ward')
        
        if zone_filter:
            pending_users = pending_users.filter(zone_id=zone_filter)
        if lga_filter:
            pending_users = pending_users.filter(lga_id=lga_filter)
        if ward_filter:
            pending_users = pending_users.filter(ward_id=ward_filter)
        
        zones = Zone.objects.all()
        lgas = LGA.objects.all()
        wards = Ward.objects.all()
        
    elif request.user.role == 'ZONAL':
        pending_users = User.objects.filter(
            status='PENDING',
            zone=request.user.zone
        ).order_by('-created_at')
        zones = lgas = wards = None
        zone_filter = lga_filter = ward_filter = None
        
    elif request.user.role == 'LGA':
        pending_users = User.objects.filter(
            status='PENDING',
            lga=request.user.lga
        ).order_by('-created_at')
        zones = lgas = wards = None
        zone_filter = lga_filter = ward_filter = None
    else:
        pending_users = User.objects.none()
        zones = lgas = wards = None
        zone_filter = lga_filter = ward_filter = None
    
    context = {
        'pending_users': pending_users,
        'zones': zones,
        'lgas': lgas,
        'wards': wards,
        'zone_filter': zone_filter,
        'lga_filter': lga_filter,
        'ward_filter': ward_filter,
    }
    
    return render(request, 'staff/approve_members.html', context)

@role_required('STATE', 'ZONAL', 'LGA')
def review_applicant(request, user_id):
    applicant = get_object_or_404(User, id=user_id, status='PENDING')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            applicant.status = 'APPROVED'
            applicant.approved_by = request.user
            applicant.date_approved = timezone.now()
            applicant.save()
            messages.success(request, f'{applicant.get_full_name()} has been approved.')
            return redirect('staff:approve_members')
        
        elif action == 'reject':
            applicant.delete()
            messages.success(request, 'Application has been rejected and deleted.')
            return redirect('staff:approve_members')
    
    context = {
        'applicant': applicant,
    }
    
    return render(request, 'staff/review_applicant.html', context)

@role_required('STATE')
def manage_staff(request):
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    zone_filter = request.GET.get('zone', '')
    status_filter = request.GET.get('status', '')
    
    staff = User.objects.all().order_by('-created_at')
    
    if search:
        staff = staff.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search) |
            Q(email__icontains=search)
        )
    
    if role_filter:
        staff = staff.filter(role=role_filter)
    
    if zone_filter:
        staff = staff.filter(zone_id=zone_filter)
    
    if status_filter:
        staff = staff.filter(status=status_filter)
    
    zones = Zone.objects.all()
    
    context = {
        'staff': staff,
        'zones': zones,
        'search': search,
        'role_filter': role_filter,
        'zone_filter': zone_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'staff/manage_staff.html', context)

@approved_leader_required
def view_reports(request):
    """View reports submitted to the current user with dashboard statistics"""
    user = request.user
    
    filter_status = request.GET.get('status', 'all')
    
    is_president = user.role_definition and user.role_definition.title == 'President'
    is_state_supervisor = user.role_definition and user.role_definition.title == 'State Supervisor'
    
    if is_president or is_state_supervisor:
        base_reports = Report.objects.all()
    else:
        base_reports = Report.objects.filter(submitted_to=user)
    
    reports = base_reports
    
    if filter_status == 'pending':
        reports = reports.filter(status='SUBMITTED', is_reviewed=False)
    elif filter_status == 'reviewed':
        reports = reports.filter(is_reviewed=True)
    elif filter_status == 'approved':
        reports = reports.filter(status='APPROVED')
    elif filter_status == 'flagged':
        reports = reports.filter(status='FLAGGED')
    elif filter_status == 'rejected':
        reports = reports.filter(status='REJECTED')
    elif filter_status == 'escalated':
        reports = reports.filter(status='ESCALATED')
    elif filter_status == 'overdue':
        from django.utils import timezone
        today = timezone.now().date()
        reports = reports.filter(
            deadline__lt=today,
            status__in=['DRAFT', 'SUBMITTED']
        )
    
    reports = reports.select_related('submitted_by', 'submitted_to', 'reviewed_by', 'parent_report').order_by('-created_at')
    
    pending_count = base_reports.filter(status='SUBMITTED', is_reviewed=False).count()
    reviewed_count = base_reports.filter(is_reviewed=True).count()
    approved_count = base_reports.filter(status='APPROVED').count()
    flagged_count = base_reports.filter(status='FLAGGED').count()
    rejected_count = base_reports.filter(status='REJECTED').count()
    escalated_count = base_reports.filter(status='ESCALATED').count()
    
    from django.utils import timezone
    today = timezone.now().date()
    overdue_count = base_reports.filter(
        deadline__lt=today,
        status__in=['DRAFT', 'SUBMITTED']
    ).count()
    
    context = {
        'reports': reports,
        'filter_status': filter_status,
        'pending_count': pending_count,
        'reviewed_count': reviewed_count,
        'approved_count': approved_count,
        'flagged_count': flagged_count,
        'rejected_count': rejected_count,
        'escalated_count': escalated_count,
        'overdue_count': overdue_count,
        'total_count': base_reports.count(),
    }
    
    return render(request, 'staff/view_reports.html', context)

@role_required('STATE')
def disciplinary_actions(request):
    actions = DisciplinaryAction.objects.all().order_by('-created_at')
    
    context = {
        'actions': actions,
    }
    
    return render(request, 'staff/disciplinary_actions.html', context)


@approved_leader_required
def create_disciplinary_action(request):
    from .forms import DisciplinaryActionForm
    
    if request.method == 'POST':
        form = DisciplinaryActionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False)
            action.issued_by = request.user
            
            if action.action_type == 'WARNING':
                action.is_approved = True
                action.approved_by = request.user
            else:
                action.is_approved = False
                action.approved_by = None
            
            action.save()
            
            if action.action_type == 'WARNING':
                messages.success(request, f'Warning issued to {action.user.get_full_name()}.')
            else:
                messages.success(request, f'{action.get_action_type_display()} proposed for {action.user.get_full_name()}. Awaiting State President approval.')
            
            return redirect('staff:disciplinary_actions')
    else:
        form = DisciplinaryActionForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'staff/create_disciplinary_action.html', context)


@approved_leader_required
def approve_disciplinary_action(request, action_id):
    action = get_object_or_404(DisciplinaryAction, pk=action_id)
    
    if action.is_approved:
        messages.warning(request, 'This action has already been approved.')
        return redirect('staff:disciplinary_actions')
    
    if request.user.role not in ['STATE']:
        messages.error(request, 'You do not have permission to approve disciplinary actions.')
        return redirect('staff:disciplinary_actions')
    
    if request.method == 'POST':
        action.is_approved = True
        action.approved_by = request.user
        action.save()
        
        member = action.user
        
        if action.action_type == 'SUSPENSION':
            member.status = 'SUSPENDED'
            member.save()
            messages.success(request, f'{member.get_full_name()} has been suspended.')
        elif action.action_type == 'DISMISSAL':
            member.status = 'DISMISSED'
            member.save()
            messages.success(request, f'{member.get_full_name()} has been dismissed from the organization.')
        else:
            messages.success(request, f'{action.get_action_type_display()} for {member.get_full_name()} has been approved.')
        
        return redirect('staff:disciplinary_actions')
    
    context = {
        'action': action,
    }
    
    return render(request, 'staff/approve_disciplinary_action.html', context)


@approved_leader_required
def reject_disciplinary_action(request, action_id):
    action = get_object_or_404(DisciplinaryAction, pk=action_id)
    
    if action.is_approved:
        messages.warning(request, 'Cannot reject an already approved action.')
        return redirect('staff:disciplinary_actions')
    
    if request.user.role not in ['STATE']:
        messages.error(request, 'You do not have permission to reject disciplinary actions.')
        return redirect('staff:disciplinary_actions')
    
    if request.method == 'POST':
        action.delete()
        messages.success(request, f'Disciplinary action for {action.user.get_full_name()} has been rejected and removed.')
        return redirect('staff:disciplinary_actions')
    
    context = {
        'action': action,
    }
    
    return render(request, 'staff/reject_disciplinary_action.html', context)

@specific_role_required('Director of Media & Publicity')
def media_director_dashboard(request):
    pending_campaigns = Campaign.objects.filter(status='PENDING').count()
    pending_media = MediaItem.objects.filter(status='PENDING').count()
    pending_members = User.objects.filter(status='PENDING').count()
    
    context = {
        'pending_campaigns': pending_campaigns,
        'pending_media': pending_media,
        'pending_members': pending_members,
    }
    
    return render(request, 'staff/dashboards/media_director.html', context)

@specific_role_required('Treasurer')
def treasurer_dashboard(request):
    from donations.models import Donation
    unverified_donations = Donation.objects.filter(status='UNVERIFIED').count()
    verified_donations = Donation.objects.filter(status='VERIFIED').count()
    
    context = {
        'unverified_donations': unverified_donations,
        'verified_donations': verified_donations,
    }
    
    return render(request, 'staff/dashboards/treasurer.html', context)

@specific_role_required('Financial Secretary')
def financial_secretary_dashboard(request):
    from donations.models import Donation, FinancialReport
    verified_donations = Donation.objects.filter(status='VERIFIED').count()
    financial_reports_count = FinancialReport.objects.count()
    
    context = {
        'verified_donations': verified_donations,
        'financial_reports_count': financial_reports_count,
    }
    
    return render(request, 'staff/dashboards/financial_secretary.html', context)

@specific_role_required('Organizing Secretary')
def organizing_secretary_dashboard(request):
    from events.models import MeetingMinutes
    upcoming_events = Event.objects.filter(start_date__gte=timezone.now()).count()
    past_events = Event.objects.filter(start_date__lt=timezone.now()).count()
    
    context = {
        'upcoming_events': upcoming_events,
        'past_events': past_events,
    }
    
    return render(request, 'staff/dashboards/organizing_secretary.html', context)

@specific_role_required('General Secretary')
def general_secretary_dashboard(request):
    from events.models import MeetingMinutes
    meeting_minutes_count = MeetingMinutes.objects.all().count()
    published_minutes = MeetingMinutes.objects.filter(is_published=True).count()
    upcoming_meetings = Event.objects.filter(start_date__gte=timezone.now()).count()
    
    context = {
        'meeting_minutes_count': meeting_minutes_count,
        'published_minutes': published_minutes,
        'upcoming_meetings': upcoming_meetings,
    }
    return render(request, 'staff/dashboards/general_secretary.html', context)

@specific_role_required('Zonal Coordinator')
def zonal_coordinator_dashboard(request):
    lgas_in_zone = LGA.objects.filter(zone=request.user.zone).count()
    members_in_zone = User.objects.filter(zone=request.user.zone, status='APPROVED').count()
    
    # Get pending reports submitted to Zonal Coordinator
    pending_reports = Report.objects.filter(
        submitted_to=request.user,
        status='SUBMITTED'
    ).count()
    
    context = {
        'lgas_in_zone': lgas_in_zone,
        'members_in_zone': members_in_zone,
        'pending_reports': pending_reports,
    }
    
    return render(request, 'staff/dashboards/zonal_coordinator.html', context)

@specific_role_required('LGA Coordinator')
def lga_coordinator_dashboard(request):
    wards_in_lga = Ward.objects.filter(lga=request.user.lga).count()
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count()
    
    # Get pending reports submitted to LGA Coordinator
    pending_reports = Report.objects.filter(
        submitted_to=request.user,
        status='SUBMITTED'
    ).count()
    
    context = {
        'wards_in_lga': wards_in_lga,
        'members_in_lga': members_in_lga,
        'pending_reports': pending_reports,
    }
    
    return render(request, 'staff/dashboards/lga_coordinator.html', context)

@specific_role_required('Ward Coordinator')
def ward_coordinator_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count()
    total_meetings = WardMeeting.objects.filter(ward=request.user.ward).count() if request.user.ward else 0
    reports_submitted = Report.objects.filter(submitted_by=request.user).count()
    
    context = {
        'members_in_ward': members_in_ward,
        'total_meetings': total_meetings,
        'reports_submitted': reports_submitted,
    }
    
    return render(request, 'staff/dashboards/ward_coordinator.html', context)

@specific_role_required('Vice President')
def vice_president_dashboard(request):
    """Vice President dashboard with inter-zone reports and disciplinary review"""
    from leadership.models import Zone
    
    # Get all zones with statistics
    zones = Zone.objects.all()
    zone_stats = []
    
    for zone in zones:
        total_members = User.objects.filter(zone=zone, status='APPROVED').count()
        leaders = User.objects.filter(zone=zone, status='APPROVED').exclude(role='GENERAL').count()
        lgas = zone.lgas.count()
        
        zone_stats.append({
            'zone': zone,
            'total_members': total_members,
            'leaders': leaders,
            'lgas': lgas,
        })
    
    # Get disciplinary actions for review
    recent_disciplinary_actions = DisciplinaryAction.objects.filter(
        is_approved=True
    ).order_by('-created_at')[:10]
    
    # Overall statistics
    total_members = User.objects.filter(status='APPROVED').count()
    total_leaders = User.objects.filter(status='APPROVED').exclude(role='GENERAL').count()
    pending_members = User.objects.filter(status='PENDING').count()
    
    context = {
        'zone_stats': zone_stats,
        'recent_disciplinary_actions': recent_disciplinary_actions,
        'total_members': total_members,
        'total_leaders': total_leaders,
        'pending_members': pending_members,
    }
    return render(request, 'staff/dashboards/vice_president.html', context)

@specific_role_required('Assistant General Secretary')
def assistant_general_secretary_dashboard(request):
    from core.models import FAQ
    
    # FAQ Statistics
    total_faqs = FAQ.objects.count()
    active_faqs = FAQ.objects.filter(is_active=True).count()
    inactive_faqs = FAQ.objects.filter(is_active=False).count()
    recent_faqs = FAQ.objects.all().order_by('-created_at')[:5]
    
    context = {
        'total_faqs': total_faqs,
        'active_faqs': active_faqs,
        'inactive_faqs': inactive_faqs,
        'recent_faqs': recent_faqs,
    }
    return render(request, 'staff/dashboards/assistant_general_secretary.html', context)

@specific_role_required('State Supervisor')
def state_supervisor_dashboard(request):
    total_zones = Zone.objects.count()
    total_lgas = LGA.objects.count()
    
    # Get pending reports submitted to State Supervisor
    pending_reports = Report.objects.filter(
        submitted_to=request.user,
        status='SUBMITTED'
    ).count()
    
    context = {
        'total_zones': total_zones,
        'total_lgas': total_lgas,
        'pending_reports': pending_reports,
    }
    
    return render(request, 'staff/dashboards/state_supervisor.html', context)

@specific_role_required('Legal & Ethics Adviser')
def legal_ethics_adviser_dashboard(request):
    disciplinary_actions = DisciplinaryAction.objects.all().count()
    pending_actions = DisciplinaryAction.objects.filter(is_approved=False).count()
    
    context = {
        'disciplinary_actions': disciplinary_actions,
        'pending_actions': pending_actions,
    }
    
    return render(request, 'staff/dashboards/legal_ethics_adviser.html', context)

@specific_role_required('Director of Mobilization')
def director_of_mobilization_dashboard(request):
    total_members = User.objects.filter(status='APPROVED').count()
    total_zones = Zone.objects.count()
    
    context = {
        'total_members': total_members,
        'total_zones': total_zones,
    }
    
    return render(request, 'staff/dashboards/director_of_mobilization.html', context)

@specific_role_required('Assistant Director of Mobilization')
def assistant_director_of_mobilization_dashboard(request):
    total_members = User.objects.filter(status='APPROVED').count()
    
    context = {
        'total_members': total_members,
    }
    
    return render(request, 'staff/dashboards/assistant_director_of_mobilization.html', context)

@specific_role_required('Assistant Organizing Secretary')
def assistant_organizing_secretary_dashboard(request):
    upcoming_events = Event.objects.filter(start_date__gte=timezone.now()).count()
    
    context = {
        'upcoming_events': upcoming_events,
    }
    
    return render(request, 'staff/dashboards/assistant_organizing_secretary.html', context)

@specific_role_required('Auditor General')
def auditor_general_dashboard(request):
    from donations.models import FinancialReport, AuditReport
    
    financial_reports = FinancialReport.objects.all()
    audit_reports = AuditReport.objects.filter(submitted_by=request.user)
    
    total_financial_reports = financial_reports.count()
    total_audit_reports = audit_reports.count()
    
    # Audit report status counts
    draft_audits = audit_reports.filter(status='DRAFT').count()
    submitted_audits = audit_reports.filter(status='SUBMITTED').count()
    reviewed_audits = audit_reports.filter(status='REVIEWED').count()
    
    context = {
        'total_financial_reports': total_financial_reports,
        'total_audit_reports': total_audit_reports,
        'financial_reports': financial_reports[:5],  # Latest 5 financial reports
        'audit_reports': audit_reports[:10],  # Latest 10 audit reports
        'draft_audits': draft_audits,
        'submitted_audits': submitted_audits,
        'reviewed_audits': reviewed_audits,
    }
    
    return render(request, 'staff/dashboards/auditor_general.html', context)

@specific_role_required('Welfare Officer')
def welfare_officer_dashboard(request):
    from .models import WelfareProgram
    
    total_members = User.objects.filter(status='APPROVED').count()
    
    # Get welfare programs based on user's jurisdiction
    if request.user.role == 'STATE':
        welfare_programs = WelfareProgram.objects.all()
    elif request.user.role == 'ZONAL' and request.user.zone:
        welfare_programs = WelfareProgram.objects.filter(zone=request.user.zone) | WelfareProgram.objects.filter(zone__isnull=True, lga__isnull=True)
    elif request.user.role == 'LGA' and request.user.lga:
        welfare_programs = WelfareProgram.objects.filter(lga=request.user.lga) | WelfareProgram.objects.filter(lga__isnull=True, zone=request.user.lga.zone)
    else:
        welfare_programs = WelfareProgram.objects.none()
    
    # Program statistics
    ongoing_programs = welfare_programs.filter(status='ONGOING').count()
    planned_programs = welfare_programs.filter(status='PLANNED').count()
    completed_programs = welfare_programs.filter(status='COMPLETED').count()
    total_beneficiaries = sum([p.get_beneficiary_count() for p in welfare_programs])
    
    context = {
        'total_members': total_members,
        'welfare_programs': welfare_programs[:10],  # Latest 10 programs
        'ongoing_programs': ongoing_programs,
        'planned_programs': planned_programs,
        'completed_programs': completed_programs,
        'total_beneficiaries': total_beneficiaries,
    }
    
    return render(request, 'staff/dashboards/welfare_officer.html', context)

@specific_role_required('Youth Development & Empowerment Officer')
def youth_empowerment_officer_dashboard(request):
    from .models import YouthProgram
    
    total_members = User.objects.filter(status='APPROVED').count()
    
    # Get youth programs based on user's jurisdiction
    if request.user.role == 'STATE':
        youth_programs = YouthProgram.objects.all()
    elif request.user.role == 'ZONAL' and request.user.zone:
        youth_programs = YouthProgram.objects.filter(zone=request.user.zone) | YouthProgram.objects.filter(zone__isnull=True, lga__isnull=True)
    elif request.user.role == 'LGA' and request.user.lga:
        youth_programs = YouthProgram.objects.filter(lga=request.user.lga) | YouthProgram.objects.filter(lga__isnull=True, zone=request.user.lga.zone)
    else:
        youth_programs = YouthProgram.objects.none()
    
    # Program statistics
    ongoing_programs = youth_programs.filter(status='ONGOING').count()
    planned_programs = youth_programs.filter(status='PLANNED').count()
    completed_programs = youth_programs.filter(status='COMPLETED').count()
    total_participants = sum([p.get_participant_count() for p in youth_programs])
    
    context = {
        'total_members': total_members,
        'youth_programs': youth_programs[:10],  # Latest 10 programs
        'ongoing_programs': ongoing_programs,
        'planned_programs': planned_programs,
        'completed_programs': completed_programs,
        'total_participants': total_participants,
    }
    
    return render(request, 'staff/dashboards/youth_empowerment_officer.html', context)

@specific_role_required('Women Leader')
def women_leader_dashboard(request):
    # Filter only female members
    if request.user.role == 'STATE':
        female_members = User.objects.filter(status='APPROVED', gender='F')
    elif request.user.role == 'ZONAL':
        female_members = User.objects.filter(status='APPROVED', gender='F', zone=request.user.zone)
    elif request.user.role == 'LGA':
        female_members = User.objects.filter(status='APPROVED', gender='F', lga=request.user.lga)
    else:
        female_members = User.objects.none()
    
    total_members = female_members.count()
    
    # Get role-based statistics for female members
    state_female_count = female_members.filter(role='STATE').count()
    zonal_female_count = female_members.filter(role='ZONAL').count()
    lga_female_count = female_members.filter(role='LGA').count()
    ward_female_count = female_members.filter(role='WARD').count()
    general_female_count = female_members.filter(role='GENERAL').count()
    
    context = {
        'total_members': total_members,
        'female_members': female_members[:20],  # Show first 20
        'state_female_count': state_female_count,
        'zonal_female_count': zonal_female_count,
        'lga_female_count': lga_female_count,
        'ward_female_count': ward_female_count,
        'general_female_count': general_female_count,
    }
    
    return render(request, 'staff/dashboards/women_leader.html', context)

@specific_role_required('Assistant Women Leader')
def assistant_women_leader_dashboard(request):
    # Filter only female members
    if request.user.role == 'STATE':
        female_members = User.objects.filter(status='APPROVED', gender='F')
    elif request.user.role == 'ZONAL':
        female_members = User.objects.filter(status='APPROVED', gender='F', zone=request.user.zone)
    elif request.user.role == 'LGA':
        female_members = User.objects.filter(status='APPROVED', gender='F', lga=request.user.lga)
    else:
        female_members = User.objects.none()
    
    total_members = female_members.count()
    
    context = {
        'total_members': total_members,
        'female_members': female_members[:20],  # Show first 20
    }
    
    return render(request, 'staff/dashboards/assistant_women_leader.html', context)

@specific_role_required('Assistant Director of Media & Publicity')
def assistant_media_director_dashboard(request):
    pending_campaigns = Campaign.objects.filter(status='PENDING').count()
    pending_media = MediaItem.objects.filter(status='PENDING').count()
    
    context = {
        'pending_campaigns': pending_campaigns,
        'pending_media': pending_media,
    }
    
    return render(request, 'staff/dashboards/assistant_media_director.html', context)

@specific_role_required('Public Relations & Community Engagement Officer')
def pr_officer_dashboard(request):
    published_campaigns = Campaign.objects.filter(status='PUBLISHED').count()
    total_outreach = CommunityOutreach.objects.count()
    completed_outreach = CommunityOutreach.objects.filter(status='COMPLETED').count()
    
    context = {
        'published_campaigns': published_campaigns,
        'total_outreach': total_outreach,
        'completed_outreach': completed_outreach,
    }
    
    return render(request, 'staff/dashboards/pr_officer.html', context)

@specific_role_required('Zonal Secretary')
def zonal_secretary_dashboard(request):
    lgas_in_zone = LGA.objects.filter(zone=request.user.zone).count() if request.user.zone else 0
    members_in_zone = User.objects.filter(zone=request.user.zone, status='APPROVED').count() if request.user.zone else 0
    
    context = {
        'lgas_in_zone': lgas_in_zone,
        'members_in_zone': members_in_zone,
    }
    
    return render(request, 'staff/dashboards/zonal_secretary.html', context)

@specific_role_required('Zonal Publicity Officer')
def zonal_publicity_officer_dashboard(request):
    members_in_zone = User.objects.filter(zone=request.user.zone, status='APPROVED').count() if request.user.zone else 0
    
    context = {
        'members_in_zone': members_in_zone,
    }
    
    return render(request, 'staff/dashboards/zonal_publicity_officer.html', context)

@specific_role_required('Secretary')
def lga_secretary_dashboard(request):
    wards_in_lga = Ward.objects.filter(lga=request.user.lga).count() if request.user.lga else 0
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'wards_in_lga': wards_in_lga,
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_secretary.html', context)

@specific_role_required('Organizing Secretary')
def lga_organizing_secretary_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_organizing_secretary.html', context)

@specific_role_required('Treasurer')
def lga_treasurer_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_treasurer.html', context)

@specific_role_required('Publicity Officer')
def lga_publicity_officer_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_publicity_officer.html', context)

@specific_role_required('LGA Supervisor')
def lga_supervisor_dashboard(request):
    wards_in_lga = Ward.objects.filter(lga=request.user.lga).count() if request.user.lga else 0
    
    context = {
        'wards_in_lga': wards_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_supervisor.html', context)

@specific_role_required('Women Leader')
def lga_women_leader_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_women_leader.html', context)

@specific_role_required('Welfare Officer')
def lga_welfare_officer_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_welfare_officer.html', context)

@specific_role_required('Director of Contact and Mobilization')
def lga_contact_mobilization_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_contact_mobilization.html', context)

@specific_role_required('LGA Adviser')
def lga_adviser_dashboard(request):
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count() if request.user.lga else 0
    
    context = {
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_adviser.html', context)

@specific_role_required('Secretary')
def ward_secretary_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    total_meetings = WardMeeting.objects.filter(ward=request.user.ward).count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
        'total_meetings': total_meetings,
    }
    
    return render(request, 'staff/dashboards/ward_secretary.html', context)

@specific_role_required('Organizing Secretary')
def ward_organizing_secretary_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_organizing_secretary.html', context)

@specific_role_required('Treasurer')
def ward_treasurer_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_treasurer.html', context)

@specific_role_required('Publicity Officer')
def ward_publicity_officer_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_publicity_officer.html', context)

@specific_role_required('Financial Secretary')
def ward_financial_secretary_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_financial_secretary.html', context)

@specific_role_required('Ward Supervisor')
def ward_supervisor_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_supervisor.html', context)

@specific_role_required('Ward Adviser')
def ward_adviser_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count() if request.user.ward else 0
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_adviser.html', context)


@specific_role_required('President')
def edit_member_role(request, user_id):
    from .forms import EditMemberRoleForm
    
    member = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        form = EditMemberRoleForm(request.POST, instance=member)
        if form.is_valid():
            updated_member = form.save()
            messages.success(request, f'Successfully updated {updated_member.get_full_name()}\'s role.')
            return redirect('staff:manage_staff')
    else:
        form = EditMemberRoleForm(instance=member)
    
    context = {
        'form': form,
        'member': member,
    }
    return render(request, 'staff/edit_member_role.html', context)


@specific_role_required('President')
def promote_member(request, user_id):
    from .forms import PromoteMemberForm
    
    member = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        form = PromoteMemberForm(request.POST, user=member)
        if form.is_valid():
            new_role_def = form.cleaned_data['new_role_definition']
            zone = form.cleaned_data.get('zone')
            lga = form.cleaned_data.get('lga')
            ward = form.cleaned_data.get('ward')
            
            member.role_definition = new_role_def
            member.role = new_role_def.tier
            member.zone = zone
            member.lga = lga
            member.ward = ward
            member.save()
            
            messages.success(request, f'Successfully promoted {member.get_full_name()} to {new_role_def.title}.')
            return redirect('staff:manage_staff')
    else:
        form = PromoteMemberForm(user=member)
    
    context = {
        'form': form,
        'member': member,
    }
    return render(request, 'staff/promote_member.html', context)


@specific_role_required('President')
def demote_member(request, user_id):
    from .forms import DemoteMemberForm
    
    member = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        form = DemoteMemberForm(request.POST, user=member)
        if form.is_valid():
            new_role = form.cleaned_data['new_role']
            
            if new_role == 'GENERAL':
                member.role = 'GENERAL'
                member.role_definition = None
                member.save()
                messages.success(request, f'{member.get_full_name()} has been demoted to General Member.')
            else:
                new_role_def = form.cleaned_data.get('new_role_definition')
                zone = form.cleaned_data.get('zone')
                lga = form.cleaned_data.get('lga')
                ward = form.cleaned_data.get('ward')
                
                if new_role_def:
                    member.role_definition = new_role_def
                    member.role = new_role_def.tier
                    member.zone = zone
                    member.lga = lga
                    member.ward = ward
                    member.save()
                    messages.success(request, f'Successfully demoted {member.get_full_name()} to {new_role_def.title}.')
                else:
                    messages.error(request, 'Please select a specific position.')
                    return redirect('staff:demote_member', user_id=user_id)
            
            return redirect('staff:manage_staff')
    else:
        form = DemoteMemberForm(user=member)
    
    context = {
        'form': form,
        'member': member,
    }
    return render(request, 'staff/demote_member.html', context)


@specific_role_required('President')
def dismiss_member(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        member.status = 'DISMISSED'
        member.save()
        
        messages.success(request, f'{member.get_full_name()} has been dismissed from the organization.')
        return redirect('staff:manage_staff')
    
    context = {
        'member': member,
    }
    return render(request, 'staff/dismiss_member.html', context)


@specific_role_required('President')
def suspend_member(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        member.status = 'SUSPENDED'
        member.save()
        
        messages.success(request, f'{member.get_full_name()} has been suspended.')
        return redirect('staff:manage_staff')
    
    context = {
        'member': member,
    }
    return render(request, 'staff/suspend_member.html', context)


@specific_role_required('President')
def reinstate_member(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        member.status = 'APPROVED'
        member.date_approved = timezone.now()
        member.approved_by = request.user
        member.save()
        
        messages.success(request, f'{member.get_full_name()} has been reinstated.')
        return redirect('staff:manage_staff')
    
    context = {
        'member': member,
    }
    return render(request, 'staff/reinstate_member.html', context)


@specific_role_required('President')
def swap_positions(request):
    from .forms import SwapPositionsForm
    
    if request.method == 'POST':
        form = SwapPositionsForm(request.POST)
        if form.is_valid():
            member1 = form.cleaned_data['member1']
            member2 = form.cleaned_data['member2']
            
            temp_role_def = member1.role_definition
            temp_role = member1.role
            temp_zone = member1.zone
            temp_lga = member1.lga
            temp_ward = member1.ward
            
            member1.role_definition = member2.role_definition
            member1.role = member2.role
            member1.zone = member2.zone
            member1.lga = member2.lga
            member1.ward = member2.ward
            member1.save()
            
            member2.role_definition = temp_role_def
            member2.role = temp_role
            member2.zone = temp_zone
            member2.lga = temp_lga
            member2.ward = temp_ward
            member2.save()
            
            messages.success(request, f'Successfully swapped positions between {member1.get_full_name()} and {member2.get_full_name()}.')
            return redirect('staff:manage_staff')
    else:
        form = SwapPositionsForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/swap_positions.html', context)


@specific_role_required('Director of Mobilization', 'Assistant Director of Mobilization')
def member_mobilization(request):
    """Member filtering and contact list generation for mobilization"""
    import csv
    from django.http import HttpResponse
    
    zone_filter = request.GET.get('zone', '')
    lga_filter = request.GET.get('lga', '')
    ward_filter = request.GET.get('ward', '')
    role_filter = request.GET.get('role', '')
    gender_filter = request.GET.get('gender', '')
    status_filter = request.GET.get('status', 'APPROVED')
    search = request.GET.get('search', '')
    export = request.GET.get('export', '')
    
    members = User.objects.all().order_by('last_name', 'first_name')
    
    if search:
        members = members.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search) |
            Q(phone__icontains=search)
        )
    
    if zone_filter:
        members = members.filter(zone_id=zone_filter)
    
    if lga_filter:
        members = members.filter(lga_id=lga_filter)
    
    if ward_filter:
        members = members.filter(ward_id=ward_filter)
    
    if role_filter:
        members = members.filter(role=role_filter)
    
    if gender_filter:
        members = members.filter(gender=gender_filter)
    
    if status_filter:
        members = members.filter(status=status_filter)
    
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="kpn_members_contact_list.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Name', 'Phone', 'Email', 'Gender', 'Role', 'Location', 'Status'])
        
        for member in members:
            location = member.get_jurisdiction()
            writer.writerow([
                member.get_full_name(),
                member.phone,
                member.email,
                member.get_gender_display() if member.gender else '',
                member.get_role_display(),
                location,
                member.get_status_display()
            ])
        
        return response
    
    zones = Zone.objects.all()
    lgas = LGA.objects.all()
    wards = Ward.objects.all()
    
    context = {
        'members': members,
        'total_count': members.count(),
        'zones': zones,
        'lgas': lgas,
        'wards': wards,
        'zone_filter': zone_filter,
        'lga_filter': lga_filter,
        'ward_filter': ward_filter,
        'role_filter': role_filter,
        'gender_filter': gender_filter,
        'status_filter': status_filter,
        'search': search,
    }
    return render(request, 'staff/member_mobilization.html', context)


@specific_role_required('Women Leader', 'Assistant Women Leader')
def women_members(request):
    """Female members dashboard for Women Leader"""
    search = request.GET.get('search', '')
    zone_filter = request.GET.get('zone', '')
    lga_filter = request.GET.get('lga', '')
    
    female_members = User.objects.filter(status='APPROVED', gender='F').order_by('last_name', 'first_name')
    
    if search:
        female_members = female_members.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search)
        )
    
    if zone_filter:
        female_members = female_members.filter(zone_id=zone_filter)
    
    if lga_filter:
        female_members = female_members.filter(lga_id=lga_filter)
    
    zones = Zone.objects.all()
    lgas = LGA.objects.all()
    
    context = {
        'female_members': female_members,
        'total_count': female_members.count(),
        'zones': zones,
        'lgas': lgas,
        'zone_filter': zone_filter,
        'lga_filter': lga_filter,
        'search': search,
    }
    return render(request, 'staff/women_members.html', context)


@specific_role_required('Director of Mobilization', 'Assistant Director of Mobilization')
def member_mobilization(request):
    """Member filtering and contact list generation for mobilization"""
    import csv
    from django.http import HttpResponse
    
    form = MemberMobilizationFilterForm(request.GET or None)
    # Start with all members - don't filter by status initially
    members = User.objects.all().order_by('last_name', 'first_name')
    
    # Apply filters
    if form.is_valid():
        if form.cleaned_data.get('zone'):
            members = members.filter(zone=form.cleaned_data['zone'])
        
        if form.cleaned_data.get('lga'):
            members = members.filter(lga=form.cleaned_data['lga'])
        
        if form.cleaned_data.get('ward'):
            members = members.filter(ward=form.cleaned_data['ward'])
        
        if form.cleaned_data.get('role'):
            members = members.filter(role=form.cleaned_data['role'])
        
        if form.cleaned_data.get('gender'):
            members = members.filter(gender=form.cleaned_data['gender'])
        
        if form.cleaned_data.get('status'):
            members = members.filter(status=form.cleaned_data['status'])
        else:
            # If no status filter selected, default to APPROVED members only
            members = members.filter(status='APPROVED')
    
    # Handle CSV export
    if 'export' in request.GET:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="kpn_contact_list.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Name', 'Phone', 'Role', 'Zone', 'LGA', 'Ward', 'Gender', 'Status'])
        
        for member in members:
            writer.writerow([
                member.get_full_name(),
                member.phone,
                member.get_role_display(),
                member.zone.name if member.zone else '',
                member.lga.name if member.lga else '',
                member.ward.name if member.ward else '',
                member.get_gender_display() if member.gender else '',
                member.get_status_display()
            ])
        
        return response
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(members, 50)  # Show 50 members per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'members': page_obj,
        'total_count': members.count(),
    }
    
    return render(request, 'staff/member_mobilization.html', context)


# Women's Program Management Views

@specific_role_required('Women Leader', 'Assistant Women Leader')
def womens_programs_list(request):
    """List all women's programs"""
    user = request.user
    
    # Filter programs based on user's jurisdiction
    if user.role == 'STATE':
        programs = WomensProgram.objects.all()
    elif user.role == 'ZONAL':
        programs = WomensProgram.objects.filter(
            models.Q(zone=user.zone) | models.Q(zone__isnull=True, lga__isnull=True)
        )
    elif user.role == 'LGA':
        programs = WomensProgram.objects.filter(
            models.Q(lga=user.lga) | models.Q(zone=user.zone, lga__isnull=True) | models.Q(zone__isnull=True, lga__isnull=True)
        )
    else:
        programs = WomensProgram.objects.none()
    
    programs = programs.order_by('-created_at')
    
    context = {
        'programs': programs,
    }
    return render(request, 'staff/womens_programs/list.html', context)


@specific_role_required('Women Leader', 'Assistant Women Leader')
def create_womens_program(request):
    """Create a new women's program"""
    from .forms import WomensProgramForm
    
    if request.method == 'POST':
        form = WomensProgramForm(request.POST)
        if form.is_valid():
            program = form.save(commit=False)
            program.created_by = request.user
            
            # Set jurisdiction based on user's role
            if request.user.role == 'ZONAL':
                program.zone = request.user.zone
            elif request.user.role == 'LGA':
                program.lga = request.user.lga
                program.zone = request.user.zone
            
            program.save()
            messages.success(request, f'Women\'s program "{program.title}" created successfully!')
            return redirect('staff:womens_programs_list')
    else:
        form = WomensProgramForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/womens_programs/form.html', context)


@specific_role_required('Women Leader', 'Assistant Women Leader')
def edit_womens_program(request, program_id):
    """Edit an existing women's program"""
    from .forms import WomensProgramForm
    
    program = get_object_or_404(WomensProgram, pk=program_id)
    
    if request.method == 'POST':
        form = WomensProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, f'Women\'s program "{program.title}" updated successfully!')
            return redirect('staff:womens_programs_list')
    else:
        form = WomensProgramForm(instance=program)
    
    context = {
        'form': form,
        'program': program,
    }
    return render(request, 'staff/womens_programs/form.html', context)


@specific_role_required('Women Leader', 'Assistant Women Leader')
def delete_womens_program(request, program_id):
    """Delete a women's program"""
    program = get_object_or_404(WomensProgram, pk=program_id)
    
    if request.method == 'POST':
        program_title = program.title
        program.delete()
        messages.success(request, f'Women\'s program "{program_title}" deleted successfully!')
        return redirect('staff:womens_programs_list')
    
    context = {
        'program': program,
    }
    return render(request, 'staff/womens_programs/delete.html', context)


@specific_role_required('Women Leader', 'Assistant Women Leader')
def manage_program_participants(request, program_id):
    """Manage participants for a women's program"""
    
    # Filter programs by jurisdiction to prevent IDOR
    if request.user.role == 'STATE':
        programs = WomensProgram.objects.all()
        female_members = User.objects.filter(status='APPROVED', gender='F')
    elif request.user.role == 'ZONAL':
        programs = WomensProgram.objects.filter(
            models.Q(zone=request.user.zone) | models.Q(zone__isnull=True, lga__isnull=True)
        )
        female_members = User.objects.filter(status='APPROVED', gender='F', zone=request.user.zone)
    elif request.user.role == 'LGA':
        programs = WomensProgram.objects.filter(
            models.Q(lga=request.user.lga) | models.Q(zone=request.user.zone, lga__isnull=True) | models.Q(zone__isnull=True, lga__isnull=True)
        )
        female_members = User.objects.filter(status='APPROVED', gender='F', lga=request.user.lga)
    else:
        programs = WomensProgram.objects.none()
        female_members = User.objects.none()
    
    program = get_object_or_404(programs, pk=program_id)
    
    if request.method == 'POST':
        selected_participants = request.POST.getlist('participants')
        # Validate that all selected participants are within jurisdiction
        valid_member_ids = set(female_members.values_list('id', flat=True))
        validated_participants = [p_id for p_id in selected_participants if int(p_id) in valid_member_ids]
        
        program.participants.set(validated_participants)
        messages.success(request, f'Participants updated for "{program.title}"!')
        return redirect('staff:womens_programs_list')
    
    current_participants = program.participants.values_list('id', flat=True)
    
    context = {
        'program': program,
        'female_members': female_members.order_by('last_name', 'first_name'),
        'current_participants': list(current_participants),
    }
    return render(request, 'staff/womens_programs/manage_participants.html', context)


# FAQ Management Views

@specific_role_required('Assistant General Secretary')
def faq_list(request):
    """List all FAQs for management"""
    from core.models import FAQ
    
    faqs = FAQ.objects.all().order_by('order', '-created_at')
    
    context = {
        'faqs': faqs,
    }
    return render(request, 'staff/faq/list.html', context)


@specific_role_required('Assistant General Secretary')
def create_faq(request):
    """Create a new FAQ"""
    from .forms import FAQForm
    
    if request.method == 'POST':
        form = FAQForm(request.POST)
        if form.is_valid():
            faq = form.save()
            messages.success(request, 'FAQ created successfully!')
            return redirect('staff:faq_list')
    else:
        form = FAQForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/faq/form.html', context)


@specific_role_required('Assistant General Secretary')
def edit_faq(request, faq_id):
    """Edit an existing FAQ"""
    from core.models import FAQ
    from .forms import FAQForm
    
    faq = get_object_or_404(FAQ, pk=faq_id)
    
    if request.method == 'POST':
        form = FAQForm(request.POST, instance=faq)
        if form.is_valid():
            form.save()
            messages.success(request, 'FAQ updated successfully!')
            return redirect('staff:faq_list')
    else:
        form = FAQForm(instance=faq)
    
    context = {
        'form': form,
        'faq': faq,
    }
    return render(request, 'staff/faq/form.html', context)


@specific_role_required('Assistant General Secretary')
def delete_faq(request, faq_id):
    """Delete an FAQ"""
    from core.models import FAQ
    
    faq = get_object_or_404(FAQ, pk=faq_id)
    
    if request.method == 'POST':
        faq.delete()
        messages.success(request, 'FAQ deleted successfully!')
        return redirect('staff:faq_list')
    
    context = {
        'faq': faq,
    }
    return render(request, 'staff/faq/delete.html', context)


@specific_role_required('Assistant General Secretary')
def toggle_faq_status(request, faq_id):
    """Toggle FAQ active/inactive status"""
    from core.models import FAQ
    
    faq = get_object_or_404(FAQ, pk=faq_id)
    faq.is_active = not faq.is_active
    faq.save()
    
    status = "activated" if faq.is_active else "deactivated"
    messages.success(request, f'FAQ "{faq.question[:50]}..." {status} successfully!')
    return redirect('staff:faq_list')


# Legal Review Views

@specific_role_required('Legal & Ethics Adviser')
def legal_review_queue(request):
    """View pending disciplinary actions for legal review"""
    
    # Get disciplinary actions that need legal review (not warnings, not already legally reviewed)
    pending_actions = DisciplinaryAction.objects.filter(
        legal_reviewed_by__isnull=True,
        is_approved=False
    ).exclude(action_type='WARNING').order_by('-created_at')
    
    # Get actions already reviewed by this legal adviser
    reviewed_actions = DisciplinaryAction.objects.filter(
        legal_reviewed_by=request.user
    ).order_by('-legal_reviewed_at')[:20]
    
    context = {
        'pending_actions': pending_actions,
        'reviewed_actions': reviewed_actions,
    }
    return render(request, 'staff/legal_review/queue.html', context)


@specific_role_required('Legal & Ethics Adviser')
def legal_review_action(request, action_id):
    """Legal review of a disciplinary action"""
    from .forms import LegalReviewForm
    
    action = get_object_or_404(DisciplinaryAction, pk=action_id)
    
    if action.legal_reviewed_by:
        messages.warning(request, 'This action has already been legally reviewed.')
        return redirect('staff:legal_review_queue')
    
    if request.method == 'POST':
        form = LegalReviewForm(request.POST)
        if form.is_valid():
            action.legal_reviewed_by = request.user
            action.legal_opinion = form.cleaned_data['legal_opinion']
            action.legal_approved = form.cleaned_data.get('legal_approved', False)
            action.legal_reviewed_at = timezone.now()
            action.save()
            
            status = "approved" if action.legal_approved else "rejected"
            messages.success(request, f'Legal review completed. Action {status}.')
            return redirect('staff:legal_review_queue')
    else:
        form = LegalReviewForm()
    
    context = {
        'form': form,
        'action': action,
    }
    return render(request, 'staff/legal_review/review_form.html', context)


# Youth Program Management Views

@specific_role_required('Youth Development & Empowerment Officer')
def youth_programs_list(request):
    """List all youth programs"""
    from .models import YouthProgram
    
    user = request.user
    
    # Filter programs based on user's jurisdiction
    if user.role == 'STATE':
        programs = YouthProgram.objects.all()
    elif user.role == 'ZONAL':
        programs = YouthProgram.objects.filter(
            models.Q(zone=user.zone) | models.Q(zone__isnull=True, lga__isnull=True)
        )
    elif user.role == 'LGA':
        programs = YouthProgram.objects.filter(
            models.Q(lga=user.lga) | models.Q(zone=user.zone, lga__isnull=True) | models.Q(zone__isnull=True, lga__isnull=True)
        )
    else:
        programs = YouthProgram.objects.none()
    
    programs = programs.order_by('-created_at')
    
    context = {
        'programs': programs,
    }
    return render(request, 'staff/youth_programs/list.html', context)


@specific_role_required('Youth Development & Empowerment Officer')
def create_youth_program(request):
    """Create a new youth program"""
    from .forms import YouthProgramForm
    from .models import YouthProgram
    
    if request.method == 'POST':
        form = YouthProgramForm(request.POST)
        if form.is_valid():
            program = form.save(commit=False)
            program.created_by = request.user
            program.save()
            messages.success(request, 'Youth program created successfully!')
            return redirect('staff:youth_programs_list')
    else:
        form = YouthProgramForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/youth_programs/form.html', context)


@specific_role_required('Youth Development & Empowerment Officer')
def edit_youth_program(request, program_id):
    """Edit an existing youth program"""
    from .forms import YouthProgramForm
    from .models import YouthProgram
    
    program = get_object_or_404(YouthProgram, pk=program_id)
    
    if request.method == 'POST':
        form = YouthProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, 'Youth program updated successfully!')
            return redirect('staff:youth_programs_list')
    else:
        form = YouthProgramForm(instance=program)
    
    context = {
        'form': form,
        'program': program,
    }
    return render(request, 'staff/youth_programs/form.html', context)


@specific_role_required('Youth Development & Empowerment Officer')
def delete_youth_program(request, program_id):
    """Delete a youth program"""
    from .models import YouthProgram
    
    program = get_object_or_404(YouthProgram, pk=program_id)
    
    if request.method == 'POST':
        program.delete()
        messages.success(request, 'Youth program deleted successfully!')
        return redirect('staff:youth_programs_list')
    
    context = {
        'program': program,
    }
    return render(request, 'staff/youth_programs/delete.html', context)


@specific_role_required('Youth Development & Empowerment Officer')
def manage_youth_participants(request, program_id):
    """Manage participants for a youth program"""
    from .models import YouthProgram
    
    # Filter programs by jurisdiction to prevent IDOR
    if request.user.role == 'STATE':
        programs = YouthProgram.objects.all()
        members = User.objects.filter(status='APPROVED')
    elif request.user.role == 'ZONAL':
        programs = YouthProgram.objects.filter(
            models.Q(zone=request.user.zone) | models.Q(zone__isnull=True, lga__isnull=True)
        )
        members = User.objects.filter(status='APPROVED', zone=request.user.zone)
    elif request.user.role == 'LGA':
        programs = YouthProgram.objects.filter(
            models.Q(lga=request.user.lga) | models.Q(zone=request.user.zone, lga__isnull=True) | models.Q(zone__isnull=True, lga__isnull=True)
        )
        members = User.objects.filter(status='APPROVED', lga=request.user.lga)
    else:
        programs = YouthProgram.objects.none()
        members = User.objects.none()
    
    program = get_object_or_404(programs, pk=program_id)
    
    if request.method == 'POST':
        selected_participants = request.POST.getlist('participants')
        # Validate that all selected participants are within jurisdiction
        valid_member_ids = set(members.values_list('id', flat=True))
        validated_participants = [p_id for p_id in selected_participants if int(p_id) in valid_member_ids]
        
        program.participants.set(validated_participants)
        messages.success(request, f'Participants updated for "{program.title}"!')
        return redirect('staff:youth_programs_list')
    
    current_participants = program.participants.values_list('id', flat=True)
    
    context = {
        'program': program,
        'members': members.order_by('last_name', 'first_name'),
        'current_participants': list(current_participants),
    }
    return render(request, 'staff/youth_programs/manage_participants.html', context)


# Welfare Program Management Views

@specific_role_required('Welfare Officer')
def welfare_programs_list(request):
    """List all welfare programs"""
    from .models import WelfareProgram
    
    user = request.user
    
    # Filter programs based on user's jurisdiction
    if user.role == 'STATE':
        programs = WelfareProgram.objects.all()
    elif user.role == 'ZONAL':
        programs = WelfareProgram.objects.filter(
            models.Q(zone=user.zone) | models.Q(zone__isnull=True, lga__isnull=True)
        )
    elif user.role == 'LGA':
        programs = WelfareProgram.objects.filter(
            models.Q(lga=user.lga) | models.Q(zone=user.zone, lga__isnull=True) | models.Q(zone__isnull=True, lga__isnull=True)
        )
    else:
        programs = WelfareProgram.objects.none()
    
    programs = programs.order_by('-created_at')
    
    context = {
        'programs': programs,
    }
    return render(request, 'staff/welfare_programs/list.html', context)


@specific_role_required('Welfare Officer')
def create_welfare_program(request):
    """Create a new welfare program"""
    from .forms import WelfareProgramForm
    from .models import WelfareProgram
    
    if request.method == 'POST':
        form = WelfareProgramForm(request.POST)
        if form.is_valid():
            program = form.save(commit=False)
            program.created_by = request.user
            program.save()
            messages.success(request, 'Welfare program created successfully!')
            return redirect('staff:welfare_programs_list')
    else:
        form = WelfareProgramForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/welfare_programs/form.html', context)


@specific_role_required('Welfare Officer')
def edit_welfare_program(request, program_id):
    """Edit an existing welfare program"""
    from .forms import WelfareProgramForm
    from .models import WelfareProgram
    
    program = get_object_or_404(WelfareProgram, pk=program_id)
    
    if request.method == 'POST':
        form = WelfareProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, 'Welfare program updated successfully!')
            return redirect('staff:welfare_programs_list')
    else:
        form = WelfareProgramForm(instance=program)
    
    context = {
        'form': form,
        'program': program,
    }
    return render(request, 'staff/welfare_programs/form.html', context)


@specific_role_required('Welfare Officer')
def delete_welfare_program(request, program_id):
    """Delete a welfare program"""
    from .models import WelfareProgram
    
    program = get_object_or_404(WelfareProgram, pk=program_id)
    
    if request.method == 'POST':
        program.delete()
        messages.success(request, 'Welfare program deleted successfully!')
        return redirect('staff:welfare_programs_list')
    
    context = {
        'program': program,
    }
    return render(request, 'staff/welfare_programs/delete.html', context)


@specific_role_required('Welfare Officer')
def manage_welfare_beneficiaries(request, program_id):
    """Manage beneficiaries for a welfare program"""
    from .models import WelfareProgram
    
    # Filter programs by jurisdiction to prevent IDOR
    if request.user.role == 'STATE':
        programs = WelfareProgram.objects.all()
        members = User.objects.filter(status='APPROVED')
    elif request.user.role == 'ZONAL':
        programs = WelfareProgram.objects.filter(
            models.Q(zone=request.user.zone) | models.Q(zone__isnull=True, lga__isnull=True)
        )
        members = User.objects.filter(status='APPROVED', zone=request.user.zone)
    elif request.user.role == 'LGA':
        programs = WelfareProgram.objects.filter(
            models.Q(lga=request.user.lga) | models.Q(zone=request.user.zone, lga__isnull=True) | models.Q(zone__isnull=True, lga__isnull=True)
        )
        members = User.objects.filter(status='APPROVED', lga=request.user.lga)
    else:
        programs = WelfareProgram.objects.none()
        members = User.objects.none()
    
    program = get_object_or_404(programs, pk=program_id)
    
    if request.method == 'POST':
        selected_beneficiaries = request.POST.getlist('beneficiaries')
        # Validate that all selected beneficiaries are within jurisdiction
        valid_member_ids = set(members.values_list('id', flat=True))
        validated_beneficiaries = [b_id for b_id in selected_beneficiaries if int(b_id) in valid_member_ids]
        
        program.beneficiaries.set(validated_beneficiaries)
        messages.success(request, f'Beneficiaries updated for "{program.title}"!')
        return redirect('staff:welfare_programs_list')
    
    current_beneficiaries = program.beneficiaries.values_list('id', flat=True)
    
    context = {
        'program': program,
        'members': members.order_by('last_name', 'first_name'),
        'current_beneficiaries': list(current_beneficiaries),
    }
    return render(request, 'staff/welfare_programs/manage_beneficiaries.html', context)


# Audit Report Management Views

@specific_role_required('Auditor General')
def create_audit_report(request):
    """Create a new audit report"""
    from donations.forms import AuditReportForm
    from donations.models import AuditReport
    
    if request.method == 'POST':
        form = AuditReportForm(request.POST, request.FILES)
        if form.is_valid():
            audit = form.save(commit=False)
            audit.submitted_by = request.user
            # Get President as submitted_to
            president = User.objects.filter(
                role_definition__title='President',
                status='APPROVED'
            ).first()
            audit.submitted_to = president
            audit.save()
            messages.success(request, 'Audit report created successfully!')
            return redirect('staff:auditor_general_dashboard')
    else:
        form = AuditReportForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/audit_reports/form.html', context)


@specific_role_required('Auditor General')
def edit_audit_report(request, report_id):
    """Edit an existing audit report"""
    from donations.forms import AuditReportForm
    from donations.models import AuditReport
    
    audit = get_object_or_404(AuditReport, pk=report_id, submitted_by=request.user)
    
    if audit.status != 'DRAFT':
        messages.warning(request, 'Only draft audit reports can be edited.')
        return redirect('staff:auditor_general_dashboard')
    
    if request.method == 'POST':
        form = AuditReportForm(request.POST, request.FILES, instance=audit)
        if form.is_valid():
            form.save()
            messages.success(request, 'Audit report updated successfully!')
            return redirect('staff:auditor_general_dashboard')
    else:
        form = AuditReportForm(instance=audit)
    
    context = {
        'form': form,
        'audit': audit,
    }
    return render(request, 'staff/audit_reports/form.html', context)


@specific_role_required('Auditor General')
def submit_audit_report(request, report_id):
    """Submit an audit report to the President"""
    from donations.models import AuditReport
    
    audit = get_object_or_404(AuditReport, pk=report_id, submitted_by=request.user)
    
    if audit.status != 'DRAFT':
        messages.warning(request, 'This audit report has already been submitted.')
        return redirect('staff:auditor_general_dashboard')
    
    if request.method == 'POST':
        audit.status = 'SUBMITTED'
        audit.submitted_at = timezone.now()
        audit.save()
        messages.success(request, 'Audit report submitted successfully to the President!')
        return redirect('staff:auditor_general_dashboard')
    
    context = {
        'audit': audit,
    }
    return render(request, 'staff/audit_reports/submit.html', context)


# Vice President Views

@specific_role_required('Vice President')
def vice_president_staff_directory(request):
    """Advanced staff directory with filtering"""
    
    # Get filter parameters
    zone_id = request.GET.get('zone')
    lga_id = request.GET.get('lga')
    role = request.GET.get('role')
    status = request.GET.get('status', 'APPROVED')
    
    # Base queryset
    members = User.objects.filter(status=status).order_by('zone__name', 'lga__name', 'last_name')
    
    # Apply filters
    if zone_id:
        members = members.filter(zone_id=zone_id)
    if lga_id:
        members = members.filter(lga_id=lga_id)
    if role:
        members = members.filter(role=role)
    
    # Get filter options
    from leadership.models import Zone, LGA
    zones = Zone.objects.all()
    lgas = LGA.objects.all()
    if zone_id:
        lgas = lgas.filter(zone_id=zone_id)
    
    context = {
        'members': members[:100],  # Limit to 100 for performance
        'zones': zones,
        'lgas': lgas,
        'selected_zone': zone_id,
        'selected_lga': lga_id,
        'selected_role': role,
        'selected_status': status,
    }
    return render(request, 'staff/vice_president/staff_directory.html', context)


@specific_role_required('Vice President')
def vice_president_disciplinary_review(request):
    """View and review disciplinary actions (read-only with comments)"""
    
    # Get all disciplinary actions
    disciplinary_actions = DisciplinaryAction.objects.all().order_by('-created_at')
    
    # Filter options
    action_type = request.GET.get('action_type')
    if action_type:
        disciplinary_actions = disciplinary_actions.filter(action_type=action_type)
    
    context = {
        'disciplinary_actions': disciplinary_actions[:50],  # Latest 50
        'selected_action_type': action_type,
    }
    return render(request, 'staff/vice_president/disciplinary_review.html', context)


# Community Outreach Management (PR Officer)

@specific_role_required('Public Relations & Community Engagement Officer')
def create_outreach(request):
    """Create a new community outreach activity"""
    if request.method == 'POST':
        form = CommunityOutreachForm(request.POST)
        if form.is_valid():
            outreach = form.save(commit=False)
            outreach.created_by = request.user
            outreach.save()
            messages.success(request, 'Community outreach activity created successfully!')
            return redirect('staff:outreach_list')
    else:
        form = CommunityOutreachForm()
    
    context = {
        'form': form,
    }
    return render(request, 'staff/outreach/create.html', context)


@specific_role_required('Public Relations & Community Engagement Officer')
def outreach_list(request):
    """List all community outreach activities"""
    outreach_activities = CommunityOutreach.objects.all().order_by('-date')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        outreach_activities = outreach_activities.filter(status=status)
    
    # Filter by engagement type
    engagement_type = request.GET.get('engagement_type')
    if engagement_type:
        outreach_activities = outreach_activities.filter(engagement_type=engagement_type)
    
    context = {
        'outreach_activities': outreach_activities,
        'selected_status': status,
        'selected_engagement_type': engagement_type,
    }
    return render(request, 'staff/outreach/list.html', context)


@specific_role_required('Public Relations & Community Engagement Officer')
def edit_outreach(request, pk):
    """Edit an existing community outreach activity"""
    outreach = get_object_or_404(CommunityOutreach, pk=pk)
    
    if request.method == 'POST':
        form = CommunityOutreachForm(request.POST, instance=outreach)
        if form.is_valid():
            form.save()
            messages.success(request, 'Community outreach activity updated successfully!')
            return redirect('staff:outreach_list')
    else:
        form = CommunityOutreachForm(instance=outreach)
    
    context = {
        'form': form,
        'outreach': outreach,
    }
    return render(request, 'staff/outreach/edit.html', context)


@specific_role_required('Public Relations & Community Engagement Officer')
def delete_outreach(request, pk):
    """Delete a community outreach activity"""
    outreach = get_object_or_404(CommunityOutreach, pk=pk)
    
    if request.method == 'POST':
        outreach.delete()
        messages.success(request, 'Community outreach activity deleted successfully!')
        return redirect('staff:outreach_list')
    
    context = {
        'outreach': outreach,
    }
    return render(request, 'staff/outreach/delete.html', context)


# Ward Meeting Management

@specific_role_required('Ward Coordinator', 'Ward Secretary')
def create_ward_meeting(request):
    """Create a new ward meeting"""
    if request.method == 'POST':
        form = WardMeetingForm(request.POST, user=request.user)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.created_by = request.user
            meeting.save()
            messages.success(request, 'Ward meeting created successfully!')
            return redirect('staff:ward_meetings_list')
    else:
        form = WardMeetingForm(user=request.user)
    
    context = {
        'form': form,
    }
    return render(request, 'staff/ward_meetings/create.html', context)


@specific_role_required('Ward Coordinator', 'Ward Secretary', 'Ward Organizing Secretary')
def ward_meetings_list(request):
    """List all ward meetings for the user's ward"""
    if request.user.ward:
        meetings = WardMeeting.objects.filter(ward=request.user.ward).order_by('-date')
    else:
        meetings = WardMeeting.objects.none()
    
    context = {
        'meetings': meetings,
    }
    return render(request, 'staff/ward_meetings/list.html', context)


@specific_role_required('Ward Coordinator', 'Ward Secretary')
def edit_ward_meeting(request, pk):
    """Edit an existing ward meeting"""
    meeting = get_object_or_404(WardMeeting, pk=pk, ward=request.user.ward)
    
    if request.method == 'POST':
        form = WardMeetingForm(request.POST, instance=meeting, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ward meeting updated successfully!')
            return redirect('staff:ward_meetings_list')
    else:
        form = WardMeetingForm(instance=meeting, user=request.user)
    
    context = {
        'form': form,
        'meeting': meeting,
    }
    return render(request, 'staff/ward_meetings/edit.html', context)


@specific_role_required('Ward Coordinator', 'Ward Secretary', 'Ward Organizing Secretary')
def manage_ward_meeting_attendance(request, pk):
    """Manage attendance for a ward meeting"""
    meeting = get_object_or_404(WardMeeting, pk=pk, ward=request.user.ward)
    
    if request.method == 'POST':
        form = WardMeetingAttendanceForm(request.POST, meeting=meeting)
        if form.is_valid():
            count = 0
            for field_name, value in form.cleaned_data.items():
                if field_name.startswith('attendee_') and value:
                    member_id = field_name.split('_')[1]
                    member = User.objects.get(id=member_id)
                    
                    attendance, created = WardMeetingAttendance.objects.get_or_create(
                        meeting=meeting,
                        member=member,
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
            return redirect('staff:ward_meetings_list')
    else:
        form = WardMeetingAttendanceForm(meeting=meeting)
    
    existing_attendances = meeting.attendance_records.filter(present=True).values_list('member_id', flat=True)
    
    context = {
        'meeting': meeting,
        'form': form,
        'existing_attendances': list(existing_attendances),
    }
    return render(request, 'staff/ward_meetings/manage_attendance.html', context)


@specific_role_required('Ward Coordinator', 'Ward Secretary')
def delete_ward_meeting(request, pk):
    """Delete a ward meeting"""
    meeting = get_object_or_404(WardMeeting, pk=pk, ward=request.user.ward)
    
    if request.method == 'POST':
        meeting.delete()
        messages.success(request, 'Ward meeting deleted successfully!')
        return redirect('staff:ward_meetings_list')
    
    context = {
        'meeting': meeting,
    }
    return render(request, 'staff/ward_meetings/delete.html', context)
