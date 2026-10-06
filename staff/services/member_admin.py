"""Authoritative member visibility and application decision rules."""
from dataclasses import dataclass
from django.db import transaction
from django.utils import timezone
from leadership.access import can_approve_members,is_in_jurisdiction,users_in_jurisdiction,role_title
from staff.models import User
from staff.services.vacancy import seat_is_filled

ENFORCE_TIER_CEILING=True
TIER_RANK={"GENERAL":0,"WARD":1,"LGA":2,"ZONAL":3,"STATE":4}
PENDING_STATUSES=("PENDING","UNDER_REVIEW")

class MemberDecisionError(Exception):
 def __init__(self,code,message): self.code=code; self.message=message; super().__init__(message)

def pending_applicants_qs(viewer):
 base=User.objects.filter(status__in=PENDING_STATUSES,is_superuser=False).select_related("role_definition","zone","lga","ward").order_by("-created_at")
 return users_in_jurisdiction(viewer,base) if can_approve_members(viewer) else base.none()

def members_qs(viewer):
 base=User.objects.filter(is_superuser=False).select_related("role_definition","zone","lga","ward").order_by("last_name","first_name","id")
 return users_in_jurisdiction(viewer,base) if viewer.role in {"STATE","ZONAL","LGA","WARD"} else base.filter(pk=viewer.pk)

def assert_can_decide(approver,applicant):
 if not can_approve_members(approver): raise MemberDecisionError("permission_denied","Your role cannot decide membership applications.")
 if applicant.is_superuser or not is_in_jurisdiction(approver,applicant): raise MemberDecisionError("outside_jurisdiction","This applicant is outside your jurisdiction.")
 if applicant.status not in PENDING_STATUSES: raise MemberDecisionError("invalid_status","This application is no longer pending.")
 applicant_tier=applicant.role_definition.tier if applicant.role_definition else applicant.role
 if applicant_tier=="STATE" and role_title(approver) not in {"President","Vice President"}:
  raise MemberDecisionError("tier_ceiling","Only the President or Vice President may approve State applicants.")
 if ENFORCE_TIER_CEILING and TIER_RANK.get(approver.role,-1)<TIER_RANK.get(applicant_tier,99):
  raise MemberDecisionError("tier_ceiling","You cannot approve an applicant above your tier.")

def decide_application(approver,applicant_id,decision):
 if decision not in {"approve","reject"}: raise MemberDecisionError("invalid_decision","Decision must be approve or reject.")
 with transaction.atomic():
  applicant=User.objects.select_for_update().select_related("role_definition","zone","lga","ward").get(pk=applicant_id)
  assert_can_decide(approver,applicant)
  if decision=="approve":
   if applicant.role_definition and seat_is_filled(applicant.role_definition,applicant.zone,applicant.lga,applicant.ward):
    raise MemberDecisionError("seat_filled","This position is already filled.")
   applicant.status="VERIFIED"; applicant.approved_by=approver; applicant.date_approved=timezone.now()
   applicant.save(update_fields=["status","approved_by","date_approved","updated_at"])
   from core.notifications import notify
   notify(applicant,notif_type="SUCCESS",title="Membership Approved",message="Congratulations! Your KPN membership has been approved.",link="/account/dashboard/",event="MEMBER_APPROVED",target_type="member",target_id=applicant.id)
   return applicant
  snapshot=applicant
  applicant.delete()
  snapshot.status="REJECTED"
  return snapshot
