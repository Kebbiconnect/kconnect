from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import User
from leadership.models import Zone, LGA, Ward, RoleDefinition

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
    
    context = {
        'user': user,
    }
    
    if user.role == 'STATE':
        pending_approvals = User.objects.filter(status='PENDING').count()
        total_members = User.objects.filter(status='APPROVED').count()
        context.update({
            'pending_approvals': pending_approvals,
            'total_members': total_members,
        })
    
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
