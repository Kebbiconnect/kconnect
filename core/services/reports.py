"""Authoritative hierarchical report workflow for website and APIs."""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from core.models import Report
from leadership.access import role_title
from staff.models import User

class ReportWorkflowError(Exception):
 def __init__(self,code,message,field=None): self.code=code; self.message=message; self.field=field; super().__init__(message)

def recipient_for(user):
 if user.role=="WARD":
  if not user.ward_id: raise ReportWorkflowError("missing_jurisdiction","Your ward assignment is missing.","submitted_to")
  return User.objects.filter(role="LGA",lga=user.ward.lga,role_definition__title="LGA Network Lead",status="VERIFIED").first()
 if user.role=="LGA":
  if not user.lga_id: raise ReportWorkflowError("missing_jurisdiction","Your LGA assignment is missing.","submitted_to")
  return User.objects.filter(role="ZONAL",zone=user.lga.zone,role_definition__title="Senatorial Director",status="VERIFIED").first()
 if user.role=="ZONAL":
  return User.objects.filter(role="STATE",role_definition__title="Director of Monitoring & Compliance",status="VERIFIED").first()
 raise ReportWorkflowError("permission_denied","Report submission is only available for Ward, LGA, and Zonal leaders.")

def report_type_for(user): return {"WARD":"WARD_TO_LGA","LGA":"LGA_TO_ZONAL","ZONAL":"ZONAL_TO_STATE"}.get(user.role)

def create_report(user,**data):
 recipient=recipient_for(user)
 if not recipient: raise ReportWorkflowError("recipient_unavailable","No verified recipient is set up for your area yet. Contact your lead.","submitted_to")
 report=Report.objects.create(submitted_by=user,submitted_to=recipient,report_type=report_type_for(user),status="SUBMITTED",submitted_at=timezone.now(),**data)
 send_report_notification(report,"submitted")
 return report

def reports_for(user):
 title=role_title(user)
 qs=Report.objects.select_related("submitted_by","submitted_to","reviewed_by","parent_report")
 if title in {"President","Director of Monitoring & Compliance"}: return qs.order_by("-created_at")
 return qs.filter(Q(submitted_by=user)|Q(submitted_to=user)).distinct().order_by("-created_at")

def can_review(user,report): return report.submitted_to_id==user.id or role_title(user)=="President"

def escalate_report(original,reviewer):
 if original.report_type=="WARD_TO_LGA":
  submitter=original.submitted_by; zone=submitter.zone or (submitter.ward.lga.zone if submitter.ward_id else None) or (submitter.lga.zone if submitter.lga_id else None)
  next_type="LGA_TO_ZONAL"; supervisor=User.objects.filter(role="ZONAL",zone=zone,role_definition__title="Senatorial Director",status="VERIFIED").first() if zone else None
 elif original.report_type=="LGA_TO_ZONAL":
  next_type="ZONAL_TO_STATE"; supervisor=User.objects.filter(role="STATE",role_definition__title="Director of Monitoring & Compliance",status="VERIFIED").first()
 else: raise ReportWorkflowError("not_escalatable","This report cannot be escalated further.")
 if not supervisor: raise ReportWorkflowError("recipient_unavailable","No verified recipient is set up for the next level.","submitted_to")
 actual_submitter=original.submitted_to or reviewer
 child=Report.objects.create(title=f"Consolidated {original.get_report_type_display()} - {original.period}",report_type=next_type,content=f"[Escalated from {actual_submitter.get_full_name()}]\n[Approved by: {reviewer.get_full_name()}]\n\n{original.content}",period=original.period,submitted_by=actual_submitter,submitted_to=supervisor,parent_report=original,status="SUBMITTED",submitted_at=timezone.now(),deadline=original.deadline)
 original.is_escalated=True; original.escalated_at=timezone.now(); original.status="ESCALATED"; original.save(update_fields=["is_escalated","escalated_at","status"])
 send_report_notification(child,"submitted")
 return child

@transaction.atomic
def review_report(user,report_id,action,notes="",auto_escalate=True):
 if action not in {"APPROVED","FLAGGED","REJECTED"}: raise ReportWorkflowError("invalid_action","Use APPROVED, FLAGGED or REJECTED.","action")
 report=Report.objects.select_for_update().select_related("submitted_by","submitted_to").get(pk=report_id)
 if not can_review(user,report): raise ReportWorkflowError("permission_denied","You do not have permission to review this report.")
 if action in {"FLAGGED","REJECTED"} and not notes.strip(): raise ReportWorkflowError("notes_required","Review notes are required when flagging or rejecting.","notes")
 report.status=action; report.review_notes=notes; report.is_reviewed=True; report.reviewed_by=user; report.reviewed_at=timezone.now(); report.save()
 send_report_notification(report,"reviewed")
 child=None
 if action=="APPROVED" and report.can_be_escalated() and auto_escalate:
  try: child=escalate_report(report,user)
  except ReportWorkflowError as exc:
   if exc.code!="recipient_unavailable": raise
 return report,child

def send_report_notification(report,kind):
 from core.notifications import notify
 if kind=="submitted" and report.submitted_to:
  notify(report.submitted_to,notif_type="INFO",title="New Report Submitted",message=f"{report.submitted_by.get_full_name()} submitted a {report.get_report_type_display()}.",link=f"/account/review-report/{report.id}/",event="REPORT_SUBMITTED",target_type="report",target_id=report.id)
 elif kind=="reviewed" and report.submitted_by:
  kind_map={"APPROVED":"SUCCESS","REJECTED":"ACTION","FLAGGED":"WARNING"}
  notify(report.submitted_by,notif_type=kind_map.get(report.status,"INFO"),title=f"Report {report.get_status_display()}",message=f"Your report '{report.title}' was reviewed by {report.reviewed_by.get_full_name() if report.reviewed_by else 'a supervisor'}.",link="#",event="REPORT_REVIEWED",target_type="report",target_id=report.id)
