from rest_framework import generics, viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from campaigns.models import Campaign
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron, CommunityReport, ImpactStory
from leadership.models import Zone, LGA, Ward, RoleDefinition
from staff.models import User
from .serializers import (
    CampaignSerializer, OpportunitySerializer, CommunityInitiativeSerializer,
    AdvocacyCampaignSerializer, PatronSerializer, ZoneSerializer, LGASerializer,
    WardSerializer, RoleDefinitionSerializer, LeaderSerializer, UserSerializer,
    RegisterSerializer, ImpactMetricsSerializer
)

class NewsroomListView(generics.ListAPIView):
    queryset = Campaign.objects.filter(status='PUBLISHED')
    serializer_class = CampaignSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class NewsroomDetailView(generics.RetrieveAPIView):
    queryset = Campaign.objects.filter(status='PUBLISHED')
    serializer_class = CampaignSerializer
    lookup_field = 'slug'
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class OpportunityListView(generics.ListAPIView):
    serializer_class = OpportunitySerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        auth=[],
        parameters=[
            OpenApiParameter(
                name="category", 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                required=False,
                enum=['SCHOLARSHIP', 'GRANT', 'FELLOWSHIP', 'JOB', 'TRAINING']
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Opportunity.objects.all()
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        return queryset

class CommunityInitiativeListView(generics.ListAPIView):
    queryset = CommunityInitiative.objects.all()
    serializer_class = CommunityInitiativeSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class CivicListView(generics.ListAPIView):
    queryset = Campaign.objects.filter(category='CIVIC', status='PUBLISHED')
    serializer_class = CampaignSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class AdvocacyListView(generics.ListAPIView):
    queryset = AdvocacyCampaign.objects.all()
    serializer_class = AdvocacyCampaignSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class LeadershipDirectoryView(generics.ListAPIView):
    serializer_class = LeaderSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return User.objects.filter(role__in=['STATE', 'ZONAL', 'LGA', 'WARD'])

class PatronListView(generics.ListAPIView):
    queryset = Patron.objects.filter(is_published=True)
    serializer_class = PatronSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class ImpactMetricsView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], responses={200: ImpactMetricsSerializer})
    def get(self, request):
        impact_communities_reached = ImpactStory.objects.filter(is_published=True).aggregate(total=Sum('communities_reached'))['total'] or 0
        
        data = {
            "verified_members": User.objects.filter(status='VERIFIED').count(),
            "trusted_reporters": User.objects.filter(is_trusted_reporter=True).count(),
            "community_reports": CommunityReport.objects.count(),
            "opportunities": Opportunity.objects.count(),
            "impact_communities_reached": impact_communities_reached,
            "active_lgas": LGA.objects.filter(user__status='VERIFIED').distinct().count(),
            "active_wards": Ward.objects.filter(user__status='VERIFIED').distinct().count(),
        }
        return Response(data)

class ZoneListView(generics.ListAPIView):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class LGAListView(generics.ListAPIView):
    serializer_class = LGASerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        auth=[],
        parameters=[
            OpenApiParameter(name="zone", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False)
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = LGA.objects.all()
        zone = self.request.query_params.get('zone')
        if zone:
            queryset = queryset.filter(zone_id=zone)
        return queryset

class WardListView(generics.ListAPIView):
    serializer_class = WardSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        auth=[],
        parameters=[
            OpenApiParameter(name="lga", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False)
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Ward.objects.all()
        lga = self.request.query_params.get('lga')
        if lga:
            queryset = queryset.filter(lga_id=lga)
        return queryset

class RoleDefinitionListView(generics.ListAPIView):
    serializer_class = RoleDefinitionSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        auth=[],
        parameters=[
            OpenApiParameter(
                name="tier", 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                required=False,
                enum=['STATE', 'ZONAL', 'LGA', 'WARD']
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = RoleDefinition.objects.all()
        tier = self.request.query_params.get('tier')
        if tier:
            queryset = queryset.filter(tier=tier)
        return queryset

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    
    @extend_schema(
        auth=[],
        responses={201: UserSerializer}
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="Authorization", 
                description="Bearer <access_token>", 
                required=True, 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.HEADER
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_object(self):
        return self.request.user
