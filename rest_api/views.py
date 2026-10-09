from rest_framework import generics, viewsets, permissions
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from campaigns.models import Campaign
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron, CommunityReport, ImpactStory
from leadership.models import Zone, LGA, Ward, RoleDefinition
from staff.models import User
from .permissions import IsVerifiedMember, capability_permission, any_capability_permission
from .serializers import (
    CampaignSerializer, OpportunitySerializer, CommunityInitiativeSerializer,
    AdvocacyCampaignSerializer, PatronSerializer, ZoneSerializer, LGASerializer,
    WardSerializer, RoleDefinitionSerializer, LeaderSerializer, UserSerializer,
    RegisterSerializer, ImpactMetricsSerializer, ProfileSerializer, LeadershipSeatSerializer, MemberSerializer, ReportSerializer, ReportCreateSerializer, ArticleWriteSerializer, MediaItemSerializer
)

class NewsroomListView(generics.ListAPIView):
    serializer_class = CampaignSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    def get_queryset(self):
        queryset = Campaign.objects.filter(status='PUBLISHED').select_related('author','lga','ward')
        category = self.request.query_params.get('category')
        lga = self.request.query_params.get('lga')
        verification = self.request.query_params.get('status')
        search = self.request.query_params.get('q','').strip()
        if category: queryset = queryset.filter(category=category)
        if lga: queryset = queryset.filter(lga_id=lga)
        if verification: queryset = queryset.filter(verification_status=verification)
        if search: queryset = queryset.filter(Q(title__icontains=search)|Q(subheadline__icontains=search)|Q(location__icontains=search))
        return queryset.order_by('-published_at','-created_at')

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
        requested_status = self.request.query_params.get('status')
        queryset = Opportunity.objects.all() if requested_status == 'all' else Opportunity.objects.filter(status__in=['OPEN','CLOSING_SOON'])
        if requested_status and requested_status != 'all': queryset = queryset.filter(status=requested_status)
        category = self.request.query_params.get('category')
        if category: queryset = queryset.filter(category=category)
        return queryset.order_by('-is_featured','-created_at')

class CommunityInitiativeListView(generics.ListAPIView):
    queryset = CommunityInitiative.objects.all()
    serializer_class = CommunityInitiativeSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class OpportunityDetailView(generics.RetrieveAPIView):
    queryset = Opportunity.objects.all()
    serializer_class = OpportunitySerializer
    lookup_field = 'slug'
    permission_classes = [permissions.AllowAny]

class CommunityInitiativeDetailView(generics.RetrieveAPIView):
    queryset = CommunityInitiative.objects.all()
    serializer_class = CommunityInitiativeSerializer
    permission_classes = [permissions.AllowAny]

class AdvocacyDetailView(generics.RetrieveAPIView):
    queryset = AdvocacyCampaign.objects.filter(is_active=True)
    serializer_class = AdvocacyCampaignSerializer
    permission_classes = [permissions.AllowAny]

class PatronDetailView(generics.RetrieveAPIView):
    queryset = Patron.objects.filter(is_published=True)
    serializer_class = PatronSerializer
    permission_classes = [permissions.AllowAny]

class CivicListView(generics.ListAPIView):
    queryset = Campaign.objects.filter(category='CIVIC', status='PUBLISHED')
    serializer_class = CampaignSerializer
    permission_classes = [permissions.AllowAny]
    @extend_schema(auth=[])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class AdvocacyListView(generics.ListAPIView):
    queryset = AdvocacyCampaign.objects.filter(is_active=True)
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
    queryset = Patron.objects.filter(is_published=True).order_by('patron_type','order','full_name')
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
            "trusted_reporters": User.objects.filter(status='VERIFIED', is_trusted_reporter=True).count(),
            "community_reports": CommunityReport.objects.filter(status='APPROVED').count(),
            "opportunities": Opportunity.objects.filter(status__in=('OPEN', 'CLOSING_SOON')).count(),
            "impact_communities_reached": impact_communities_reached,
            "active_lgas": LGA.objects.filter(members__status='VERIFIED').distinct().count(),
            "active_wards": Ward.objects.filter(members__status='VERIFIED').distinct().count(),
            "zones_total": Zone.objects.count(),
            "lgas_total": LGA.objects.count(),
            "wards_total": Ward.objects.count(),
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Match the documented response: actual identity/status, not the write-form serializer.
        return Response(UserSerializer(user, context=self.get_serializer_context()).data, status=201)
    
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


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# =========================================================
# TRACK B: ANDROID REQUIRED API EXTENSIONS
# =========================================================

