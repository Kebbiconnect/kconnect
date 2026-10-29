from django.db.models import Q
from leadership.access import is_verified, has_full_access, role_title
from .models import Item

EDITORS = {'Director of Media & Communications','Assistant Director of Media & Communications','President','General Secretary'}

def active(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or is_verified(user)))

def editor(user): return active(user) and (user.is_superuser or (user.is_leader() and role_title(user) in EDITORS))

def manager(user):
    return active(user) and (user.is_superuser or role_title(user)=='Director of Media & Communications')

def items_for(user):
    if not active(user): return Item.objects.none()
    # Hierarchical reports retain their existing supervisor/full-access boundary.
    report_scope = Q(report__submitted_to=user)
    if has_full_access(user): report_scope = Q(report__isnull=False)
    allowed = Q(kind='REPORT_EDIT') & report_scope
    if editor(user): allowed |= ~Q(kind__in=['REPORT_EDIT','COMMUNITY_EDIT'])
    from leadership.capabilities import capabilities_for
    if active(user) and 'REVIEW_COMMUNITY_REPORTS' in capabilities_for(user):
        allowed |= Q(kind='COMMUNITY_EDIT')
    return Item.objects.filter(allowed).select_related('report','community_report','source','article','opportunity')
