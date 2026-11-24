"""
core/context_processors.py
Injects notification data into every template automatically.
Register this in settings.py under TEMPLATES -> OPTIONS -> context_processors.
"""
from .notification_queries import visible_notifications


def notifications_processor(request):
    """Add unread notification count and recent notifications to all templates."""
    if not request.user.is_authenticated:
        return {}

    try:
        unread_count = visible_notifications(request.user).filter(is_read=False).count()
        recent = visible_notifications(request.user).order_by('-created_at')[:6]
    except Exception:
        unread_count = 0
        recent = []

    return {
        'unread_notifications_count': unread_count,
        'recent_notifications': recent,
    }


def ict_admin_navigation(request):
    """Expose ``ict_admin_available`` for the nav's ICT Admin link.

    The link renders ONLY for the assigned ICT Admin holder or a
    super admin (server-side conditional, decided here — not CSS).
    Fail-safe like the notifications processor: any error means the
    link simply does not render.
    """
    if not request.user.is_authenticated:
        return {'ict_admin_available': False}
    try:
        from .ict_admin import can_access_ict_admin

        available = can_access_ict_admin(request.user)
    except Exception:
        available = False
    return {'ict_admin_available': available}
