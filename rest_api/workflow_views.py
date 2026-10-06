from decimal import Decimal
import secrets
from datetime import timedelta
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from events.models import Event, EventAttendance, MeetingMinutes
from staff.models import User, WardMeeting, WomensProgram, YouthProgram, WelfareProgram, DisciplinaryAction
from donations.models import Donation, Expense
from core.models import Notification
from telegram_integration.models import TelegramAuthState, TelegramMembership
from .models import DeviceRegistration
from .permissions import IsVerifiedMember, capability_permission
from .serializers import (EventSerializer,AttendanceRecordSerializer,MeetingMinutesSerializer,WardMeetingSerializer,
 WomensProgramSerializer,YouthProgramSerializer,WelfareProgramSerializer,DonationSerializer,ExpenseSerializer,
 DisciplineSerializer,NotificationSerializer,DeviceRegistrationSerializer,TelegramMembershipSerializer)

AUTH=[permissions.IsAuthenticated,IsVerifiedMember]

def scoped_users(user):
    qs=User.objects.filter(status='VERIFIED',is_superuser=False)
    if user.role=='STATE': return qs
    if user.role=='ZONAL': return qs.filter(zone=user.zone)
    if user.role=='LGA': return qs.filter(lga=user.lga)
    if user.role=='WARD': return qs.filter(ward=user.ward)
    return qs.filter(pk=user.pk)

def scoped_programs(model,user):
    qs=model.objects.all()
    if user.role=='STATE': return qs
    if user.role=='ZONAL': return qs.filter(Q(zone=user.zone)|Q(zone__isnull=True,lga__isnull=True))
    if user.role=='LGA': return qs.filter(Q(lga=user.lga)|Q(zone=user.lga.zone,lga__isnull=True)|Q(zone__isnull=True,lga__isnull=True))
    return qs.none()

class EventListCreateView(generics.ListCreateAPIView):
    serializer_class=EventSerializer
    def get_permissions(self):
        required='MANAGE_EVENTS' if self.request.method=='POST' else 'VIEW_EVENTS'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]
    def get_queryset(self): return Event.objects.select_related('created_by').all()
    def perform_create(self,s): s.save(created_by=self.request.user)

class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class=EventSerializer
    queryset=Event.objects.all()
    def get_permissions(self):
        required='VIEW_EVENTS' if self.request.method=='GET' else 'MANAGE_EVENTS'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]

class EventAttendanceView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('RECORD_ATTENDANCE')]
    def get_event(self,pk):
        try:return Event.objects.get(pk=pk)
        except Event.DoesNotExist:raise NotFound('Event not found.')
    def get(self,request,pk):
        return Response(AttendanceRecordSerializer(self.get_event(pk).attendances.all(),many=True).data)
    @transaction.atomic
    def put(self,request,pk):
        event=self.get_event(pk); records=request.data.get('records')
        if not isinstance(records,list): raise ValidationError({'records':'A list is required.'})
        allowed=set(scoped_users(request.user).values_list('id',flat=True)); output=[]
        for item in records:
            sid=AttendanceRecordSerializer(data=item); sid.is_valid(raise_exception=True)
            attendee=sid.validated_data['attendee']
            if attendee.pk not in allowed: raise PermissionDenied('Attendee is outside your jurisdiction.')
            row,_=EventAttendance.objects.update_or_create(event=event,attendee=attendee,defaults={
                'present':sid.validated_data.get('present',False),'notes':sid.validated_data.get('notes',''),'recorded_by':request.user})
            output.append(row)
        return Response(AttendanceRecordSerializer(output,many=True).data)

