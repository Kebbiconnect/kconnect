"""Role-aware mobile REST surface. All object access is scoped on the server."""
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from leadership.access import scope_users, require_jurisdiction, report_visible_to, role_title, can_approve_members
from leadership.roles import EDITOR_ROLES
from staff.models import User, DisciplinaryAction, WomensProgram, YouthProgram, WelfareProgram, WardMeeting, WardMeetingAttendance
from core.models import Report, Notification, DeviceRegistration, Opportunity, CommunityInitiative, AdvocacyCampaign, Patron
from campaigns.models import Campaign
from media.models import MediaItem
from events.models import Event, EventAttendance, MeetingMinutes
from donations.models import Donation, Expense, FinancialReport
from .permissions import IsVerifiedMember, IsEditor, IsPublicityOfficer, IsEventManager, IsStateExecutive
from .serializers import *
from staff.services.membership import decide_application
from core.services.reports import submit_report, review_report, escalate_report
from campaigns.services.articles import submit as submit_article, decide as decide_article

class MemberListView(generics.ListAPIView):
 serializer_class=MemberSummarySerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self):
  qs=scope_users(self.request.user).select_related('role_definition','zone','lga','ward')
  state=self.request.query_params.get('status')
  if state: qs=qs.filter(status=state)
  return qs.order_by('last_name','first_name')
class PendingApplicantsView(MemberListView):
 def get_queryset(self):
  if not can_approve_members(self.request.user): raise PermissionDenied('This role cannot review applications.')
  return scope_users(self.request.user).filter(status__in=('PENDING','UNDER_REVIEW')).select_related('role_definition','zone','lga','ward')
class MemberDetailView(generics.RetrieveAPIView):
 serializer_class=MemberSummarySerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self): return scope_users(self.request.user).select_related('role_definition','zone','lga','ward')
class ApplicantDecisionView(APIView):
 serializer_class=MemberSummarySerializer
 permission_classes=[IsVerifiedMember]
 def post(self,request,pk):
  applicant=get_object_or_404(scope_users(request.user),pk=pk)
  applicant=decide_application(request.user,applicant,request.data.get('decision'))
  return Response(MemberSummarySerializer(applicant,context={'request':request}).data)

class ProfileView(generics.RetrieveUpdateAPIView):
 permission_classes=[IsVerifiedMember]
 def get_object(self): return self.request.user
 def get_serializer_class(self): return ProfileUpdateSerializer if self.request.method in ('PUT','PATCH') else UserSerializer
class PasswordChangeView(APIView):
 serializer_class=PasswordChangeSerializer
 permission_classes=[IsVerifiedMember]
 def post(self,request):
  s=PasswordChangeSerializer(data=request.data,context={'request':request}); s.is_valid(raise_exception=True)
  if not request.user.check_password(s.validated_data['old_password']): raise ValidationError({'old_password':'Current password is incorrect.'})
  request.user.set_password(s.validated_data['new_password']); request.user.save(update_fields=['password']); return Response(status=status.HTTP_204_NO_CONTENT)

class ReportListCreateView(generics.ListCreateAPIView):
 permission_classes=[IsVerifiedMember]
 def get_serializer_class(self): return ReportSubmitSerializer if self.request.method=='POST' else ReportSerializer
 def get_queryset(self):
  u=self.request.user
  qs=Report.objects.select_related('submitted_by','submitted_to','reviewed_by')
  if role_title(u) in ('President','Director of Monitoring & Compliance'): return qs
  return qs.filter(Q(submitted_by=u)|Q(submitted_to=u))
 def perform_create(self,serializer): self.created=submit_report(self.request.user,**serializer.validated_data)
 def create(self,request,*args,**kwargs):
  s=self.get_serializer(data=request.data); s.is_valid(raise_exception=True); self.perform_create(s); return Response(ReportSerializer(self.created).data,status=201)
class ReportDetailView(generics.RetrieveAPIView):
 serializer_class=ReportSerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self):
  u=self.request.user; qs=Report.objects.all()
  return qs if role_title(u) in ('President','Director of Monitoring & Compliance') else qs.filter(Q(submitted_by=u)|Q(submitted_to=u))
class ReportReviewView(APIView):
 serializer_class=ReportSerializer
 permission_classes=[IsVerifiedMember]
 def post(self,request,pk):
  report=get_object_or_404(Report,pk=pk)
  return Response(ReportSerializer(review_report(request.user,report,request.data.get('action'),request.data.get('notes',''))).data)
class ReportEscalateView(APIView):
 serializer_class=ReportSerializer
 permission_classes=[IsVerifiedMember]
 def post(self,request,pk):
  return Response(ReportSerializer(escalate_report(request.user,get_object_or_404(Report,pk=pk))).data,status=201)

