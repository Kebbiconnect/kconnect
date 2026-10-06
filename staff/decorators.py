from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from leadership.roles import canonical_role_title

def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.status != 'VERIFIED':
                messages.error(request, 'Your account is pending verification.')
                return redirect('core:home')
            
            if request.user.role not in allowed_roles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('staff:dashboard')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def specific_role_required(*role_titles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.status != 'VERIFIED':
                messages.error(request, 'Your account is pending verification.')
                return redirect('core:home')
            
            # Super Access for President and Director of Media & Communications
            super_roles = ['President', 'Director of Media & Communications']
            actual_title = canonical_role_title(request.user.role_definition.title) if request.user.role_definition else None
            allowed_titles = {canonical_role_title(title) for title in role_titles}
            has_super_access = actual_title in super_roles
            
            if not has_super_access and actual_title not in allowed_titles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('staff:dashboard')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def approved_leader_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if request.user.status != 'VERIFIED':
            messages.error(request, 'Your account is pending verification.')
            return redirect('core:home')
        
        if not request.user.is_leader():
            messages.error(request, 'This page is only accessible to leaders.')
            return redirect('staff:dashboard')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view
