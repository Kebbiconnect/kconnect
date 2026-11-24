"""ICT Admin console — access rules and the initial-holder seed.

Owner instruction (2026-11-24): KPN has no "ICT Admin" role. The
Director of Media & Communications IS the ICT admin; the console at
``/ict-admin/`` is his dedicated page for seeing and checking
everything ICT-related across the site. The assignment is
transferable, but ONLY the Super Admin may move it, and only in the
Django admin panel — the Super Admin operates only through /admin/
(owner clarification, 2026-11-24); not even the President can change
it, and the console page itself carries no change controls.

Access rule (the whole rule, nothing wider):

- the assigned holder (``core.IctAdminAssignment.user``), or
- any superuser (``is_superuser=True``)

may open the console. Everyone else gets the site's standard denial
for gated pages.

The seed below runs fail-safe inside ``release_migrate`` (production
deploys have no shell access, so no step may be manual). It is
idempotent and edit-preserving, like the intelligence seeds: once a
holder is recorded — by the seed or by a super admin's reassignment —
the seed never overwrites it. If no Director of Media exists yet, the
assignment is left unassigned and the console stays superuser-only
until a super admin assigns a holder.
"""
import logging

from leadership.access import role_title

from .models import IctAdminAssignment

logger = logging.getLogger(__name__)

DIRECTOR_OF_MEDIA_TITLE = 'Director of Media & Communications'


def current_assignment():
    """The singleton assignment row, created empty on first use."""
    assignment, _ = IctAdminAssignment.objects.get_or_create(pk=1)
    return assignment


def current_holder():
    """The assigned ICT Admin holder, or None when unassigned."""
    assignment = IctAdminAssignment.objects.filter(pk=1).first()
    if assignment is None:
        return None
    return assignment.user


def is_ict_admin(user):
    """True when ``user`` may open the ICT Admin console."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    holder = current_holder()
    return holder is not None and holder.pk == user.pk


def can_access_ict_admin(user):
    return is_ict_admin(user)


def _find_director_of_media():
    """The Director of Media & Communications account, if one exists.

    Resolved through the canonical role title (leadership.access),
    so legacy title spellings still match. A VERIFIED holder wins;
    ties break to the earliest account. Superuser accounts are never
    seeded as holder — super admins already have console access, and
    the assignment names a member/position holder.
    """
    from staff.models import User

    candidates = (
        User.objects.filter(is_superuser=False,
                            role_definition__isnull=False)
        .select_related('role_definition')
        .order_by('created_at', 'pk'))
    fallback = None
    for candidate in candidates:
        if role_title(candidate) != DIRECTOR_OF_MEDIA_TITLE:
            continue
        if candidate.status == 'VERIFIED':
            return candidate
        if fallback is None:
            fallback = candidate
    return fallback


def seed_ict_admin_assignment():
    """Record the Director of Media as the initial ICT Admin holder.

    Returns the assignment row. Never overwrites an existing holder:
    a super admin's reassignment (or an earlier seed) always stands.
    When no Director of Media exists, the row is created unassigned.
    """
    assignment = current_assignment()
    if assignment.user_id is not None:
        return assignment
    director = _find_director_of_media()
    if director is None:
        logger.info(
            'seed_ict_admin: no Director of Media & Communications '
            'account found; ICT Admin left unassigned (console is '
            'superuser-only until a super admin assigns a holder).')
        return assignment
    assignment.user = director
    assignment.save(update_fields=['user', 'updated_at'])
    logger.info('seed_ict_admin: ICT Admin assigned to %s.', director)
    return assignment