class MyArticleListCreateView(generics.ListCreateAPIView):
 serializer_class=CampaignWriteSerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self): return Campaign.objects.filter(author=self.request.user)
 def perform_create(self,s):
  base=slugify(s.validated_data['title']) or 'article'; slug=base; n=2
  while Campaign.objects.filter(slug=slug).exists(): slug=f'{base}-{n}'; n+=1
  s.save(author=self.request.user,status='DRAFT',slug=slug)
class MyArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
 serializer_class=CampaignWriteSerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self): return Campaign.objects.filter(author=self.request.user).exclude(status='PUBLISHED')
 def perform_destroy(self,obj):
  if obj.status=='PENDING': raise ValidationError({'status':'Pending articles cannot be deleted.'})
  obj.delete()
class ArticleSubmitView(APIView):
 serializer_class=CampaignWriteSerializer
 permission_classes=[IsVerifiedMember]
 def post(self,request,pk): return Response(CampaignWriteSerializer(submit_article(get_object_or_404(Campaign,pk=pk),request.user)).data)
class EditorialQueueView(generics.ListAPIView):
 serializer_class=CampaignWriteSerializer; permission_classes=[IsEditor]
 def get_queryset(self): return Campaign.objects.filter(status='PENDING').select_related('author','lga','ward')
class EditorialDecisionView(APIView):
 serializer_class=CampaignWriteSerializer
 permission_classes=[IsEditor]
 def post(self,request,pk): return Response(CampaignWriteSerializer(decide_article(get_object_or_404(Campaign,pk=pk),request.user,request.data.get('decision'),request.data.get('note',''))).data)

class MyMediaView(generics.ListCreateAPIView):
 serializer_class=MediaItemSerializer; permission_classes=[IsPublicityOfficer]
 def get_queryset(self): return MediaItem.objects.filter(uploaded_by=self.request.user)
 def perform_create(self,s):
  director=role_title(self.request.user)=='Director of Media & Communications'
  s.save(uploaded_by=self.request.user,status='APPROVED' if director else 'PENDING',approved_by=self.request.user if director else None)
class MyMediaDetailView(generics.RetrieveUpdateDestroyAPIView):
 serializer_class=MediaItemSerializer; permission_classes=[IsPublicityOfficer]
 def get_queryset(self): return MediaItem.objects.filter(uploaded_by=self.request.user)
class MediaReviewQueueView(generics.ListAPIView):
 serializer_class=MediaItemSerializer; permission_classes=[IsEditor]
 def get_queryset(self): return MediaItem.objects.filter(status='PENDING')
class MediaDecisionView(APIView):
 serializer_class=MediaItemSerializer
 permission_classes=[IsEditor]
 def post(self,request,pk):
  item=get_object_or_404(MediaItem,pk=pk,status='PENDING'); decision=request.data.get('decision')
  if decision not in ('approve','reject'): raise ValidationError({'decision':'Use approve or reject.'})
  item.status='APPROVED' if decision=='approve' else 'REJECTED'; item.approved_by=request.user if decision=='approve' else None; item.save()
  from core.notifications import notify
  notify(item.uploaded_by,'SUCCESS' if decision=='approve' else 'WARNING','Media Reviewed',f'Your media item was {decision}d.','/media/my-media/',event='MEDIA_REVIEWED')
  return Response(MediaItemSerializer(item).data)

class EventViewSet(viewsets.ModelViewSet):
 serializer_class=EventSerializer; permission_classes=[IsVerifiedMember]; queryset=Event.objects.all()
 def get_permissions(self): return [IsEventManager()] if self.action in ('create','update','partial_update','destroy') else [IsVerifiedMember()]
 def perform_create(self,s):
  event=s.save(created_by=self.request.user)
  from core.notifications import notify_event_audience
  notify_event_audience('MEETING_CREATED',event,f'A new KPN event has been scheduled for {event.start_date}.')
 def perform_update(self,s):
  event=s.save()
  from core.notifications import notify_event_audience
  notify_event_audience('MEETING_CHANGED',event,'A KPN event schedule or details changed.')
 def perform_destroy(self,event):
  from core.notifications import notify_event_audience
  notify_event_audience('MEETING_CANCELLED',event,'A KPN event has been cancelled.')
  event.delete()
 @action(detail=True,methods=['get','put'],permission_classes=[IsEventManager])
 def attendance(self,request,pk=None):
  event=self.get_object()
  if request.method=='GET': return Response(AttendanceSerializer(event.attendances.all(),many=True).data)
  records=request.data.get('records',[])
  allowed=set(scope_users(request.user).values_list('id',flat=True))
  for row in records:
   if row.get('attendee') not in allowed: raise PermissionDenied('An attendee is outside your jurisdiction.')
   EventAttendance.objects.update_or_create(event=event,attendee_id=row['attendee'],defaults={'present':bool(row.get('present',True)),'notes':row.get('notes',''),'recorded_by':request.user})
  return Response(AttendanceSerializer(event.attendances.all(),many=True).data)
 @action(detail=True,methods=['get','put'],permission_classes=[IsVerifiedMember])
 def minutes(self,request,pk=None):
  event=self.get_object()
  if request.method=='GET': return Response(MinutesSerializer(get_object_or_404(MeetingMinutes,event=event)).data)
  if role_title(request.user)!='General Secretary': raise PermissionDenied('Only the General Secretary manages minutes.')
  obj,_=MeetingMinutes.objects.get_or_create(event=event,defaults={'content':'','summary':'','recorded_by':request.user})
  s=MinutesSerializer(obj,data=request.data,partial=True); s.is_valid(raise_exception=True); s.save(recorded_by=request.user,published_at=timezone.now() if s.validated_data.get('is_published') else None); return Response(s.data)

