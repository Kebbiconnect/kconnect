from .models import Announcement


def announcements(request):
    """
    Context processor to add active announcements for the current user to all templates
    """
    user_announcements = []
    
    if request.user.is_authenticated:
        user_announcements = Announcement.for_user(request.user)[:10]
    
    return {
        'user_announcements': user_announcements
    }
