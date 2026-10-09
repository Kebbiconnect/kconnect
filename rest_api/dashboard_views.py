"""Role-aware, database-backed Android dashboard endpoints."""
from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiTypes
from campaigns.models import Campaign
from core.models import Report, CommunityInitiative, CommunityReport
from donations.models import Donation, Expense
from events.models import Event, MeetingMinutes
from leadership.access import users_in_jurisdiction, role_title
from leadership.capabilities import capabilities_for
from leadership.models import LGA, Ward
from staff.models import User, Announcement
from telegram_integration.permissions import check_dashboard_access
from .permissions import IsVerifiedMember, capability_permission
from leadership.roles import DASHBOARD_BY_ROLE
from .workflow_views import scoped_programs, PROGRAMS
from staff.models import DisciplinaryAction, WardMeeting, CommunityOutreach
from core.models import FAQ
from donations.models import FinancialReport, AuditReport


def item(key,label,value,currency=None):
 data={"key":key,"label":label,"value":value}
 if currency: data["currency"]=currency
 return data

def block(key,title,items,kind="metrics"):
 return {"key":key,"type":kind,"title":title,"available":True,"items":items}

def unavailable(key,title,reason):
 return {"key":key,"type":"unavailable","title":title,"available":False,"reason":reason,"items":[]}

def scoped_users(user): return users_in_jurisdiction(user,User.objects.filter(is_superuser=False))
def scoped_reports(user):
 from core.services.reports import reports_for
 return reports_for(user)

def access_denied_response(user):
 access=check_dashboard_access(user)
 if access["allowed"]: return None
 return Response({"error":{"code":access["reason"],"message":"Dashboard access is not currently available.","details":{"telegram_required":access["telegram_required"]}}},status=status.HTTP_403_FORBIDDEN)


def work_sections(user,caps):
 """Small real record queues; never expand permissions beyond the existing API services."""
 sections=[]
 def add(key,title,route,rows,empty):
  sections.append({"key":key,"title":title,"route":route,"empty_message":empty,"items":rows})
 def row(obj,title,subtitle,status,route):
  return {"id":obj.pk,"title":title,"subtitle":subtitle or "","status":status or "","route":route}
 if "REVIEW_APPLICANTS" in caps:
  from staff.services.member_admin import pending_applicants_qs
  add("membership","Applicants awaiting review","members",[row(u,u.get_full_name() or u.username,role_title(u),u.status,"members") for u in pending_applicants_qs(user)[:5]],"No applications currently await your review.")
 if {"SUBMIT_REPORTS","REVIEW_REPORTS","OVERSIGHT_REPORTS"}&caps:
  qs=scoped_reports(user).filter(status__in=("SUBMITTED","FLAGGED")).order_by("-created_at")
  add("reports","Active reports","reports",[row(r,r.title,r.period,r.status,"reports") for r in qs[:5]],"No submitted or flagged reports in your authorized queue.")
 if {"REVIEW_ARTICLES","WRITE_ARTICLES"}&caps:
  review="REVIEW_ARTICLES" in caps
  qs=Campaign.objects.filter(status="PENDING") if review else Campaign.objects.filter(author=user,status__in=("DRAFT","REJECTED","PENDING"))
  route="editorial" if review else "my_articles"
  add("editorial","Editorial review queue" if review else "Your article work",route,[row(c,c.title,c.get_category_display(),c.status,route) for c in qs.order_by("-created_at")[:5]],"No articles currently require attention.")
 if "VIEW_EVENTS" in caps:
  add("events","Upcoming events","events",[row(e,e.title,e.location,"",f"event/{e.pk}") for e in Event.objects.filter(end_date__gte=timezone.now()).order_by("start_date")[:5]],"No upcoming events have been published.")
 if "VERIFY_DONATION" in caps:
  add("finance","Donations awaiting verification","finance",[row(d,d.donor_name,"NGN "+str(d.amount),d.status,"finance") for d in Donation.objects.filter(status="UNVERIFIED").order_by("-created_at")[:5]],"No donations are awaiting verification.")
 if "MANAGE_FINANCIAL_REPORTS" in caps:
  add("finance","Financial reporting","financial_reports",[row(r,r.title,"", "","financial_reports") for r in FinancialReport.objects.order_by("-created_at")[:5]],"No financial reports have been recorded.")
 if {"MANAGE_AUDIT_REPORTS","VIEW_AUDIT_REPORTS"}&caps:
  qs=AuditReport.objects.filter(submitted_by=user) if "MANAGE_AUDIT_REPORTS" in caps else AuditReport.objects.all()
  add("audit","Audit reports","audit_reports",[row(r,r.title,"",r.status,"audit_reports") for r in qs.order_by("-created_at")[:5]],"No authorized audit reports are available.")
 if {"LEGAL_REVIEW","DECIDE_DISCIPLINE"}&caps:
  add("discipline","Pending disciplinary review","discipline",[row(d,d.user.get_full_name() or d.user.username,d.get_action_type_display(),"PENDING","discipline") for d in DisciplinaryAction.objects.filter(is_approved=False,user__is_superuser=False).select_related("user")[:5]],"No disciplinary actions await review.")
 for kind,(model,serializer,cap) in PROGRAMS.items():
  if cap in caps:
   route="programs/"+kind
   add("programs_"+kind,kind.title()+" programme delivery",route,[row(p,p.title,"",p.status,route) for p in scoped_programs(model,user).order_by("-created_at")[:5]],"No programmes have been recorded for your authorized scope.")
 if "MANAGE_WARD_MEETINGS" in caps and user.ward_id:
  add("ward_meetings","Ward meeting records","ward_meetings",[row(m,m.title,str(m.date),"","ward_meetings") for m in WardMeeting.objects.filter(ward_id=user.ward_id).order_by("-date")[:5]],"No ward meetings have been recorded.")
 if "MANAGE_OUTREACH" in caps:
  add("outreach","Partnership engagements","outreach",[row(o,o.organization,o.purpose,o.status,"outreach") for o in CommunityOutreach.objects.order_by("-created_at")[:5]],"No outreach engagements have been logged.")
 if "REVIEW_COMMUNITY_REPORTS" in caps:
  add("community_reports","Community review queue","community_report_review",[row(r,r.location_details,r.what_happened,r.status,"community_report_review") for r in CommunityReport.objects.filter(status__in=("PENDING","UNDER_REVIEW")).order_by("-created_at")[:5]],"No community reports currently await review.")
 return sections

