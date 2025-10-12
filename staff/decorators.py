from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.status != 'APPROVED':
                messages.error(request, 'Your account is not approved yet.')
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
            if request.user.status != 'APPROVED':
                messages.error(request, 'Your account is not approved yet.')
                return redirect('core:home')
            
            if not request.user.role_definition or request.user.role_definition.title not in role_titles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('staff:dashboard')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def approved_leader_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if request.user.status != 'APPROVED':
            messages.error(request, 'Your account is not approved yet.')
            return redirect('core:home')
        
        if not request.user.is_leader():
            messages.error(request, 'This page is only accessible to leaders.')
            return redirect('staff:dashboard')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view
