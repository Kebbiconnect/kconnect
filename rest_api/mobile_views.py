"""Additive native-mobile endpoints. Website views, models, and migrations are unchanged."""
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import generics, permissions, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError, MethodNotAllowed
from leadership.capabilities import capabilities_for
from leadership.access import users_in_jurisdiction, role_title
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron, FAQ, Notification
from staff.models import User, WardMeeting, WardMeetingAttendance
from .permissions import IsVerifiedMember, capability_permission
from .serializers import OpportunitySerializer, CommunityInitiativeSerializer, AdvocacyCampaignSerializer, PatronSerializer, FAQSerializer, WardMeetingSerializer, AttendanceRecordSerializer, EventSerializer
from .workflow_views import PROGRAMS, scoped_programs, programme_creation_scope
from .serializers import DonationSerializer,ExpenseSerializer,FinancialReportSerializer,AuditReportSerializer,OutreachSerializer
from donations.models import Donation,Expense,FinancialReport,AuditReport
from events.models import Event
from staff.models import CommunityOutreach

class MobileHomeView(APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request):
        # Exact text from core/templates/core/home.html, exposed for native presentation.
        return Response({"organization":"Kebbi Progressive Youth Network","motto":"One Voice, One Change.","introduction":"Connecting communities, amplifying civic voices, sharing opportunities, and promoting positive development across Kebbi State.","pillars":[
            {"title":"Media & Information","body":"Verified grassroots reporting, breaking news, and combating misinformation.","route":"news"},
            {"title":"Community Development","body":"Interventions, welfare programs, and driving localized positive change.","route":"community"},
            {"title":"Youth Empowerment","body":"Mentorship, leadership training, and skill acquisition for the next generation.","route":"opportunities"},
            {"title":"Opportunities Hub","body":"Connecting youth to jobs, grants, scholarships, and training programs.","route":"opportunities"},
            {"title":"Civic Engagement","body":"Voter education, grassroots mobilization, and policy advocacy.","route":"civic"}
        ]})

class PublicLeaderDetailView(APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk, status='VERIFIED', is_active=True, is_superuser=False, role__in=['STATE','ZONAL','LGA','WARD'])
        return Response({'id':user.id,'name':user.get_full_name() or user.username,'role_title':role_title(user),'tier':user.role,'jurisdiction':user.get_jurisdiction(),'bio':user.bio,'photo':request.build_absolute_uri(user.photo.url) if user.photo else None})

class NotificationSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        return Response({'unread_count':Notification.objects.filter(user=request.user,is_read=False).count()})
class NotificationStateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk):
        state = serializers.BooleanField().run_validation(request.data.get('is_read'))
        row = get_object_or_404(Notification, pk=pk, user=request.user)
        row.is_read=state; row.save(update_fields=['is_read'])
        return Response({'id':row.id,'is_read':row.is_read})

# Only resources with existing website forms and existing role capabilities are exposed.
RESOURCE_CONFIG = {
    'opportunities':(Opportunity,OpportunitySerializer,'MANAGE_HUBS','Opportunities'),
    'community':(CommunityInitiative,CommunityInitiativeSerializer,'MANAGE_HUBS','Community initiatives'),
    'advocacy':(AdvocacyCampaign,AdvocacyCampaignSerializer,'MANAGE_HUBS','Advocacy campaigns'),
    'patrons':(Patron,PatronSerializer,'MANAGE_PATRONS','Patrons'),
    'faq':(FAQ,FAQSerializer,'MANAGE_FAQ','Frequently asked questions'),
    'donations':(Donation,DonationSerializer,'RECORD_DONATION','Donation records'),
    'expenses':(Expense,ExpenseSerializer,'RECORD_EXPENSE','Expense records'),
    'financial-reports':(FinancialReport,FinancialReportSerializer,'MANAGE_FINANCIAL_REPORTS','Financial reports'),
    'audit-reports':(AuditReport,AuditReportSerializer,'MANAGE_AUDIT_REPORTS','Audit reports'),
    'outreach':(CommunityOutreach,OutreachSerializer,'MANAGE_OUTREACH','Partnerships and outreach'),
    'events':(Event,EventSerializer,'MANAGE_EVENTS','Events and meetings'),
    'ward-meetings':(WardMeeting,WardMeetingSerializer,'MANAGE_WARD_MEETINGS','Ward meetings and minutes'),
}
for kind,(model,serializer,cap) in PROGRAMS.items():
    RESOURCE_CONFIG["programs_"+kind]=(model,serializer,cap,kind.title()+" programmes")

def resource_config(kind):
    try:return RESOURCE_CONFIG[kind]
    except KeyError:raise NotFound('Unknown management resource.')