class MyDashboardView(APIView):
 permission_classes=[permissions.IsAuthenticated]
 @extend_schema(responses={200:OpenApiTypes.OBJECT})
 def get(self,request):
  denied=access_denied_response(request.user)
  if denied: return denied
  user=request.user; caps=set(capabilities_for(user)); users=scoped_users(user); reports=scoped_reports(user)
  title="My KPN" if user.role=="GENERAL" else (user.get_jurisdiction() if user.role in {"ZONAL","LGA","WARD"} else "Executive overview")
  blocks=[block("membership","Membership",[
   item("verified_members","Verified members",users.filter(status="VERIFIED").count()),
   item("pending_members","Pending applicants",users.filter(status__in=("PENDING","UNDER_REVIEW")).count()),
  ])]
  if "SUBMIT_REPORTS" in caps or "REVIEW_REPORTS" in caps or "OVERSIGHT_REPORTS" in caps:
   blocks.append(block("reports","Reports",[
    item("submitted_reports","Submitted",reports.filter(status="SUBMITTED").count()),
    item("flagged_reports","Flagged",reports.filter(status="FLAGGED").count()),
    item("approved_reports","Approved",reports.filter(status="APPROVED").count()),
   ]))
  blocks.append(block("events","Events",[
   item("upcoming_events","Upcoming",Event.objects.filter(end_date__gte=timezone.now()).count()),
   item("published_minutes","Published minutes",MeetingMinutes.objects.filter(is_published=True).count()),
  ]))
  if "VIEW_FINANCE" in caps:
   income=Donation.objects.filter(status__in=("VERIFIED","RECORDED")).aggregate(v=Sum("amount"))["v"] or Decimal("0")
   expenses=Expense.objects.aggregate(v=Sum("amount"))["v"] or Decimal("0")
   blocks.append(block("finance","Finance",[
    item("total_income","Verified income",str(income),"NGN"),item("total_expenses","Expenses",str(expenses),"NGN"),item("balance","Balance",str(income-expenses),"NGN"),item("pending_donations","Unverified donations",Donation.objects.filter(status="UNVERIFIED").count())]))
  elif user.role in {"LGA","WARD"}:
   blocks.append(unavailable("finance","Finance","Finance is not established for this jurisdiction in the source."))
  role=role_title(user)
  # Operational blocks follow real website responsibilities, not placeholder template variables.
  if {"REVIEW_ARTICLES","WRITE_ARTICLES"} & caps:
   articles=Campaign.objects.all() if "ALL_ARTICLES" in caps else Campaign.objects.filter(author=user)
   blocks.append(block("editorial","Newsroom",[item("drafts","Drafts",articles.filter(status="DRAFT").count()),item("pending_articles","Awaiting review",articles.filter(status="PENDING").count()),item("published","Published",articles.filter(status="PUBLISHED").count())]))
  if "REVIEW_COMMUNITY_REPORTS" in caps:
   blocks.append(block("community_reports","Community reports",[item("pending","Pending",CommunityReport.objects.filter(status="PENDING").count()),item("under_review","Under review",CommunityReport.objects.filter(status="UNDER_REVIEW").count())]))
  if "MANAGE_FAQ" in caps:
   blocks.append(block("faq","FAQ administration",[item("active","Active questions",FAQ.objects.filter(is_active=True).count()),item("inactive","Inactive questions",FAQ.objects.filter(is_active=False).count())]))
  if "MANAGE_OUTREACH" in caps:
   blocks.append(block("outreach","Partnerships & outreach",[item("records","Engagement records",CommunityOutreach.objects.count())]))
  if "MANAGE_AUDIT_REPORTS" in caps:
   audits=AuditReport.objects.filter(submitted_by=user)
   blocks.append(block("audit","Audit & accountability",[item("draft","Draft audits",audits.filter(status="DRAFT").count()),item("submitted","Submitted audits",audits.filter(status="SUBMITTED").count()),item("financial_reports","Financial reports",FinancialReport.objects.count())]))
  if "LEGAL_REVIEW" in caps or "DECIDE_DISCIPLINE" in caps:
   blocks.append(block("discipline","Disciplinary review",[item("pending","Pending actions",DisciplinaryAction.objects.filter(is_approved=False).count())]))
  for kind,(model,serializer,cap) in PROGRAMS.items():
   if cap in caps:
    programs=scoped_programs(model,user)
    blocks.append(block("programs_"+kind,kind.title()+" programmes",[item("planned","Planned",programs.filter(status="PLANNED").count()),item("ongoing","Ongoing",programs.filter(status="ONGOING").count()),item("completed","Completed",programs.filter(status="COMPLETED").count())]))
  if "MANAGE_WARD_MEETINGS" in caps and user.ward_id:
   blocks.append(block("ward_meetings","Ward meeting logbook",[item("meetings","Recorded meetings",WardMeeting.objects.filter(ward=user.ward).count())]))
  return Response({"title":title,"role_title":role,"dashboard_key":DASHBOARD_BY_ROLE.get(role,"member"),"jurisdiction":user.get_jurisdiction(),"blocks":blocks,"work_sections":work_sections(user,caps)})

