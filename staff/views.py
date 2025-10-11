from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from .models import User, DisciplinaryAction
from .decorators import specific_role_required, role_required, approved_leader_required
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
        
        if role_title == 'President':
            return redirect('staff:president_dashboard')
        elif role_title == 'Director of Media & Publicity':
            return redirect('staff:media_director_dashboard')
        elif role_title == 'Treasurer':
            return redirect('staff:treasurer_dashboard')
        elif role_title == 'Financial Secretary':
            return redirect('staff:financial_secretary_dashboard')
        elif role_title == 'Organizing Secretary':
            return redirect('staff:organizing_secretary_dashboard')
        elif role_title == 'General Secretary':
            return redirect('staff:general_secretary_dashboard')
        elif role_title == 'Zonal Coordinator':
            return redirect('staff:zonal_coordinator_dashboard')
        elif role_title == 'LGA Coordinator':
            return redirect('staff:lga_coordinator_dashboard')
        elif role_title == 'Ward Coordinator':
            return redirect('staff:ward_coordinator_dashboard')
    
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
    upcoming_events = Event.objects.filter(start_date__gte=timezone.now()).count()
    
    context = {
        'upcoming_events': upcoming_events,
    }
    
    return render(request, 'staff/dashboards/organizing_secretary.html', context)

@specific_role_required('General Secretary')
def general_secretary_dashboard(request):
    context = {}
    return render(request, 'staff/dashboards/general_secretary.html', context)

@specific_role_required('Zonal Coordinator')
def zonal_coordinator_dashboard(request):
    lgas_in_zone = LGA.objects.filter(zone=request.user.zone).count()
    members_in_zone = User.objects.filter(zone=request.user.zone, status='APPROVED').count()
    
    context = {
        'lgas_in_zone': lgas_in_zone,
        'members_in_zone': members_in_zone,
    }
    
    return render(request, 'staff/dashboards/zonal_coordinator.html', context)

@specific_role_required('LGA Coordinator')
def lga_coordinator_dashboard(request):
    wards_in_lga = Ward.objects.filter(lga=request.user.lga).count()
    members_in_lga = User.objects.filter(lga=request.user.lga, status='APPROVED').count()
    
    context = {
        'wards_in_lga': wards_in_lga,
        'members_in_lga': members_in_lga,
    }
    
    return render(request, 'staff/dashboards/lga_coordinator.html', context)

@specific_role_required('Ward Coordinator')
def ward_coordinator_dashboard(request):
    members_in_ward = User.objects.filter(ward=request.user.ward, status='APPROVED').count()
    
    context = {
        'members_in_ward': members_in_ward,
    }
    
    return render(request, 'staff/dashboards/ward_coordinator.html', context)