CREATE_ONLY_RESOURCES={'donations','expenses','financial-reports'}
NO_DELETE_RESOURCES=CREATE_ONLY_RESOURCES|{'audit-reports'}
class ResourceCatalogView(APIView):
    permission_classes = [permissions.IsAuthenticated,IsVerifiedMember]
    def get(self,request):
        caps=set(capabilities_for(request.user)); resources=[]
        for kind,(model,serializer,cap,title) in RESOURCE_CONFIG.items():
            if cap not in caps:continue
            fields=[]
            for name,field in serializer().fields.items():
                if field.read_only or kind=="audit-reports" and name=="review_notes":continue
                model_name=field.source if field.source not in (None,'*') else name
                try:
                    mf=model._meta.get_field(model_name); default=mf.get_default() if mf.has_default() and not callable(mf.default) else None
                except Exception:default=None
                fields.append({'default_value':str(default).lower() if isinstance(default,bool) else str(default) if default is not None else None,'name':name,'label':field.label or name.replace('_',' ').title(),'required':field.required,'type':'choice' if getattr(field,'choices',None) else 'image' if isinstance(field,serializers.ImageField) else 'file' if isinstance(field,serializers.FileField) else 'boolean' if isinstance(field,serializers.BooleanField) else 'integer' if isinstance(field,serializers.IntegerField) else 'datetime' if isinstance(field,serializers.DateTimeField) else 'time' if isinstance(field,serializers.TimeField) else 'date' if isinstance(field,serializers.DateField) else 'number' if isinstance(field,(serializers.DecimalField,serializers.FloatField)) else 'email' if isinstance(field,serializers.EmailField) else 'url' if isinstance(field,serializers.URLField) else 'text','choices':[{'value':str(k),'label':str(v)} for k,v in getattr(field,'choices',{}).items()]})
            resources.append({'kind':kind,'title':title,'fields':fields,'can_edit':kind not in CREATE_ONLY_RESOURCES,'can_delete':kind not in NO_DELETE_RESOURCES})
        return Response({'resources':resources})
class ResourceListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission(resource_config(self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind'])[2])()]
    def get_serializer_class(self):return resource_config(self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind'])[1]
    def get_queryset(self):
        if getattr(self,'swagger_fake_view',False):return FAQ.objects.none()
        kind=self.kwargs['kind']; model=resource_config(kind)[0]
        qs=scoped_programs(model,self.request.user) if kind.startswith('programs_') else model.objects.all()
        if kind=='audit-reports':qs=qs.filter(submitted_by=self.request.user)
        if kind=='ward-meetings':qs=qs.filter(ward_id=self.request.user.ward_id) if self.request.user.ward_id else qs.none()
        return qs.order_by('-pk')
    def perform_create(self,s):
        kind=self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind']; fields={}
        owner={'expenses':'recorded_by','financial-reports':'prepared_by','audit-reports':'submitted_by','outreach':'created_by','events':'created_by','ward-meetings':'created_by'}
        if kind in owner:fields[owner[kind]]=self.request.user
        if kind=='ward-meetings':
            if not self.request.user.ward_id:raise ValidationError({'ward':'Your profile has no Ward jurisdiction.'})
            fields['ward']=self.request.user.ward
        if kind.startswith('programs_'):
            fields.update(programme_creation_scope(self.request.user))
        if kind=="audit-reports":fields["review_notes"]=""
        s.save(**fields)
class ResourceDetailView(ResourceListCreateView,generics.RetrieveUpdateDestroyAPIView):
    http_method_names=["get","put","patch","delete","head","options"]
    def get_permissions(self):return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission(resource_config(self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind'])[2])()]
    def get_serializer_class(self):return resource_config(self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind'])[1]
    def get(self,request,*args,**kwargs):return self.retrieve(request,*args,**kwargs)
    def update(self,request,*args,**kwargs):
        kind=self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind']
        if kind in CREATE_ONLY_RESOURCES:raise MethodNotAllowed(request.method)
        if kind=='audit-reports' and self.get_object().status!='DRAFT':raise PermissionDenied('Only your draft audit reports can be edited.')
        if kind=='audit-reports' and 'review_notes' in request.data:raise PermissionDenied('Audit authors cannot change reviewer notes.')
        return super().update(request,*args,**kwargs)
    def destroy(self,request,*args,**kwargs):
        if self.kwargs.get('kind','faq') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind'] in NO_DELETE_RESOURCES:raise MethodNotAllowed('DELETE')
        return super().destroy(request,*args,**kwargs)

class ProgramDetailView(generics.RetrieveUpdateDestroyAPIView):
    def config(self):
        try:return PROGRAMS[self.kwargs.get('kind','women') if getattr(self,'swagger_fake_view',False) else self.kwargs['kind']]
        except KeyError:raise NotFound('Unknown programme kind.')
    def get_permissions(self):return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission(self.config()[2])()]
    def get_serializer_class(self):return self.config()[1]
    def get_queryset(self):return self.config()[0].objects.none() if getattr(self,'swagger_fake_view',False) else scoped_programs(self.config()[0],self.request.user)
class ProgramParticipantsView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember]
    def config(self,kind):
        try:return PROGRAMS[kind]
        except KeyError:raise NotFound('Unknown programme kind.')
    def permissions_check(self,request,kind):
        if not IsVerifiedMember().has_permission(request,self) or not {self.config(kind)[2],"MANAGE_PROGRAM_PARTICIPANTS"}.issubset(set(capabilities_for(request.user))):raise PermissionDenied('Your role cannot manage this programme.')
    def get(self,request,kind,pk):
        self.permissions_check(request,kind)
        obj=get_object_or_404(scoped_programs(self.config(kind)[0],request.user),pk=pk)
        relation=obj.beneficiaries if kind=='welfare' else obj.participants
        return Response({'members':list(relation.values_list('pk',flat=True))})
    @transaction.atomic
    def put(self,request,kind,pk):
        self.permissions_check(request,kind)
        obj=get_object_or_404(scoped_programs(self.config(kind)[0],request.user),pk=pk)
        ids=serializers.ListField(child=serializers.IntegerField(min_value=1)).run_validation(request.data.get('members'))
        allowed=users_in_jurisdiction(request.user,User.objects.filter(status='VERIFIED',is_superuser=False))
        if len(set(ids))!=allowed.filter(pk__in=ids).count():raise PermissionDenied('A participant is outside your jurisdiction.')
        relation=obj.beneficiaries if kind=='welfare' else obj.participants
        relation.set(ids)
        return Response({'members':list(relation.values_list('pk',flat=True))})

class WardMeetingDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class=WardMeetingSerializer
    def get_permissions(self):return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission('VIEW_WARD_MEETINGS' if self.request.method=='GET' else 'MANAGE_WARD_MEETINGS')()]
    def get_queryset(self):return WardMeeting.objects.none() if getattr(self,'swagger_fake_view',False) else WardMeeting.objects.filter(ward_id=self.request.user.ward_id) if self.request.user.ward_id else WardMeeting.objects.none()
class WardAttendanceView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('MANAGE_WARD_ATTENDANCE')]
    def get_meeting(self,request,pk):return get_object_or_404(WardMeeting,pk=pk,ward_id=request.user.ward_id)
    def get(self,request,pk):
        rows=self.get_meeting(request,pk).attendance_records.all()
        return Response([{'attendee':r.member_id,'present':r.present,'notes':r.notes} for r in rows])
    @transaction.atomic
    def put(self,request,pk):
        meeting=self.get_meeting(request,pk)
        data=AttendanceRecordSerializer(data=request.data.get('records'),many=True);data.is_valid(raise_exception=True)
        for item in data.validated_data:
            if item['attendee'].ward_id!=meeting.ward_id or item['attendee'].status!='VERIFIED':raise PermissionDenied('Member is outside this ward.')
            WardMeetingAttendance.objects.update_or_create(meeting=meeting,member=item['attendee'],defaults={'present':item.get('present',False),'notes':item.get('notes',''),'recorded_by':request.user})
        return self.get(request,pk)

class ArticleBodyImageView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('WRITE_ARTICLES')]
    def post(self,request):
        from django.core.files.storage import default_storage
        from PIL import Image
        from pathlib import Path
        import uuid
        image=request.FILES.get('image')
        if not image:raise ValidationError({'image':'Choose an image.'})
        if image.size>2*1024*1024:raise ValidationError({'image':'Article body images must be at most 2 MB.'})
        extension=Path(image.name).suffix.lower()
        if extension not in {'.jpg','.jpeg','.png','.gif','.webp'}:raise ValidationError({'image':'Use JPG, PNG, GIF or WebP.'})
        try:
            decoded=Image.open(image)
            if max(decoded.size)>4000 or decoded.format.lower() not in {'jpeg','png','gif','webp'}:raise ValueError('Unsupported image dimensions or format.')
            decoded.verify()
        except Exception:raise ValidationError({'image':'Use a valid image no larger than 4000×4000 pixels.'})
        image.seek(0)
        name=default_storage.save('kpn_newsroom/'+uuid.uuid4().hex+extension,image)
        return Response({'url':request.build_absolute_uri(default_storage.url(name))},status=201)