class MediaPipelineView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('REVIEW_ARTICLES')]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        pending_count = Campaign.objects.filter(status='DRAFT').count()
        published_count = Campaign.objects.filter(status='PUBLISHED').count()
        active_campaigns = Campaign.objects.filter(status='PUBLISHED', category='CIVIC').count()
        trusted_reporters = User.objects.filter(status='VERIFIED', is_trusted_reporter=True).count()
        
        return Response({
            "pending_review": pending_count,
            "published_news": published_count,
            "active_campaigns": active_campaigns,
            "trusted_reporters": trusted_reporters
        })

class VPOversightView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('VIEW_OVERSIGHT')]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        zonal_directors = User.objects.filter(role='ZONAL', status='VERIFIED').count()
        lga_coordinators = User.objects.filter(role='LGA', status='VERIFIED').count()
        
        from staff.models import DisciplinaryAction
        from core.models import Report
        return Response({
            "zonal_directors_active": zonal_directors,
            "lga_coordinators_active": lga_coordinators,
            "disciplinary_cases": DisciplinaryAction.objects.filter(is_approved=False).count(),
            "operational_reports": Report.objects.count()
        })

class LeadershipSeatListView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(auth=[], responses={200: LeadershipSeatSerializer(many=True)})
    def get(self, request):
        from django.shortcuts import get_object_or_404
        from .leadership_read_model import leadership_seats
        from rest_framework.exceptions import ValidationError
        from .pagination import StandardPagination
        from .serializers import LeadershipSeatSerializer
        tier = request.query_params.get('tier')
        seat_status = request.query_params.get('status', 'FILLED')
        if tier and tier not in {'STATE','ZONAL','LGA','WARD'}:
            raise ValidationError({'tier': 'Use STATE, ZONAL, LGA or WARD.'})
        if seat_status not in {'FILLED','VACANT','all'}:
            raise ValidationError({'status': 'Use FILLED, VACANT or all.'})
        if seat_status in {'VACANT','all'} and not tier:
            raise ValidationError({'tier': 'A tier is required when requesting vacant seats.'})
        zone = get_object_or_404(Zone, pk=request.query_params['zone']) if request.query_params.get('zone') else None
        lga = get_object_or_404(LGA.objects.select_related('zone'), pk=request.query_params['lga']) if request.query_params.get('lga') else None
        ward = get_object_or_404(Ward.objects.select_related('lga__zone'), pk=request.query_params['ward']) if request.query_params.get('ward') else None
        if lga and zone and lga.zone_id != zone.id:
            raise ValidationError({'lga': 'The selected LGA is outside the selected zone.'})
        if ward and lga and ward.lga_id != lga.id:
            raise ValidationError({'ward': 'The selected ward is outside the selected LGA.'})
        if ward and zone and ward.lga.zone_id != zone.id:
            raise ValidationError({'ward': 'The selected ward is outside the selected zone.'})
        if seat_status in {'VACANT','all'}:
            requirements = {'ZONAL': zone, 'LGA': lga, 'WARD': ward or lga}
            if tier in requirements and not requirements[tier]:
                raise ValidationError({'scope': f'{tier} vacancies require a location scope.'})
        rows = leadership_seats(tier, zone, lga, ward, seat_status, request)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(LeadershipSeatSerializer(page, many=True).data)

