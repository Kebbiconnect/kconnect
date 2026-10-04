from django.db.models import Sum
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from staff.models import User, DisciplinaryAction, WardMeeting
from campaigns.models import Campaign
from core.models import Report, CommunityInitiative, CommunityReport
from leadership.models import LGA, Ward
from donations.models import Donation, Expense
from events.models import Event, MeetingMinutes
from .serializers import GenericObjectSerializer
from .permissions import IsStateExecutive, IsZonalExecutive, IsLgaExecutive, IsWardExecutive, IsVerifiedMember
from leadership.access import role_title

class SecretariatDashboardView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsStateExecutive]
 def get(self,request):
  if role_title(request.user) not in ('President','Vice President','General Secretary','Assistant General Secretary'): from rest_framework.exceptions import PermissionDenied; raise PermissionDenied('Secretariat permission required.')
  return Response({'verified_members':User.objects.filter(status='VERIFIED',is_superuser=False).count(),'pending_members':User.objects.filter(status__in=('PENDING','UNDER_REVIEW'),is_superuser=False).count(),'upcoming_events':Event.objects.filter(start_date__gte=timezone.now()).count(),'published_minutes':MeetingMinutes.objects.filter(is_published=True).count(),'pending_reports':Report.objects.filter(status='SUBMITTED').count()})
class FinanceDashboardView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsStateExecutive]
 def get(self,request):
  from rest_framework.exceptions import PermissionDenied
  if role_title(request.user) not in ('President','Director of Finance','Finance Operations Officer','Director of Audit & Accountability'): raise PermissionDenied('State finance permission required.')
  income=Donation.objects.filter(status__in=('VERIFIED','RECORDED')).aggregate(v=Sum('amount'))['v'] or 0; exp=Expense.objects.aggregate(v=Sum('amount'))['v'] or 0
  return Response({'scope':'STATE','total_income':income,'total_expenses':exp,'balance':income-exp,'pending_receipts':Donation.objects.filter(status='UNVERIFIED').count()})
class CommunityEngagementDashboardView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsStateExecutive]
 def get(self,request): return Response({'active_initiatives':CommunityInitiative.objects.filter(status='ACTIVE').count(),'pending_community_reports':CommunityReport.objects.filter(status='PENDING').count()})
class ZonalDashboardView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsZonalExecutive]
 def get(self,request):
  z=request.user.zone
  return Response({'zone_name':z.name,'lgas_in_zone':LGA.objects.filter(zone=z).count(),'verified_members':User.objects.filter(zone=z,status='VERIFIED').count(),'pending_members':User.objects.filter(zone=z,status__in=('PENDING','UNDER_REVIEW')).count(),'pending_reports':Report.objects.filter(submitted_to=request.user,status='SUBMITTED').count()})
class LgaDashboardView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsLgaExecutive]
 def get(self,request):
  l=request.user.lga
  return Response({'lga_name':l.name,'verified_members':User.objects.filter(lga=l,status='VERIFIED').count(),'wards':Ward.objects.filter(lga=l).count(),'pending_members':User.objects.filter(lga=l,status__in=('PENDING','UNDER_REVIEW')).count(),'pending_reports':Report.objects.filter(submitted_to=request.user,status='SUBMITTED').count(),'finance_available':False})
class WardDashboardView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsWardExecutive]
 def get(self,request):
  w=request.user.ward
  return Response({'ward_name':w.name,'verified_members':User.objects.filter(ward=w,status='VERIFIED').count(),'pending_members':User.objects.filter(ward=w,status__in=('PENDING','UNDER_REVIEW')).count(),'meetings':WardMeeting.objects.filter(ward=w).count(),'reports_submitted':Report.objects.filter(submitted_by=request.user).count(),'finance_available':False})
