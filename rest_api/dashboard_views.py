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


def item(key,label,value,currency=None):
 data={"key":key,"label":label,"value":value}
 if currency: data["currency"]=currency
 return data

def block(key,title,items,kind="metrics"):
 return {"key":key,"type":kind,"title":title,"available":True,"items":items}

def unavailable(key,title,reason):
 return {"key":key,"type":"unavailable","title":title,"available":False,"reason":reason,"items":[]}

def scoped_users(user): return users_in_jurisdiction(user,User.objects.all())
def scoped_reports(user): return Report.objects.filter(submitted_by__in=scoped_users(user))

def access_denied_response(user):
 access=check_dashboard_access(user)
 if access["allowed"]: return None
 return Response({"error":{"code":access["reason"],"message":"Dashboard access is not currently available.","details":{"telegram_required":access["telegram_required"]}}},status=status.HTTP_403_FORBIDDEN)

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
  return Response({"title":title,"blocks":blocks})

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