class EventMinutesView(APIView):
    def get_permissions(self):
        required='EDIT_MINUTES' if self.request.method=='PUT' else 'VIEW_EVENTS'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]
    def get_event(self,pk):
        try:return Event.objects.get(pk=pk)
        except Event.DoesNotExist:raise NotFound('Event not found.')
    def get(self,request,pk):
        event=self.get_event(pk)
        try: obj=event.minutes
        except MeetingMinutes.DoesNotExist: raise NotFound('Meeting minutes have not been recorded.')
        return Response(MeetingMinutesSerializer(obj).data)
    @transaction.atomic
    def put(self,request,pk):
        event=self.get_event(pk)
        obj=MeetingMinutes.objects.filter(event=event).first()
        serializer=MeetingMinutesSerializer(obj,data=request.data,partial=False); serializer.is_valid(raise_exception=True)
        attendees=serializer.validated_data.pop('attendees_present',[])
        allowed=set(scoped_users(request.user).values_list('id',flat=True))
        if any(u.pk not in allowed for u in attendees): raise PermissionDenied('An attendee is outside your jurisdiction.')
        obj=serializer.save(event=event,recorded_by=request.user)
        obj.attendees_present.set(attendees)
        if obj.is_published and not obj.published_at: obj.published_at=timezone.now(); obj.save(update_fields=['published_at'])
        return Response(MeetingMinutesSerializer(obj).data)

class WardMeetingListCreateView(generics.ListCreateAPIView):
    serializer_class=WardMeetingSerializer
    def get_permissions(self):
        required='MANAGE_WARD_MEETINGS' if self.request.method=='POST' else 'VIEW_WARD_MEETINGS'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]
    def get_queryset(self):
        return WardMeeting.objects.filter(ward=self.request.user.ward) if self.request.user.ward_id else WardMeeting.objects.none()
    def perform_create(self,s):
        if not self.request.user.ward_id: raise ValidationError({'ward':'Your profile has no Ward jurisdiction.'})
        s.save(ward=self.request.user.ward,created_by=self.request.user)

PROGRAMS={'women':(WomensProgram,WomensProgramSerializer,'MANAGE_PROGRAMS_WOMEN'),
          'youth':(YouthProgram,YouthProgramSerializer,'MANAGE_PROGRAMS_YOUTH'),
          'welfare':(WelfareProgram,WelfareProgramSerializer,'MANAGE_PROGRAMS_WELFARE')}
class ProgramListCreateView(generics.ListCreateAPIView):
    def config(self):
        try:return PROGRAMS[self.kwargs.get('kind','women')]
        except KeyError: raise NotFound('Unknown program kind.')
    def get_serializer_class(self): return self.config()[1]
    def get_permissions(self): return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(self.config()[2])]]
    def get_queryset(self): return scoped_programs(self.config()[0],self.request.user)
    def perform_create(self,s):
        values={'created_by':self.request.user}
        if self.request.user.role=='ZONAL': values['zone']=self.request.user.zone
        elif self.request.user.role=='LGA': values.update(zone=self.request.user.lga.zone,lga=self.request.user.lga)
        s.save(**values)

class FinanceSummaryView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('VIEW_FINANCE')]
    def get(self,request):
        income=Donation.objects.filter(status='RECORDED').aggregate(v=Sum('amount'))['v'] or Decimal('0')
        expenses=Expense.objects.aggregate(v=Sum('amount'))['v'] or Decimal('0')
        return Response({'scope':'STATE','total_income':str(income),'total_expenses':str(expenses),
                         'balance':str(income-expenses),'pending_donations':Donation.objects.filter(status='UNVERIFIED').count()})

class DonationListCreateView(generics.ListCreateAPIView):
    serializer_class=DonationSerializer
    queryset=Donation.objects.all()
    def get_permissions(self):
        required='RECORD_DONATION' if self.request.method=='POST' else 'VIEW_FINANCE'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]

class ExpenseListCreateView(generics.ListCreateAPIView):
    serializer_class=ExpenseSerializer
    queryset=Expense.objects.all()
    def get_permissions(self):
        required='RECORD_EXPENSE' if self.request.method=='POST' else 'VIEW_FINANCE'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]
    def perform_create(self,s): s.save(recorded_by=self.request.user)

