from django.db.models import Q, Sum
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from campaigns.models import Campaign
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron, CommunityReport, ImpactStory, Report
from leadership.models import Zone, LGA, Ward, RoleDefinition
from staff.models import User, DisciplinaryAction
from .serializers import *
from .permissions import IsEditor, IsVerifiedMember
from leadership.access import role_title
class NewsroomListView(generics.ListAPIView):
 serializer_class=CampaignSerializer; permission_classes=[permissions.AllowAny]
 def get_queryset(self):
  qs=Campaign.objects.filter(status='PUBLISHED').select_related('author','lga','ward').order_by('-published_at')
  for key in ('category','verification_status','lga','ward'):
   val=self.request.query_params.get(key)
   if val: qs=qs.filter(**{key:val})
  q=self.request.query_params.get('q')
  return qs.filter(Q(title__icontains=q)|Q(subheadline__icontains=q)|Q(location__icontains=q)) if q else qs
class NewsroomDetailView(generics.RetrieveAPIView): queryset=Campaign.objects.filter(status='PUBLISHED').select_related('author','lga','ward'); serializer_class=CampaignSerializer; lookup_field='slug'; permission_classes=[permissions.AllowAny]
class OpportunityListView(generics.ListAPIView):
 serializer_class=OpportunitySerializer; permission_classes=[permissions.AllowAny]
 def get_queryset(self):
  status_param=self.request.query_params.get('status')
  qs=Opportunity.objects.all() if status_param=='all' else Opportunity.objects.filter(status__in=(status_param,) if status_param else ('OPEN','CLOSING_SOON'))
  category=self.request.query_params.get('category'); return qs.filter(category=category) if category else qs
class CommunityInitiativeListView(generics.ListAPIView): queryset=CommunityInitiative.objects.all(); serializer_class=CommunityInitiativeSerializer; permission_classes=[permissions.AllowAny]
class CivicListView(generics.ListAPIView): queryset=Campaign.objects.filter(category='CIVIC',status='PUBLISHED'); serializer_class=CampaignSerializer; permission_classes=[permissions.AllowAny]
class AdvocacyListView(generics.ListAPIView): queryset=AdvocacyCampaign.objects.all(); serializer_class=AdvocacyCampaignSerializer; permission_classes=[permissions.AllowAny]
class LeadershipDirectoryView(generics.ListAPIView):
 serializer_class=LeaderSerializer; permission_classes=[permissions.AllowAny]
 def get_queryset(self): return User.objects.filter(status='VERIFIED',role__in=('STATE','ZONAL','LGA','WARD')).select_related('role_definition','zone','lga','ward')
class PatronListView(generics.ListAPIView): queryset=Patron.objects.filter(is_published=True); serializer_class=PatronSerializer; permission_classes=[permissions.AllowAny]
class ImpactMetricsView(APIView):
 serializer_class=ImpactMetricsSerializer
 permission_classes=[permissions.AllowAny]
 def get(self,request): return Response({'verified_members':User.objects.filter(status='VERIFIED').count(),'trusted_reporters':User.objects.filter(status='VERIFIED',is_trusted_reporter=True).count(),'community_reports':CommunityReport.objects.filter(status='APPROVED').count(),'opportunities':Opportunity.objects.filter(status__in=('OPEN','CLOSING_SOON')).count(),'impact_communities_reached':ImpactStory.objects.filter(is_published=True).aggregate(v=Sum('communities_reached'))['v'] or 0,'active_lgas':LGA.objects.filter(members__status='VERIFIED').distinct().count(),'active_wards':Ward.objects.filter(members__status='VERIFIED').distinct().count()})
class ZoneListView(generics.ListAPIView): queryset=Zone.objects.all(); serializer_class=ZoneSerializer; permission_classes=[permissions.AllowAny]
class LGAListView(generics.ListAPIView):
 serializer_class=LGASerializer; permission_classes=[permissions.AllowAny]
 def get_queryset(self):
  qs=LGA.objects.all(); z=self.request.query_params.get('zone'); return qs.filter(zone_id=z) if z else qs
class WardListView(generics.ListAPIView):
 serializer_class=WardSerializer; permission_classes=[permissions.AllowAny]
 def get_queryset(self):
  qs=Ward.objects.all(); l=self.request.query_params.get('lga'); return qs.filter(lga_id=l) if l else qs
class RoleDefinitionListView(generics.ListAPIView):
 serializer_class=RoleDefinitionSerializer; permission_classes=[permissions.AllowAny]
 def get_queryset(self):
  qs=RoleDefinition.objects.all(); tier=self.request.query_params.get('tier'); return qs.filter(tier=tier) if tier else qs
class RegisterView(generics.CreateAPIView):
 """Leadership-position application only. General-member self-registration remains intentionally unavailable."""
 serializer_class=RegisterSerializer; permission_classes=[permissions.AllowAny]
class MeView(generics.RetrieveAPIView):
 serializer_class=UserSerializer; permission_classes=[permissions.IsAuthenticated]
 def get_object(self): return self.request.user
class MediaPipelineView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsEditor]
 def get(self,request): return Response({'pending_review':Campaign.objects.filter(status='PENDING').count(),'published_news':Campaign.objects.filter(status='PUBLISHED').count(),'pending_media':__import__('media.models',fromlist=['MediaItem']).MediaItem.objects.filter(status='PENDING').count(),'trusted_reporters':User.objects.filter(status='VERIFIED',is_trusted_reporter=True).count()})
class VPOversightView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsVerifiedMember]
 def get(self,request):
  if role_title(request.user) not in ('President','Vice President'): raise PermissionDenied('Executive oversight permission required.')
  return Response({'zonal_leaders':User.objects.filter(role='ZONAL',status='VERIFIED').count(),'lga_leaders':User.objects.filter(role='LGA',status='VERIFIED').count(),'disciplinary_cases':DisciplinaryAction.objects.filter(is_approved=False).count(),'operational_reports':Report.objects.count()})
