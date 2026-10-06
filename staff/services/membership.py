from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from leadership.access import can_approve_members, require_jurisdiction
from core.notifications import notify

@transaction.atomic
def decide_application(actor, applicant, decision):
    if not can_approve_members(actor): raise PermissionDenied('This role cannot decide membership applications.')
    require_jurisdiction(actor, applicant)
    if applicant.status not in ('PENDING', 'UNDER_REVIEW'): raise ValidationError({'status': 'Application is no longer pending.'})
    if decision == 'approve':
        applicant.status='VERIFIED'; applicant.approved_by=actor; applicant.date_approved=timezone.now()
        applicant.save(update_fields=['status','approved_by','date_approved','updated_at'])
        notify(applicant,'SUCCESS','Membership Approved','Your KPN membership has been approved.','/account/dashboard/', event='MEMBER_APPROVED')
    elif decision == 'reject':
        # Preserve the record for auditability instead of deleting an application.
        applicant.status='REJECTED'; applicant.save(update_fields=['status','updated_at'])
        notify(applicant,'WARNING','Membership Application Update','Your KPN membership application was not approved.','', event='MEMBER_REJECTED')
    else: raise ValidationError({'decision':'Use approve or reject.'})
    return applicant