class WardMeetingViewSet(viewsets.ModelViewSet):
 queryset=WardMeeting.objects.all()
 serializer_class=WardMeetingSerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self):
  u=self.request.user
  if u.role=='STATE': return WardMeeting.objects.all()
  if u.role=='ZONAL': return WardMeeting.objects.filter(ward__lga__zone=u.zone)
  if u.role=='LGA': return WardMeeting.objects.filter(ward__lga=u.lga)
  return WardMeeting.objects.filter(ward=u.ward) if u.ward_id else WardMeeting.objects.none()
 def perform_create(self,s):
  if self.request.user.role!='WARD' or role_title(self.request.user) not in ('Ward Community Lead','Ward Administrative Officer'): raise PermissionDenied('Ward meeting management permission required.')
  s.save(ward=self.request.user.ward,created_by=self.request.user)

class DeviceRegistrationView(generics.ListCreateAPIView):
 serializer_class=DeviceSerializer; permission_classes=[permissions.IsAuthenticated]
 def get_queryset(self): return DeviceRegistration.objects.filter(user=self.request.user,is_active=True)
 def create(self,request,*args,**kwargs):
  s=self.get_serializer(data=request.data); s.is_valid(raise_exception=True)
  obj,_=DeviceRegistration.objects.update_or_create(token=s.validated_data['token'],defaults={**s.validated_data,'user':request.user,'is_active':True})
  return Response(self.get_serializer(obj).data,status=200)
class DeviceRemoveView(APIView):
 serializer_class=DeviceSerializer
 permission_classes=[permissions.IsAuthenticated]
 def delete(self,request,pk): DeviceRegistration.objects.filter(pk=pk,user=request.user).update(is_active=False); return Response(status=204)
class NotificationListView(generics.ListAPIView):
 serializer_class=NotificationSerializer; permission_classes=[permissions.IsAuthenticated]
 def get_queryset(self): return Notification.objects.filter(user=self.request.user)
class NotificationReadView(APIView):
 serializer_class=NotificationSerializer
 permission_classes=[permissions.IsAuthenticated]
 def post(self,request,pk=None):
  qs=Notification.objects.filter(user=request.user); qs=qs if pk is None else qs.filter(pk=pk); qs.update(is_read=True); return Response(status=204)

class ProgramViewSet(viewsets.ModelViewSet):
 serializer_class=WomensProgramSerializer
 permission_classes=[IsVerifiedMember]
 def _config(self):
  kind=self.kwargs.get('kind','women'); cfg={'women':(WomensProgram,WomensProgramSerializer,("Director of Women's Development","Assistant Director of Women's Development","LGA Women's Development Officer")),'youth':(YouthProgram,YouthProgramSerializer,('Director of Youth Development',)),'welfare':(WelfareProgram,WelfareProgramSerializer,('Director of Member Support & Welfare','LGA Member Support Officer'))}; return cfg[kind]
 def get_serializer_class(self): return self._config()[1]
 def get_queryset(self):
  model,_,_=self._config(); u=self.request.user; qs=model.objects.all()
  if u.role=='ZONAL': return qs.filter(Q(zone=u.zone)|Q(zone__isnull=True))
  if u.role=='LGA': return qs.filter(Q(lga=u.lga)|Q(lga__isnull=True,zone=u.zone)|Q(lga__isnull=True,zone__isnull=True))
  return qs
 def _check(self):
  if role_title(self.request.user) not in self._config()[2]: raise PermissionDenied('Program management permission required.')
 def _scope_values(self):
  u=self.request.user
  if u.role=='LGA': return {'zone':u.zone,'lga':u.lga}
  if u.role=='ZONAL': return {'zone':u.zone,'lga':None}
  return {}
 def perform_create(self,s): self._check(); s.save(created_by=self.request.user,**self._scope_values())
 def perform_update(self,s): self._check(); s.save(**self._scope_values())
 def perform_destroy(self,obj): self._check(); obj.delete()

