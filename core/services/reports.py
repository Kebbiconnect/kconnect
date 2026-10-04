from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from leadership.access import report_visible_to
from staff.models import User
from core.notifications import notify

RECIPIENT_ROLE = {'WARD_TO_LGA':'LGA Network Lead','LGA_TO_ZONAL':'Senatorial Director','ZONAL_TO_STATE':'Director of Monitoring & Compliance'}

def recipient_for(submitter, report_type):
    qs=User.objects.filter(status='VERIFIED', role_definition__title=RECIPIENT_ROLE[report_type])
    if report_type=='WARD_TO_LGA': qs=qs.filter(lga=submitter.lga)
    elif report_type=='LGA_TO_ZONAL': qs=qs.filter(zone=submitter.zone)
    return qs.order_by('id').first()

@transaction.atomic
def submit_report(user, **data):
    from core.models import Report
    expected={'WARD':'WARD_TO_LGA','LGA':'LGA_TO_ZONAL','ZONAL':'ZONAL_TO_STATE'}.get(user.role)
    if not expected: raise PermissionDenied('This tier cannot submit hierarchical reports.')
    if data.get('report_type') and data['report_type'] != expected: raise ValidationError({'report_type':'Report type must match your tier.'})
    recipient=recipient_for(user,expected)
    if not recipient: raise ValidationError({'submitted_to':'No verified recipient is configured for your jurisdiction.'})
    report=Report.objects.create(title=data['title'],content=data['content'],period=data.get('period',''),deadline=data.get('deadline'),report_type=expected,submitted_by=user,submitted_to=recipient,status='SUBMITTED',submitted_at=timezone.now())
    notify(recipient,'ACTION','Report Submitted',f'{user.get_full_name()} submitted “{report.title}”.',f'/account/view-reports/',event='REPORT_SUBMITTED')
    return report

@transaction.atomic
def review_report(actor, report, action, notes=''):
    if not report_visible_to(actor, report) or (report.submitted_to_id not in (None,actor.id) and actor.role!='STATE'):
        raise PermissionDenied('You cannot review this report.')
    transitions={'approve':'APPROVED','flag':'FLAGGED','reject':'REJECTED','under_review':'UNDER_REVIEW'}
    if action not in transitions: raise ValidationError({'action':'Unsupported report action.'})
    report.status=transitions[action]; report.review_notes=notes; report.reviewed_by=actor; report.reviewed_at=timezone.now(); report.is_reviewed=action!='under_review'
    report.save(update_fields=['status','review_notes','reviewed_by','reviewed_at','is_reviewed'])
    notify(report.submitted_by,'INFO','Report Updated',f'“{report.title}” is now {report.get_status_display()}.','/account/view-reports/',event='REPORT_REVIEWED')
    return report

@transaction.atomic
def escalate_report(actor, report):
    if not report_visible_to(actor, report): raise PermissionDenied('You cannot escalate this report.')
    if not report.can_be_escalated(): raise ValidationError({'status':'Only approved, non-escalated Ward/LGA reports can be escalated.'})
    next_type='LGA_TO_ZONAL' if report.report_type=='WARD_TO_LGA' else 'ZONAL_TO_STATE'
    recipient=recipient_for(actor,next_type)
    if not recipient: raise ValidationError({'submitted_to':'No next-tier recipient is configured.'})
    child=type(report).objects.create(title=report.title,content=report.content,period=report.period,deadline=report.deadline,report_type=next_type,submitted_by=actor,submitted_to=recipient,parent_report=report,status='SUBMITTED',submitted_at=timezone.now())
    report.is_escalated=True; report.escalated_at=timezone.now(); report.save(update_fields=['is_escalated','escalated_at'])
    notify(recipient,'ACTION','Report Escalated',f'“{report.title}” was escalated to you.','/account/view-reports/',event='REPORT_ESCALATED')
    return child
