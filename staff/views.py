from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from .models import User, DisciplinaryAction
from .decorators import specific_role_required, role_required, approved_leader_required
from .forms import MemberMobilizationFilterForm
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
        
        if request.FILES.get('photo'):
            user.photo = request.FILES['photo']
            user.save()
        
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
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name')
        request.user.last_name = request.POST.get('last_name')
        request.user.email = request.POST.get('email')
        request.user.phone = request.POST.get('phone')
        request.user.bio = request.POST.get('bio', '')
        request.user.gender = request.POST.get('gender', '')
        
        if request.FILES.get('photo'):
            request.user.photo = request.FILES['photo']
        
        request.user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('staff:profile')
    
    return render(request, 'staff/profile.html')

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
                    'title': role.title
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
                    'title': role.title
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
                    'title': role.title
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
                    'title': role.title
                })
    
    return JsonResponse({
        'vacant_roles': vacant_roles
    })

@specific_role_required('President')
def president_dashboard(request):
    pending_approvals = User.objects.filter(status='PENDING').count()
    total_members = User.objects.filter(status='APPROVED').count()
    total_leaders = User.objects.filter(status='APPROVED').exclude(role='GENERAL').count()
    pending_reports = Report.objects.filter(is_reviewed=False).count()
    
    pending_applicants = User.objects.filter(status='PENDING').order_by('-created_at')[:10]
    
    context = {
        'pending_approvals': pending_approvals,
        'total_members': total_members,
        'total_leaders': total_leaders,
        'pending_reports': pending_reports,
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
    if request.user.role == 'STATE':
        reports = Report.objects.all().order_by('-created_at')
    elif request.user.role == 'ZONAL':
        reports = Report.objects.filter(
            Q(submitted_by__zone=request.user.zone) |
            Q(report_type='LGA_TO_ZONAL')
        ).order_by('-created_at')
    elif request.user.role == 'LGA':
        reports = Report.objects.filter(
            Q(submitted_by__lga=request.user.lga) |
            Q(report_type='WARD_TO_LGA')
        ).order_by('-created_at')
    else:
        reports = Report.objects.none()
    
    context = {
        'reports': reports,
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
    
    context = {
        'unverified_donations': unverified_donations,
    }
    
    return render(request, 'staff/dashboards/treasurer.html', context)

@specific_role_required('Financial Secretary')
def financial_secretary_dashboard(request):
    from donations.models import Donation
    verified_donations = Donation.objects.filter(status='VERIFIED').count()
    
    context = {
        'verified_donations': verified_donations,
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
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_coordinator.html', context)

@specific_role_required('Vice President')
def vice_president_dashboard(request):
    total_members = User.objects.filter(status='APPROVED').count()
    total_leaders = User.objects.filter(status='APPROVED').exclude(role='GENERAL').count()
    pending_reports = Report.objects.filter(is_reviewed=False).count()
    
    context = {
        'total_members': total_members,
        'total_leaders': total_leaders,
        'pending_reports': pending_reports,
    }
    
    return render(request, 'staff/dashboards/vice_president.html', context)

@specific_role_required('Assistant General Secretary')
def assistant_general_secretary_dashboard(request):
    context = {}
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
    from donations.models import FinancialReport
    total_reports = FinancialReport.objects.count() if hasattr(FinancialReport, 'objects') else 0
    
    context = {
        'total_reports': total_reports,
    }
    
    return render(request, 'staff/dashboards/auditor_general.html', context)

@specific_role_required('Welfare Officer')
def welfare_officer_dashboard(request):
    total_members = User.objects.filter(status='APPROVED').count()
    
    context = {
        'total_members': total_members,
    }
    
    return render(request, 'staff/dashboards/welfare_officer.html', context)

@specific_role_required('Youth Development & Empowerment Officer')
def youth_empowerment_officer_dashboard(request):
    total_members = User.objects.filter(status='APPROVED').count()
    
    context = {
        'total_members': total_members,
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
    
    context = {
        'published_campaigns': published_campaigns,
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
    
    context = {
        'members_in_ward': members_in_ward,
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
