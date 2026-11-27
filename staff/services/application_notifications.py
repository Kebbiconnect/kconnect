"""Approver notifications for new membership applications.

Owner request (27 Nov 2026): when a person applies for any role, the
leaders responsible for approving that application should receive an
in-app notification (with push) naming the applicant, the role applied
for and the applicant's location — for example, an applicant in
Birnin Kebbi LGA is notified to the President, the Director of Media,
that LGA's leadership and the Senatorial leadership of Kebbi Central.

"Responsible" is defined by the platform's own decision rules: a
leader is notified exactly when `member_admin.assert_can_decide`
would let them decide this application (verified, can approve, inside
jurisdiction, tier ceiling respected). Only one of them can actually
decide: `decide_application` locks the applicant row and refuses a
second decision with "This application is no longer pending", so the
other notified leaders see the decided state when they open it.
"""
import logging

from leadership.access import can_approve_members, is_in_jurisdiction, role_title
from staff.models import User

logger = logging.getLogger(__name__)

TIER_RANK = {"GENERAL": 0, "WARD": 1, "LGA": 2, "ZONAL": 3, "STATE": 4}
STATE_TIER_TITLES = {"President", "Vice President", "Director of Media & Communications"}


def approvers_for(applicant):
    """Every verified leader who could decide this application."""
    applicant_tier = applicant.role_definition.tier if applicant.role_definition_id else applicant.role
    result = []
    candidates = (
        User.objects.filter(status="VERIFIED", is_active=True, is_superuser=False)
        .select_related("role_definition", "zone", "lga", "ward")
        .exclude(pk=applicant.pk)
    )
    for user in candidates:
        if not can_approve_members(user):
            continue
        if not is_in_jurisdiction(user, applicant):
            continue
        if applicant_tier == "STATE" and role_title(user) not in STATE_TIER_TITLES:
            continue
        if TIER_RANK.get(user.role, -1) < TIER_RANK.get(applicant_tier, 99):
            continue
        result.append(user)
    return result


def notify_application_approvers(applicant_id):
    """Create the MEMBER_APPLIED notification (+ push) for every
    responsible approver. Never raises: a notification failure must not
    break a registration."""
    try:
        applicant = (
            User.objects.select_related("role_definition", "zone", "lga", "ward")
            .filter(pk=applicant_id)
            .first()
        )
        if applicant is None or applicant.status not in ("PENDING", "UNDER_REVIEW"):
            return []
        approvers = approvers_for(applicant)
        if not approvers:
            return []
        name = applicant.get_full_name() or applicant.username
        role_label = (
            applicant.role_definition.canonical_title
            if applicant.role_definition_id
            else "General Member"
        )
        location = " · ".join(
            part
            for part in (
                applicant.ward.name if applicant.ward_id else "",
                applicant.lga.name if applicant.lga_id else "",
                applicant.zone.name if applicant.zone_id else "",
            )
            if part
        )
        message = f"{name} applied for {role_label}"
        if location:
            message += f" — {location}"
        message += ". Waiting for approval."
        from core.notifications import notify_many

        return notify_many(
            approvers,
            "INFO",
            "New membership application",
            message,
            link="/account/pending-members/",
            event="MEMBER_APPLIED",
            target_type="member",
            target_id=applicant.id,
        )
    except Exception:
        logger.exception("notify_application_approvers failed for user pk=%s", applicant_id)
        return []
