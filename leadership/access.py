"""Server-side role and jurisdiction policy shared by website and REST APIs."""
from rest_framework.exceptions import PermissionDenied

ACTIVE_USER_STATUS = 'VERIFIED'
PENDING_USER_STATUSES = ('PENDING', 'UNDER_REVIEW')


def role_title(user):
    return getattr(getattr(user, 'role_definition', None), 'title', '')


def is_verified(user):
    return bool(user and user.is_authenticated and user.status == ACTIVE_USER_STATUS)


def is_in_jurisdiction(actor, target):
    if not is_verified(actor): return False
    if actor.role == 'STATE': return True
    if actor.role == 'ZONAL': return bool(actor.zone_id and actor.zone_id == target.zone_id)
    if actor.role == 'LGA': return bool(actor.lga_id and actor.lga_id == target.lga_id)
    if actor.role == 'WARD': return bool(actor.ward_id and actor.ward_id == target.ward_id)
    return actor.pk == target.pk


def scope_users(actor, queryset=None):
    from staff.models import User
    qs = queryset if queryset is not None else User.objects.all()
    qs = qs.filter(is_superuser=False)
    if actor.role == 'STATE': return qs
    if actor.role == 'ZONAL' and actor.zone_id: return qs.filter(zone_id=actor.zone_id)
    if actor.role == 'LGA' and actor.lga_id: return qs.filter(lga_id=actor.lga_id)
    if actor.role == 'WARD' and actor.ward_id: return qs.filter(ward_id=actor.ward_id)
    return qs.filter(pk=actor.pk)


def require_jurisdiction(actor, target):
    if not is_in_jurisdiction(actor, target):
        raise PermissionDenied('The requested object is outside your jurisdiction.')
    return target


def can_approve_members(user):
    return is_verified(user) and user.role in ('STATE', 'ZONAL', 'LGA')


def report_visible_to(user, report):
    if report.submitted_by_id == user.id or report.submitted_to_id == user.id: return True
    return role_title(user) in ('President', 'Director of Monitoring & Compliance')