class DisciplineListCreateView(generics.ListCreateAPIView):
    serializer_class=DisciplineSerializer
    def get_permissions(self):
        required='CREATE_DISCIPLINE' if self.request.method=='POST' else 'VIEW_DISCIPLINE'
        return [p() for p in [permissions.IsAuthenticated,IsVerifiedMember,capability_permission(required)]]
    def get_queryset(self): return DisciplinaryAction.objects.filter(user__is_superuser=False).select_related('user')
    def perform_create(self,s):
        target=s.validated_data['user']
        if target.is_superuser: raise ValidationError({'user':'Website administrators cannot be subject to this workflow.'})
        warning=s.validated_data['action_type']=='WARNING'
        s.save(issued_by=self.request.user,is_approved=warning,approved_by=self.request.user if warning else None)

class DisciplineDecisionView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('DECIDE_DISCIPLINE')]
    @transaction.atomic
    def post(self,request,pk):
        try: action=DisciplinaryAction.objects.select_for_update().select_related('user').get(pk=pk,user__is_superuser=False)
        except DisciplinaryAction.DoesNotExist: raise NotFound('Disciplinary action not found.')
        decision=request.data.get('decision','').upper()
        if decision not in {'APPROVE','REJECT'}: raise ValidationError({'decision':'Use APPROVE or REJECT.'})
        if action.is_approved: raise ValidationError({'decision':'This action is already approved.'})
        if decision=='REJECT': action.delete(); return Response(status=status.HTTP_204_NO_CONTENT)
        if action.action_type=='DISMISSAL' and (not action.legal_reviewed_by_id or not action.legal_approved):
            raise ValidationError({'decision':'A favorable legal opinion is required before dismissal approval.'})
        action.is_approved=True; action.approved_by=request.user; action.save(update_fields=['is_approved','approved_by'])
        if action.action_type=='SUSPENSION': action.user.status='SUSPENDED'; action.user.save(update_fields=['status'])
        elif action.action_type=='DISMISSAL':
            # Dismissal remains the disciplinary outcome. The account uses valid membership state plus inactive login.
            action.user.status='SUSPENDED'; action.user.is_active=False; action.user.save(update_fields=['status','is_active'])
        return Response(DisciplineSerializer(action).data)

class NotificationListView(generics.ListAPIView):
    serializer_class=NotificationSerializer
    permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Notification.objects.filter(user=self.request.user)
class NotificationReadView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request,pk):
        updated=Notification.objects.filter(pk=pk,user=request.user).update(is_read=True)
        if not updated: raise NotFound('Notification not found.')
        return Response(status=status.HTTP_204_NO_CONTENT)
class NotificationReadAllView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request): Notification.objects.filter(user=request.user,is_read=False).update(is_read=True); return Response(status=status.HTTP_204_NO_CONTENT)

class DeviceListCreateView(generics.ListCreateAPIView):
    serializer_class=DeviceRegistrationSerializer
    permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return DeviceRegistration.objects.filter(user=self.request.user)
    @transaction.atomic
    def create(self,request,*a,**kw):
        serializer=self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True)
        token=serializer.validated_data['token']
        DeviceRegistration.objects.filter(token=token).exclude(user=request.user).update(is_active=False)
        obj,_=DeviceRegistration.objects.update_or_create(user=request.user,token=token,defaults={
            'device_id':serializer.validated_data.get('device_id',''),'platform':serializer.validated_data.get('platform','ANDROID'),
            'app_version':serializer.validated_data.get('app_version',''),'is_active':serializer.validated_data.get('is_active',True)})
        return Response(self.get_serializer(obj).data,status=status.HTTP_200_OK)
class DeviceDetailView(generics.DestroyAPIView):
    serializer_class=DeviceRegistrationSerializer
    permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return DeviceRegistration.objects.filter(user=self.request.user)
class DeviceDeactivateView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request):
        token=request.data.get('token')
        if not token: raise ValidationError({'token':'This field is required.'})
        DeviceRegistration.objects.filter(user=request.user,token=token).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)

class TelegramStatusView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def get(self,request):
        try: data=TelegramMembershipSerializer(request.user.telegram_membership).data
        except TelegramMembership.DoesNotExist: data=None
        return Response({'connected':data is not None,'membership':data})
