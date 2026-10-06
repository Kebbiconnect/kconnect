"""
core/context_processors.py
Injects notification data into every template automatically.
Register this in settings.py under TEMPLATES -> OPTIONS -> context_processors.
"""
from .models import Notification


def notifications_processor(request):
    """Add unread notification count and recent notifications to all templates."""
    if not request.user.is_authenticated:
        return {}

    try:
        unread_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        recent = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:6]
    except Exception:
        unread_count = 0
        recent = []

    return {
        'unread_notifications_count': unread_count,
        'recent_notifications': recent,
    }