class FinanceSummaryView(APIView):
 serializer_class=GenericObjectSerializer
 permission_classes=[IsStateExecutive]
 def get(self,request):
  if role_title(request.user) not in ('President','Director of Finance','Finance Operations Officer','Director of Audit & Accountability'): raise PermissionDenied('State finance permission required.')
  income=Donation.objects.filter(status__in=('VERIFIED','RECORDED')).aggregate(v=Sum('amount'))['v'] or 0; expenses=Expense.objects.aggregate(v=Sum('amount'))['v'] or 0
  return Response({'scope':'STATE','total_income':income,'total_expenses':expenses,'balance':income-expenses,'pending_donations':Donation.objects.filter(status='UNVERIFIED').count()})
class DonationListCreateView(generics.ListCreateAPIView):
 serializer_class=DonationSerializer; permission_classes=[IsStateExecutive]; queryset=Donation.objects.all()
 def perform_create(self,s):
  if role_title(self.request.user)!='Director of Finance': raise PermissionDenied('Director of Finance permission required.')
  s.save(recorded_by=self.request.user)
class ExpenseListCreateView(generics.ListCreateAPIView):
 serializer_class=ExpenseSerializer; permission_classes=[IsStateExecutive]; queryset=Expense.objects.all()
 def perform_create(self,s):
  if role_title(self.request.user)!='Finance Operations Officer': raise PermissionDenied('Finance Operations Officer permission required.')
  s.save(recorded_by=self.request.user)

class DisciplineListCreateView(generics.ListCreateAPIView):
 serializer_class=DisciplinarySerializer; permission_classes=[IsVerifiedMember]
 def get_queryset(self):
  if self.request.user.role!='STATE': raise PermissionDenied('State disciplinary permission required.')
  return DisciplinaryAction.objects.filter(user__is_superuser=False)
 def perform_create(self,s):
  if self.request.user.role!='STATE': raise PermissionDenied('State disciplinary permission required.')
  target=s.validated_data['user']; require_jurisdiction(self.request.user,target); s.save(issued_by=self.request.user,is_approved=s.validated_data['action_type']=='WARNING',approved_by=self.request.user if s.validated_data['action_type']=='WARNING' else None)
class DisciplineDecisionView(APIView):
 serializer_class=DisciplinarySerializer
 permission_classes=[IsVerifiedMember]
 def post(self,request,pk):
  action=get_object_or_404(DisciplinaryAction,pk=pk,user__is_superuser=False)
  if role_title(request.user)!='President': raise PermissionDenied('Only the President makes the final disciplinary decision.')
  decision=request.data.get('decision')
  if decision=='approve':
   action.is_approved=True; action.approved_by=request.user; action.save(update_fields=['is_approved','approved_by'])
   if action.action_type=='SUSPENSION': action.user.status='SUSPENDED'; action.user.is_active=True
   elif action.action_type=='DISMISSAL': action.user.status='DISMISSED'; action.user.is_active=False
   action.user.save(update_fields=['status','is_active','updated_at'])
  elif decision=='reject': action.delete(); return Response(status=204)
  else: raise ValidationError({'decision':'Use approve or reject.'})
  return Response(DisciplinarySerializer(action).data)

class HubManagementViewSet(viewsets.ModelViewSet):
 serializer_class=OpportunitySerializer
 def perform_create(self,s):
  obj=s.save(); self._notify_opportunity(obj,'OPPORTUNITY_PUBLISHED')
 def perform_update(self,s):
  obj=s.save(); self._notify_opportunity(obj,'OPPORTUNITY_UPDATED')
 def _notify_opportunity(self,obj,event):
  if isinstance(obj,Opportunity) and obj.status in ('OPEN','CLOSING_SOON'):
   from core.notifications import notify_many,verified_members
   notify_many(verified_members(),'INFO','Opportunity Update',obj.title,'/opportunities/',event=event)
 permission_classes=[IsEditor]
 def _config(self):
  return {'opportunities':(Opportunity,OpportunitySerializer),'initiatives':(CommunityInitiative,CommunityInitiativeSerializer),'advocacy':(AdvocacyCampaign,AdvocacyCampaignSerializer),'patrons':(Patron,PatronSerializer)}[self.kwargs.get('kind','opportunities')]
 def get_queryset(self): return self._config()[0].objects.all()
 def get_serializer_class(self): return self._config()[1]