class TelegramLinkView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request):
        expires=timezone.now()+timedelta(minutes=10)
        state=TelegramAuthState.objects.create(state_token=secrets.token_urlsafe(32),user=request.user,expires_at=expires)
        # The API returns the existing website connection surface with a one-time state for future callback validation.
        bot=getattr(settings,'TELEGRAM_BOT_USERNAME','KPNKebbiBot').lstrip('@')
        path=reverse('telegram_integration:connect')
        return Response({'url':f'https://t.me/{bot}?start=kpn_{state.state_token}','web_url':request.build_absolute_uri(f'{path}?state={state.state_token}'),'expires_at':expires})

from django.core.mail import send_mail
from core.models import FAQ,CommunityReport
from staff.models import Announcement,CommunityOutreach
from donations.models import FinancialReport,AuditReport
from .serializers import FAQSerializer,CommunityReportSerializer,AnnouncementSerializer,OutreachSerializer,FinancialReportSerializer,AuditReportSerializer,UserSerializer,MediaItemSerializer

class PublicAboutView(APIView):
    permission_classes=[permissions.AllowAny]
    def get(self,request): return Response({'name':'Kebbi Progressive Youth Network','short_name':'KPN','motto':'One Voice, One Change.','description':'A modern civic network, community media, advocacy, development, and opportunities platform for the people of Kebbi State.','vision':'To build a progressive, transparent, and united Kebbi State where every citizen has equal opportunities for growth, development, and meaningful participation in governance and societal advancement.','mission':'To build a strong, connected civic network across Kebbi State—a platform where our collective voice influences the future of our state. We mobilize and empower citizens through advocacy, education, and community engagement.','pillars':['KPN Media','KPN Civic','KPN Community','KPN Opportunities','KPN Advocacy']})
class PublicCodeView(APIView):
    permission_classes=[permissions.AllowAny]
    def get(self,request): return Response({'title':'Code of Conduct','source':'Article XII of the Kebbi Progressive Youth Network Constitution','sections':[{'title':'General Obligations','items':['Uphold the aims and objectives of KPN.','Conduct yourself in a manner that brings honor and respect to the organization.','Respect the constitutional hierarchy.','Promote unity and peace.','Attend statutory meetings and participate actively.']},{'title':'Disciplinary Sanctions','items':['Reprimand','Suspension','Fines / Restitution','Removal from Office','Expulsion']},{'title':'Appeals','body':'A member may appeal within 14 days of receiving official notice.'}]})
class PublicSupportView(APIView):
    permission_classes=[permissions.AllowAny]
    def get(self,request): return Response({'title':'Support KPN','bank_details':None,'bank_details_status':'UNVERIFIED','message':'Bank details are being verified. Please contact KPN before making a transfer.'})
class PublicContactView(APIView):
    permission_classes=[permissions.AllowAny]
    def get(self,request): return Response({'address':'Sani Abacha Bypass Road, Birnin Kebbi','phone':'+234 806 777 0283','email':'info@kpn.com.ng'})
    def post(self,request):
        for field in ('name','email','message'):
            if not str(request.data.get(field,'')).strip(): raise ValidationError({field:'This field is required.'})
        send_mail(f"KPN Contact Form: Message from {request.data['name']}",f"Name: {request.data['name']}\nEmail: {request.data['email']}\n\n{request.data['message']}",settings.DEFAULT_FROM_EMAIL,['info@kpn.com.ng'],fail_silently=False)
        return Response({'message':'Thank you for contacting us! We will get back to you soon.'},status=201)
class PublicFAQView(generics.ListAPIView):
    serializer_class=FAQSerializer; permission_classes=[permissions.AllowAny]
    def get_queryset(self):return FAQ.objects.filter(is_active=True)
class PublicGalleryView(generics.ListAPIView):
    serializer_class=MediaItemSerializer; permission_classes=[permissions.AllowAny]
    def get_queryset(self):
        from media.models import MediaItem
        return MediaItem.objects.filter(status='APPROVED').select_related('uploaded_by')