class SecretariatDashboardView(APIView):
 permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission("EDIT_MINUTES")]
 def get(self,request):
  return Response({"title":"Secretariat","blocks":[block("records","Records",[item("upcoming_events","Upcoming meetings",Event.objects.filter(end_date__gte=timezone.now()).count()),item("meeting_minutes","Meeting minutes",MeetingMinutes.objects.count()),item("active_announcements","Active announcements",Announcement.objects.filter(is_active=True).count())])]})

class FinanceDashboardView(APIView):
 permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission("VIEW_FINANCE")]
 def get(self,request):
  income=Donation.objects.filter(status__in=("VERIFIED","RECORDED")).aggregate(v=Sum("amount"))["v"] or Decimal("0")
  expenses=Expense.objects.aggregate(v=Sum("amount"))["v"] or Decimal("0")
  return Response({"title":"Finance","blocks":[block("finance","State finance",[item("total_income","Verified income",str(income),"NGN"),item("total_expenses","Expenses",str(expenses),"NGN"),item("balance","Balance",str(income-expenses),"NGN"),item("pending_receipts","Unverified donations",Donation.objects.filter(status="UNVERIFIED").count())])]})

class CommunityEngagementDashboardView(APIView):
 permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission("MOBILIZATION")]
 def get(self,request):
  return Response({"title":"Community engagement","blocks":[block("community","Community",[item("active_initiatives","Active initiatives",CommunityInitiative.objects.exclude(status="COMPLETED").count()),item("pending_reports","Pending community reports",CommunityReport.objects.exclude(status="APPROVED").count())])]})

class TierDashboardView(APIView):
 required_role=None
 permission_classes=[permissions.IsAuthenticated,IsVerifiedMember]
 def get(self,request):
  if request.user.role!=self.required_role:
   return Response({"error":{"code":"permission_denied","message":f"{self.required_role} role required.","details":None}},status=403)
  return MyDashboardView().get(request)
class ZonalDashboardView(TierDashboardView): required_role="ZONAL"
class LgaDashboardView(TierDashboardView): required_role="LGA"
class WardDashboardView(TierDashboardView): required_role="WARD"
