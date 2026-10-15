"""Concise dashboard shortcuts, filtered by existing web permissions."""
from django.urls import reverse
from leadership.access import is_verified, role_title, has_full_access
from leadership.capabilities import capabilities_for

def actions_for(user):
    if not is_verified(user):
        return []
    caps = set(capabilities_for(user))
    title = role_title(user)
    full = has_full_access(user)
    actions = []
    def add(key, label, icon, route, allowed=True):
        if allowed:
            actions.append({'key': key, 'label': label, 'icon': icon, 'url': reverse(route)})
    # Functional shortcuts precede common tools. Web-only title checks mirror
    # their existing decorators; API capabilities never grant extra web access.
    add('applications', 'Applications', 'user-check', 'staff:approve_members', 'REVIEW_APPLICANTS' in caps)
    add('editorial', 'Review articles', 'newspaper', 'campaigns:approval_queue', 'REVIEW_ARTICLES' in caps)
    add('donations', 'Donations', 'receipt', 'donations:treasurer_donations', full or title == 'Director of Finance')
    add('expenses', 'Expenses', 'wallet', 'donations:expenses_list', full or title == 'Finance Operations Officer')
    add('financial_reports', 'Financial reports', 'chart-line', 'donations:financial_reports', full or title == 'Finance Operations Officer')
    add('audit', 'Prepare audit', 'clipboard-check', 'staff:create_audit_report', 'MANAGE_AUDIT_REPORTS' in caps)
    add('legal', 'Legal review', 'balance-scale', 'staff:legal_review_queue', 'LEGAL_REVIEW' in caps)
    add('events_create', 'Create event', 'calendar-plus', 'events:create_event', 'MANAGE_EVENTS' in caps)
    add('minutes', 'Meeting minutes', 'file-alt', 'events:all_meeting_minutes', 'EDIT_MINUTES' in caps)
    add('women', 'Women’s programmes', 'users', 'staff:womens_programs_list', full or title in {"Director of Women's Development", "Assistant Director of Women's Development"})
    add('youth', 'Youth programmes', 'graduation-cap', 'staff:youth_programs_list', full or title == 'Director of Youth Development')
    add('welfare', 'Welfare programmes', 'hands-helping', 'staff:welfare_programs_list', full or title == 'Director of Member Support & Welfare')
    add('faq', 'Manage FAQ', 'question-circle', 'staff:faq_list', 'MANAGE_FAQ' in caps)
    add('outreach', 'Partnerships', 'handshake', 'staff:outreach_list', 'MANAGE_OUTREACH' in caps)
    add('ward_meetings', 'Ward meetings', 'calendar-check', 'staff:ward_meetings_list', bool(getattr(user, 'ward_id', None)) and (full or title in {'Ward Community Lead', 'Ward Administrative Officer', 'Ward Programmes Officer'}))
    add('mobilization', 'Mobilization', 'users', 'staff:member_mobilization', full or title in {'President','Director of Community Engagement','Assistant Director of Community Engagement','LGA Community Engagement Officer','Senatorial Director','LGA Network Lead','Ward Community Lead'})
    add('reports', 'Review reports', 'file-alt', 'staff:view_reports', bool(caps & {'REVIEW_REPORTS','OVERSIGHT_REPORTS'}))
    add('submit_report', 'Submit report', 'paper-plane', 'core:submit_report', 'SUBMIT_REPORTS' in caps)
    add('upload', 'Upload media', 'camera', 'media:create_media', 'UPLOAD_MEDIA' in caps)
    add('members', 'Members', 'users', 'staff:my_jurisdiction_members', 'VIEW_MEMBERS' in caps)
    add('announcements', 'Announcement', 'bullhorn', 'staff:create_announcement', 'CREATE_ANNOUNCEMENT' in caps)
    add('articles', 'Write article', 'pen', 'campaigns:create_campaign', 'WRITE_ARTICLES' in caps)
    add('opportunities_manage', 'Manage opportunities', 'briefcase', 'staff:manage_opportunities', 'MANAGE_HUBS' in caps)
    add('community_manage', 'Community hub', 'hands-helping', 'staff:manage_community_initiatives', 'MANAGE_HUBS' in caps)
    add('advocacy_manage', 'Advocacy hub', 'vote-yea', 'staff:manage_advocacy_campaigns', 'MANAGE_HUBS' in caps)
    add('patrons', 'Patrons', 'crown', 'staff:manage_patrons', 'MANAGE_PATRONS' in caps)
    add('reporters', 'Trusted reporters', 'user-shield', 'staff:trusted_reporters_list', 'MANAGE_REPORTERS' in caps)
    add('staff', 'Staff directory', 'users-cog', 'staff:manage_staff', 'STAFF_VIEW' in caps)
    add('discipline', 'Discipline', 'gavel', 'staff:disciplinary_actions', 'VIEW_DISCIPLINE' in caps)
    add('export', 'Export members', 'file-csv', 'staff:export_members_csv', 'EXPORT_MEMBERS' in caps)
    add('all_articles', 'All articles', 'list', 'campaigns:all_campaigns', 'ALL_ARTICLES' in caps)
    add('review_media', 'Review media', 'check-double', 'media:review_media', 'REVIEW_MEDIA' in caps)
    add('announcements_list', 'Announcements', 'bullhorn', 'staff:announcements_list', 'CREATE_ANNOUNCEMENT' in caps)
    add('my_reports', 'My reports', 'file-alt', 'staff:view_reports', 'SUBMIT_REPORTS' in caps)
    add('profile', 'My profile', 'user-circle', 'staff:profile')
    add('opportunities', 'Opportunities', 'briefcase', 'core:opportunities')
    add('newsroom', 'Newsroom', 'newspaper', 'campaigns:newsroom')
    add('calendar', 'Event calendar', 'calendar', 'events:event_calendar')
    add('rankings', 'Network rankings', 'trophy', 'core:network_rankings')
    priority = {
        'President': ['applications','reports','announcements','members'],
        'Director of Media & Communications': ['editorial','upload','articles','announcements'],
        'Vice President': ['members','reports','announcements','calendar'],
        'Director of Finance': ['donations','announcements','members','calendar'],
        'Finance Operations Officer': ['expenses','financial_reports','announcements','members'],
    }.get(title, [])
    return sorted(actions, key=lambda a: priority.index(a['key']) if a['key'] in priority else len(priority) + actions.index(a))
