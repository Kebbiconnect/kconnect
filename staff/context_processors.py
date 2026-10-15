from .models import Announcement


def announcements(request):
    """
    Context processor to add active announcements for the current user to all templates
    """
    user_announcements = []
    
    if request.user.is_authenticated:
        user_announcements = list(Announcement.for_user(request.user)[:10])
    
    return {
        'user_announcements': user_announcements,
        'announcement_data': [
            {'title': item.title, 'content': item.content, 'priority': item.priority}
            for item in user_announcements
        ]
    }