class RegistrationVacantRolesView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    def get(self, request):
        from django.shortcuts import get_object_or_404
        from rest_framework.exceptions import ValidationError
        from staff.services.vacancy import vacant_roles
        zone = get_object_or_404(Zone, pk=request.query_params['zone']) if request.query_params.get('zone') else None
        lga = get_object_or_404(LGA.objects.select_related('zone'), pk=request.query_params['lga']) if request.query_params.get('lga') else None
        ward = get_object_or_404(Ward.objects.select_related('lga__zone'), pk=request.query_params['ward']) if request.query_params.get('ward') else None
        if lga and zone and lga.zone_id != zone.id:
            raise ValidationError({'lga':'The selected LGA is outside the selected zone.'})
        if ward and lga and ward.lga_id != lga.id:
            raise ValidationError({'ward':'The selected ward is outside the selected LGA.'})
        if ward and zone and ward.lga.zone_id != zone.id:
            raise ValidationError({'ward':'The selected ward is outside the selected zone.'})
        roles = vacant_roles(zone=zone,lga=lga,ward=ward)
        labels={'STATE':'State Executive','ZONAL':'Senatorial Director','LGA':'LGA Network Lead','WARD':'Ward Leader'}
        tiers=[]
        for tier in ('STATE','ZONAL','LGA','WARD'):
            count=sum(role['tier']==tier for role in roles)
            if count and (tier!='WARD' or ward): tiers.append({'tier':tier,'label':labels[tier],'vacant':count})
        return Response({'vacant_roles':roles,'tiers':tiers})

class MemberListView(generics.ListAPIView):
    serializer_class = MemberSerializer
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('VIEW_MEMBERS')]
    def get_queryset(self):
        from staff.services.member_admin import members_qs
        queryset=members_qs(self.request.user)
        requested_status=self.request.query_params.get('status')
        if requested_status: queryset=queryset.filter(status=requested_status)
        gender=self.request.query_params.get('gender')
        if gender: queryset=queryset.filter(gender=gender)
        for field in ('zone','lga','ward'):
            value=self.request.query_params.get(field)
            if value:
                try:queryset=queryset.filter(**{field+'_id':int(value)})
                except (ValueError,TypeError):return queryset.none()
        tier=self.request.query_params.get('tier')
        if tier:queryset=queryset.filter(role=tier)
        query=self.request.query_params.get('search','').strip()
        if query:
            from django.db.models import Q
            queryset=queryset.filter(Q(first_name__icontains=query)|Q(last_name__icontains=query)|Q(username__icontains=query))
        return queryset

class PendingMemberListView(generics.ListAPIView):
    serializer_class = MemberSerializer
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('REVIEW_APPLICANTS')]
    def get_queryset(self):
        from staff.services.member_admin import pending_applicants_qs
        return pending_applicants_qs(self.request.user)

class MemberDetailView(generics.RetrieveAPIView):
    serializer_class = MemberSerializer
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('VIEW_MEMBERS')]
    def get_queryset(self):
        from staff.services.member_admin import members_qs
        return members_qs(self.request.user)

class MemberDecisionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('REVIEW_APPLICANTS')]
    def post(self,request,pk):
        from staff.services.member_admin import decide_application,MemberDecisionError
        try: member=decide_application(request.user,pk,request.data.get('decision'))
        except User.DoesNotExist: raise NotFound('Applicant not found.')
        except MemberDecisionError as exc:
            from rest_framework.exceptions import PermissionDenied,ValidationError
            if exc.code in {'permission_denied','outside_jurisdiction','tier_ceiling'}: raise PermissionDenied(exc.message,code=exc.code)
            raise ValidationError({'non_field_errors':[exc.message]})
        return Response(MemberSerializer(member,context={'request':request}).data)

class ReportListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, any_capability_permission('SUBMIT_REPORTS','REVIEW_REPORTS','OVERSIGHT_REPORTS')]
    def get_serializer_class(self): return ReportCreateSerializer if self.request.method=='POST' else ReportSerializer
    def get_queryset(self):
        from core.services.reports import reports_for
        queryset=reports_for(self.request.user)
        requested=self.request.query_params.get('status')
        if requested: queryset=queryset.filter(status=requested)
        return queryset
    def create(self,request,*args,**kwargs):
        from leadership.capabilities import capabilities_for
        from core.services.reports import create_report,ReportWorkflowError
        from rest_framework.exceptions import PermissionDenied,ValidationError
        if 'SUBMIT_REPORTS' not in capabilities_for(request.user): raise PermissionDenied('Your role cannot submit hierarchical reports.')
        serializer=ReportCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        try: report=create_report(request.user,**serializer.validated_data)
        except ReportWorkflowError as exc:
            if exc.code=='permission_denied': raise PermissionDenied(exc.message,code=exc.code)
            raise ValidationError({exc.field or 'non_field_errors':[exc.message]})
        return Response(ReportSerializer(report).data,status=201)

class ReportDetailView(generics.RetrieveAPIView):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, any_capability_permission('SUBMIT_REPORTS','REVIEW_REPORTS','OVERSIGHT_REPORTS')]
    def get_queryset(self):
        from core.services.reports import reports_for
        return reports_for(self.request.user)

class ReportRecipientView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, capability_permission('SUBMIT_REPORTS')]
    def get(self,request):
        from core.services.reports import recipient_for,report_type_for,ReportWorkflowError
        from rest_framework.exceptions import ValidationError
        try: recipient=recipient_for(request.user)
        except ReportWorkflowError as exc: raise ValidationError({exc.field or 'non_field_errors':[exc.message]})
        if not recipient: raise ValidationError({'submitted_to':['No verified recipient is set up for your area yet. Contact your lead.']})
        return Response({'report_type':report_type_for(request.user),'recipient':{'id':recipient.id,'name':recipient.get_full_name(),'role_title':recipient.role_definition.title if recipient.role_definition else None}})

class ReportReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, any_capability_permission('REVIEW_REPORTS','OVERSIGHT_REPORTS')]
    def post(self,request,pk):
        from core.services.reports import review_report,ReportWorkflowError
        from rest_framework.exceptions import PermissionDenied,ValidationError
        raw_action=str(request.data.get('action','')).lower()
        action={'approve':'APPROVED','approved':'APPROVED','flag':'FLAGGED','flagged':'FLAGGED','reject':'REJECTED','rejected':'REJECTED'}.get(raw_action,raw_action.upper())
        notes=request.data.get('notes','')
        try: report,child=review_report(request.user,pk,action,notes)
        except __import__('core.models',fromlist=['Report']).Report.DoesNotExist: raise NotFound('Report not found.')
        except ReportWorkflowError as exc:
            if exc.code=='permission_denied': raise PermissionDenied(exc.message,code=exc.code)
            raise ValidationError({exc.field or 'non_field_errors':[exc.message]})
        data=ReportSerializer(report).data; data['escalated_report']=ReportSerializer(child).data if child else None
        return Response(data)

class ReportEscalateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedMember, any_capability_permission('REVIEW_REPORTS','OVERSIGHT_REPORTS')]
    def post(self,request,pk):
        from core.models import Report
        from core.services.reports import reports_for,can_review,escalate_report,ReportWorkflowError
        from rest_framework.exceptions import PermissionDenied,ValidationError
        report=reports_for(request.user).filter(pk=pk).first()
        if not report: raise NotFound('Report not found.')
        if not can_review(request.user,report): raise PermissionDenied('You do not have permission to escalate this report.')
        if not report.can_be_escalated(): raise ValidationError({'non_field_errors':['Only an approved, un-escalated Ward or LGA report can be escalated.']})
        try: child=escalate_report(report,request.user)
        except ReportWorkflowError as exc: raise ValidationError({exc.field or 'non_field_errors':[exc.message]})
        return Response(ReportSerializer(child).data,status=201)

class MyArticleListCreateView(generics.ListCreateAPIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('WRITE_ARTICLES')]
    def get_serializer_class(self): return ArticleWriteSerializer if self.request.method=='POST' else CampaignSerializer
    def get_queryset(self): return Campaign.objects.filter(author=self.request.user).select_related('author','lga','ward').order_by('-updated_at')
    def perform_create(self,serializer):
        from django.utils.text import slugify
        base=slugify(serializer.validated_data['title']) or 'article'; slug=base; n=2
        while Campaign.objects.filter(slug=slug).exists(): slug=f'{base}-{n}'; n+=1
        serializer.save(author=self.request.user,slug=slug,status='DRAFT')

class MyArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class=ArticleWriteSerializer
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('WRITE_ARTICLES')]
    def get_queryset(self): return Campaign.objects.filter(author=self.request.user)
    def perform_update(self,serializer):
        article=self.get_object()
        if article.status in {'PUBLISHED','PENDING'}:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'non_field_errors':['Published or pending articles cannot be edited.']})
        serializer.save(status='DRAFT' if article.status=='REJECTED' else article.status,rejection_note='' if article.status=='REJECTED' else article.rejection_note)
    def perform_destroy(self,instance):
        if instance.status in {'PUBLISHED','PENDING'}:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'non_field_errors':['Cannot delete a published or pending article.']})
        instance.delete()

class ArticleSubmitView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('WRITE_ARTICLES')]
    def post(self,request,pk):
        from rest_framework.exceptions import ValidationError
        article=Campaign.objects.filter(pk=pk,author=request.user).first()
        if not article: raise NotFound('Article not found.')
        if article.status!='DRAFT': raise ValidationError({'non_field_errors':['Only draft articles can be submitted for review.']})
        if not article.content_json and not article.content.strip(): raise ValidationError({'content':['Article body is empty.']})
        article.status='PENDING'; article.save(update_fields=['status'])
        return Response(CampaignSerializer(article,context={'request':request}).data)

class ArticleReviewListView(generics.ListAPIView):
    queryset=Campaign.objects.filter(status='PENDING').select_related('author','lga','ward').order_by('-updated_at')
    serializer_class=CampaignSerializer
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('REVIEW_ARTICLES')]

class ArticleDecisionView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('REVIEW_ARTICLES')]
    def post(self,request,pk):
        from django.utils import timezone
        from rest_framework.exceptions import ValidationError
        article=Campaign.objects.filter(pk=pk,status='PENDING').first()
        if not article: raise NotFound('Pending article not found.')
        action=request.data.get('action'); note=str(request.data.get('note','')).strip()
        if action=='publish': article.status='PUBLISHED'; article.approved_by=request.user; article.published_at=timezone.now(); article.rejection_note=''
        elif action in {'return','reject'}:
            if not note: raise ValidationError({'note':['An editor note is required.']})
            article.status='REJECTED'; article.rejection_note=note
        else: raise ValidationError({'action':['Use publish or return.']})
        article.save(); return Response(CampaignSerializer(article,context={'request':request}).data)

class MyMediaListCreateView(generics.ListCreateAPIView):
    serializer_class=MediaItemSerializer
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('UPLOAD_MEDIA')]
    def get_queryset(self):
        from media.models import MediaItem
        return MediaItem.objects.filter(uploaded_by=self.request.user)
    def perform_create(self,serializer):
        from leadership.access import role_title
        director=role_title(self.request.user)=='Director of Media & Communications'
        serializer.save(uploaded_by=self.request.user,status='APPROVED' if director else 'PENDING',approved_by=self.request.user if director else None)

class MediaReviewListView(generics.ListAPIView):
    serializer_class=MediaItemSerializer
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('REVIEW_MEDIA')]
    def get_queryset(self):
        from media.models import MediaItem
        return MediaItem.objects.filter(status='PENDING')

class MediaDecisionView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('REVIEW_MEDIA')]
    def post(self,request,pk):
        from media.models import MediaItem
        from rest_framework.exceptions import ValidationError
        item=MediaItem.objects.filter(pk=pk,status='PENDING').first()
        if not item: raise NotFound('Pending media item not found.')
        action=request.data.get('action')
        if action=='approve': item.status='APPROVED'; item.approved_by=request.user
        elif action=='reject': item.status='REJECTED'; item.approved_by=None
        else: raise ValidationError({'action':['Use approve or reject.']})
        item.save(update_fields=['status','approved_by','updated_at']); return Response(MediaItemSerializer(item,context={'request':request}).data)