class CommunityReportListCreateView(generics.ListCreateAPIView):
    serializer_class=CommunityReportSerializer
    def get_permissions(self):
        if self.request.method=='POST': return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission('SUBMIT_COMMUNITY_REPORT')()]
        return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission('REVIEW_COMMUNITY_REPORTS')()]
    def get_queryset(self): return CommunityReport.objects.select_related('submitted_by','zone','lga','ward').all()
    def perform_create(self,s):
        u=self.request.user
        s.save(submitted_by=u,reporter_name=u.get_full_name(),reporter_phone=u.phone,zone=(u.zone or (u.lga.zone if u.lga_id else (u.ward.lga.zone if u.ward_id else None))))
class CommunityReportDecisionView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('REVIEW_COMMUNITY_REPORTS')]
    def post(self,request,pk):
        try: report=CommunityReport.objects.get(pk=pk)
        except CommunityReport.DoesNotExist:raise NotFound('Community report not found.')
        action=request.data.get('action'); mapping={'approve':'APPROVED','reject':'REJECTED','under_review':'UNDER_REVIEW'}
        if action not in mapping:raise ValidationError({'action':'Use approve, reject or under_review.'})
        info=request.data.get('info_status','')
        if action=='approve' and info not in dict(CommunityReport.INFO_STATUS_CHOICES):raise ValidationError({'info_status':'A valid information label is required for approval.'})
        report.status=mapping[action]; report.info_status=info if action=='approve' else report.info_status; report.internal_notes=request.data.get('internal_notes',''); report.save()
        if report.submitted_by_id:
            from core.notifications import notify
            notify(report.submitted_by,'SUCCESS' if action=='approve' else 'ACTION','Community Report Reviewed',f'Your community report is now {report.get_status_display()}.',event='COMMUNITY_REPORT_REVIEWED',target_type='community_report',target_id=report.id)
        return Response(CommunityReportSerializer(report).data)

class ReporterListView(generics.ListAPIView):
    serializer_class=UserSerializer; permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('MANAGE_REPORTERS')]
    def get_queryset(self):return User.objects.filter(status='VERIFIED').filter(Q(reporter_level__in=['COMMUNITY_REPORTER','TRUSTED_REPORTER'])|Q(is_trusted_reporter=True))
class ReporterActionView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('MANAGE_REPORTERS')]
    def post(self,request,pk,action):
        try:u=User.objects.get(pk=pk,status='VERIFIED',is_superuser=False)
        except User.DoesNotExist:raise NotFound('Member not found.')
        if action=='promote-community':u.reporter_level='COMMUNITY_REPORTER';u.is_trusted_reporter=False
        elif action=='promote-trusted':u.reporter_level='TRUSTED_REPORTER';u.is_trusted_reporter=True
        elif action=='revoke':u.reporter_level='COMMUNITY_REPORTER';u.is_trusted_reporter=False
        else:raise NotFound('Unknown reporter action.')
        u.save(update_fields=['reporter_level','is_trusted_reporter']);return Response(UserSerializer(u,context={'request':request}).data)

class AnnouncementListCreateView(generics.ListCreateAPIView):
    serializer_class=AnnouncementSerializer; permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('CREATE_ANNOUNCEMENT')]
    def get_queryset(self):
        qs=Announcement.objects.all() if self.request.user.role=='STATE' and self.request.query_params.get('mine')=='false' else Announcement.objects.filter(created_by=self.request.user)
        return qs
    def perform_create(self,s):
        obj=s.save(created_by=self.request.user)
        from core.notifications import notify_many
        users=User.objects.filter(status='VERIFIED',is_active=True)
        if obj.scope=='ZONAL':users=users.filter(zone=obj.target_zone)
        elif obj.scope=='LGA':users=users.filter(lga=obj.target_lga)
        elif obj.scope=='WARD':users=users.filter(ward=obj.target_ward)
        notify_many(users,'INFO',obj.title,obj.content,event='ANNOUNCEMENT',target_type='announcement',target_id=obj.id)
class AnnouncementDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class=AnnouncementSerializer; permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('CREATE_ANNOUNCEMENT')]
    def get_queryset(self):return Announcement.objects.filter(created_by=self.request.user)
class ReceivedAnnouncementView(generics.ListAPIView):
    serializer_class=AnnouncementSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self):return Announcement.for_user(self.request.user)

class DonationTransitionView(APIView):
    action=None; capability=None; from_status=None; to_status=None
    def get_permissions(self):return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission(self.capability)()]
    def post(self,request,pk):
        try:d=Donation.objects.get(pk=pk,status=self.from_status)
        except Donation.DoesNotExist:raise NotFound('Donation not found in the required state.')
        d.status=self.to_status
        if self.action=='verify':d.verified_by=request.user;d.verified_at=timezone.now(); fields=['status','verified_by','verified_at']
        else:d.recorded_by=request.user;d.recorded_at=timezone.now();fields=['status','recorded_by','recorded_at']
        d.save(update_fields=fields);return Response(DonationSerializer(d).data)
class DonationVerifyView(DonationTransitionView):action='verify';capability='VERIFY_DONATION';from_status='UNVERIFIED';to_status='VERIFIED'
class DonationRecordView(DonationTransitionView):action='record';capability='RECORD_EXPENSE';from_status='VERIFIED';to_status='RECORDED'
class FinancialReportListCreateView(generics.ListCreateAPIView):
    serializer_class=FinancialReportSerializer
    def get_permissions(self):
        cap='MANAGE_FINANCIAL_REPORTS' if self.request.method=='POST' else 'VIEW_FINANCE';return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission(cap)()]
    def get_queryset(self):return FinancialReport.objects.all()
    def perform_create(self,s):s.save(prepared_by=self.request.user)
class AuditReportListCreateView(generics.ListCreateAPIView):
    serializer_class=AuditReportSerializer
    def get_permissions(self):
        cap='MANAGE_AUDIT_REPORTS' if self.request.method=='POST' else 'VIEW_AUDIT_REPORTS';return [permissions.IsAuthenticated(),IsVerifiedMember(),capability_permission(cap)()]
    def get_queryset(self):return AuditReport.objects.all()
    def perform_create(self,s):s.save(submitted_by=self.request.user)
class AuditReportSubmitView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('MANAGE_AUDIT_REPORTS')]
    def post(self,request,pk):
        try:r=AuditReport.objects.get(pk=pk,submitted_by=request.user,status='DRAFT')
        except AuditReport.DoesNotExist:raise NotFound('Draft audit report not found.')
        president=User.objects.filter(status='VERIFIED',role_definition__title='President').first()
        if not president:raise ValidationError({'submitted_to':'No verified President is configured.'})
        r.status='SUBMITTED';r.submitted_to=president;r.submitted_at=timezone.now();r.save(update_fields=['status','submitted_to','submitted_at']);return Response(AuditReportSerializer(r).data)
class LegalOpinionView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('LEGAL_REVIEW')]
    def post(self,request,pk):
        try:a=DisciplinaryAction.objects.get(pk=pk,is_approved=False)
        except DisciplinaryAction.DoesNotExist:raise NotFound('Pending disciplinary action not found.')
        opinion=str(request.data.get('legal_opinion','')).strip()
        if not opinion:raise ValidationError({'legal_opinion':'This field is required.'})
        a.legal_opinion=opinion;a.legal_approved=bool(request.data.get('legal_approved'));a.legal_reviewed_by=request.user;a.legal_reviewed_at=timezone.now();a.save();return Response(DisciplineSerializer(a).data)

class OutreachListCreateView(generics.ListCreateAPIView):
    serializer_class=OutreachSerializer; permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('MANAGE_OUTREACH')]
    def get_queryset(self):return CommunityOutreach.objects.all()
    def perform_create(self,s):s.save(created_by=self.request.user)
class OutreachDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class=OutreachSerializer; queryset=CommunityOutreach.objects.all();permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission('MANAGE_OUTREACH')]

class TelegramDisconnectView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request):
        TelegramMembership.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
