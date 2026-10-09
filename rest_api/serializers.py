from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from campaigns.models import Campaign
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron
from leadership.models import Zone, LGA, Ward, RoleDefinition
from staff.models import User
from telegram_integration.models import TelegramMembership
from leadership.access import role_title
from leadership.capabilities import capabilities_for
from leadership.roles import DASHBOARD_BY_ROLE
from telegram_integration.permissions import check_dashboard_access

class CampaignSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(source='featured_image', allow_null=True, read_only=True)
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True, read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    read_time = serializers.SerializerMethodField()
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    verification_status_label = serializers.CharField(source='get_verification_status_display', read_only=True)

    class Meta:
        model = Campaign
        fields = ['id','slug','title','subheadline','category','category_label','location','lga','lga_name',
                  'ward','ward_name','verification_status','verification_status_label','reporter_credit',
                  'author_name','image','content','content_json','meta_description','views','read_time','published_at','status']

    def get_read_time(self, obj) -> int:
        return obj.get_read_time()

class OpportunitySerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source='provider')
    external_apply_link = serializers.URLField(source='application_link', allow_blank=True)
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Opportunity
        fields = ['id','slug','title','category','category_label','organization','description','requirements',
                  'benefits','deadline','status','status_label','is_featured','external_apply_link','created_at','updated_at']

class CommunityInitiativeSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    class Meta:
        model = CommunityInitiative
        fields = ['id','title','category','category_label','status','status_label','description','location_text',
                  'people_reached','image','created_at','updated_at']

class AdvocacyCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvocacyCampaign
        fields = ['id','title','issue','background','kpn_position','actions_taken','government_response',
                  'outcome','is_active','image','created_at','updated_at']

class PatronSerializer(serializers.ModelSerializer):
    patron_type_label = serializers.CharField(source='get_patron_type_display', read_only=True)
    class Meta:
        model = Patron
        fields = ['id','patron_type','patron_type_label','full_name','title','bio','photo','is_published','order']

class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ['id', 'name']

class LGASerializer(serializers.ModelSerializer):
    class Meta:
        model = LGA
        fields = ['id', 'name', 'zone']

class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = ['id', 'name', 'lga']

class RoleDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleDefinition
        fields = '__all__'

class LeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'role', 'role_definition', 'photo']

class TelegramMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramMembership
        fields = ['telegram_user_id', 'telegram_username', 'telegram_status', 'is_verified', 'last_verified_at', 'left_at']

class UserSerializer(serializers.ModelSerializer):
    telegram_membership = TelegramMembershipSerializer(read_only=True, allow_null=True)
    tier = serializers.CharField(source='role', read_only=True)
    zone_name = serializers.CharField(source='zone.name', read_only=True, allow_null=True)
    lga_name = serializers.CharField(source='lga.name', read_only=True, allow_null=True)
    ward_name = serializers.CharField(source='ward.name', read_only=True, allow_null=True)
    role_title = serializers.SerializerMethodField()
    seat_number = serializers.IntegerField(source='role_definition.seat_number', read_only=True, allow_null=True)
    access = serializers.SerializerMethodField()
    dashboard = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    mobile_tools = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'bio', 'photo', 'gender',
                  'role', 'tier', 'zone', 'zone_name', 'lga', 'lga_name', 'ward', 'ward_name',
                  'role_definition', 'role_title', 'seat_number', 'status', 'reporter_level',
                  'is_trusted_reporter', 'telegram_membership', 'access', 'dashboard', 'capabilities',
                  'facebook_url','twitter_url','instagram_url','tiktok_url','mobile_tools']
        read_only_fields = fields

    def get_role_title(self, obj) -> str | None:
        return role_title(obj)

    def get_access(self, obj) -> dict:
        result = check_dashboard_access(obj)
        states = {'ok': 'ALLOWED', 'not_verified': 'PENDING_APPROVAL', 'telegram_required': 'TELEGRAM_REQUIRED'}
        return {
            'state': states[result['reason']],
            'telegram_required': result['telegram_required'],
            'telegram_verified': result['telegram_active'],
        }

    def get_dashboard(self, obj) -> str:
        return DASHBOARD_BY_ROLE.get(role_title(obj), 'member')

    def get_capabilities(self, obj) -> tuple[str, ...]:
        return capabilities_for(obj)


    def get_mobile_tools(self,obj) -> list[str]:
        from .mobilization_views import can_mobilize
        return ['mobilization'] if can_mobilize(obj) else []

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'bio', 'gender',
                  'photo', 'zone', 'lga', 'ward', 'facebook_url','twitter_url','instagram_url','tiktok_url']
        read_only_fields = ['username', 'zone', 'lga', 'ward']

class ImpactMetricsSerializer(serializers.Serializer):
    verified_members = serializers.IntegerField()
    trusted_reporters = serializers.IntegerField()
    community_reports = serializers.IntegerField()
    opportunities = serializers.IntegerField()
    impact_communities_reached = serializers.IntegerField()
    active_lgas = serializers.IntegerField()
    active_wards = serializers.IntegerField()
    zones_total = serializers.IntegerField()
    lgas_total = serializers.IntegerField()
    wards_total = serializers.IntegerField()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)
    photo = serializers.ImageField(required=True)
    role_definition = serializers.PrimaryKeyRelatedField(queryset=RoleDefinition.objects.all(), required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm', 'first_name', 'last_name', 'phone', 'gender', 'photo', 'zone', 'lga', 'ward', 'role_definition', 'bio']

    def validate(self, attrs):
        # 1. Passwords match
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})

        # 2. Password complexity
        user = User(username=attrs['username'], email=attrs.get('email'), first_name=attrs.get('first_name'), last_name=attrs.get('last_name'))
        try:
            validate_password(attrs['password'], user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        # 3. Photo size limit
        photo = attrs.get('photo')
        if photo and photo.size > 400 * 1024:
            raise serializers.ValidationError({"photo": "Profile photo must not exceed 400KB."})

        # 4. Role and location constraints
        role_def = attrs.get('role_definition')
        zone = attrs.get('zone')
        lga = attrs.get('lga')
        ward = attrs.get('ward')
        role = role_def.tier

        if role == 'STATE':
            if not zone or not lga:
                raise serializers.ValidationError("Zone and LGA are required for State Executive roles.")
        elif role == 'ZONAL':
            if not zone:
                raise serializers.ValidationError("Zone is required for Zonal Excos roles.")
        elif role == 'LGA':
            if not lga:
                raise serializers.ValidationError("LGA is required for LGA Excos roles.")
        elif role == 'WARD':
            if not ward:
                raise serializers.ValidationError("Ward is required for Ward Leaders roles.")

        # 5. Position availability check
        existing_holder = User.objects.filter(role_definition=role_def, status='VERIFIED')
        if role == 'ZONAL':
            existing_holder = existing_holder.filter(zone=zone)
        elif role == 'LGA':
            existing_holder = existing_holder.filter(lga=lga)
        elif role == 'WARD':
            existing_holder = existing_holder.filter(ward=ward)

        if existing_holder.exists():
            raise serializers.ValidationError("This position is already filled.")

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        role_def = validated_data['role_definition']
        validated_data['role'] = role_def.tier
        validated_data['status'] = 'PENDING'
        validated_data['facebook_verified'] = False # For backward compatibility in DB

        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

class LeadershipHolderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    photo = serializers.URLField(allow_null=True)

class LeadershipLocationSerializer(serializers.Serializer):
    label = serializers.CharField()
    zone = serializers.IntegerField(allow_null=True)
    zone_name = serializers.CharField(allow_null=True)
    lga = serializers.IntegerField(allow_null=True)
    lga_name = serializers.CharField(allow_null=True)
    ward = serializers.IntegerField(allow_null=True)
    ward_name = serializers.CharField(allow_null=True)

class LeadershipSeatSerializer(serializers.Serializer):
    seat_key = serializers.CharField()
    role_definition = serializers.IntegerField()
    role_title = serializers.CharField()
    tier = serializers.ChoiceField(choices=['STATE','ZONAL','LGA','WARD'])
    seat_number = serializers.IntegerField()
    location = LeadershipLocationSerializer()
    status = serializers.ChoiceField(choices=['FILLED','VACANT'])
    holder = LeadershipHolderSerializer(allow_null=True)

class MemberSerializer(serializers.ModelSerializer):
    role_title = serializers.CharField(source='role_definition.title', allow_null=True, read_only=True)
    zone_name = serializers.CharField(source='zone.name', allow_null=True, read_only=True)
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True, read_only=True)
    class Meta:
        model = User
        fields = ['id','username','first_name','last_name','email','phone','photo','gender','bio','role','role_title',
                  'zone','zone_name','lga','lga_name','ward','ward_name','status','reporter_level','created_at']
        read_only_fields = fields

class ReportSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source='submitted_by.get_full_name', read_only=True)
    submitted_to_name = serializers.CharField(source='submitted_to.get_full_name', allow_null=True, read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', allow_null=True, read_only=True)
    class Meta:
        model = __import__('core.models',fromlist=['Report']).Report
        fields = ['id','title','report_type','content','period','submitted_by','submitted_by_name','submitted_to',
                  'submitted_to_name','reviewed_by','reviewed_by_name','parent_report','status','is_reviewed',
                  'is_escalated','review_notes','deadline','created_at','submitted_at','reviewed_at','escalated_at']
        read_only_fields = fields

class ReportCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    content = serializers.CharField()
    period = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    deadline = serializers.DateField(required=False, allow_null=True)

class ArticleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ['id','slug','status','rejection_note','title','subheadline','category','location','lga','ward','verification_status','reporter_credit','content','content_json','featured_image','meta_description']
        read_only_fields = ['id','slug','status','rejection_note']
    def validate(self,attrs):
        lga=attrs.get('lga',getattr(self.instance,'lga',None))
        ward=attrs.get('ward',getattr(self.instance,'ward',None))
        if ward and (not lga or ward.lga_id!=lga.pk):raise serializers.ValidationError({'ward':'Choose a ward belonging to the selected LGA.'})
        if 'content_json' in attrs:
            from .article_blocks import sanitize_article_blocks
            attrs['content_json']=sanitize_article_blocks(attrs['content_json'])
        return attrs

class MediaItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = __import__('media.models',fromlist=['MediaItem']).MediaItem
        fields = ['id','title','description','media_type','file','thumbnail','uploaded_by','status','approved_by','created_at','updated_at']
        read_only_fields = ['id','uploaded_by','status','approved_by','created_at','updated_at']

from events.models import Event, EventAttendance, MeetingMinutes
from staff.models import WardMeeting, WomensProgram, YouthProgram, WelfareProgram, DisciplinaryAction
from donations.models import Donation, Expense
from core.models import Notification
from .models import DeviceRegistration

class EventSerializer(serializers.ModelSerializer):
    def validate(self,attrs):
        starts=attrs.get('start_date',getattr(self.instance,'start_date',None))
        ends=attrs.get('end_date',getattr(self.instance,'end_date',None))
        if starts and ends and starts>=ends:raise serializers.ValidationError({'end_date':'End date must be after start date.'})
        return attrs
    class Meta:
        model = Event
        fields = ['id','title','description','location','start_date','end_date','created_by','created_at','updated_at']
        read_only_fields = ['id','created_by','created_at','updated_at']

class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventAttendance
        fields = ['attendee','present','notes']

class MeetingMinutesSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingMinutes
        fields = ['id','event','content','summary','attendees_present','recorded_by','recorded_at','updated_at','is_published','published_at']
        read_only_fields = ['id','event','recorded_by','recorded_at','updated_at','published_at']

class WardMeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = WardMeeting
        fields = ['id','ward','meeting_type','title','date','time','location','agenda','minutes','created_by','created_at','updated_at']
        read_only_fields = ['id','ward','created_by','created_at','updated_at']

class WomensProgramSerializer(serializers.ModelSerializer):
    target_participants = serializers.IntegerField(required=False)
    class Meta:
        model = WomensProgram
        fields = ['id','title','description','program_type','status','zone','lga','start_date','end_date','location','target_participants','budget','notes','created_by','created_at','updated_at']
        read_only_fields = ['id','zone','lga','created_by','created_at','updated_at']

class YouthProgramSerializer(serializers.ModelSerializer):
    target_participants = serializers.IntegerField(required=False)
    class Meta:
        model = YouthProgram
        fields = ['id','title','description','program_type','status','zone','lga','start_date','end_date','location','target_participants','budget','notes','created_by','created_at','updated_at']
        read_only_fields = ['id','zone','lga','created_by','created_at','updated_at']

class WelfareProgramSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    target_participants = serializers.IntegerField(source='target_beneficiaries', required=False)
    class Meta:
        model = WelfareProgram
        fields = ['id','title','description','program_type','status','zone','lga','start_date','end_date','location','target_participants','target_beneficiaries','budget','notes','created_by','created_at','updated_at']
        read_only_fields = ['id','zone','lga','location','created_by','created_at','updated_at']
    def get_location(self,obj) -> str:
        return obj.get_scope()

class DonationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donation
        fields = ['id','donor_name','amount','reference','notes','status','verified_by','verified_at','recorded_by','recorded_at','created_at']
        read_only_fields = ['id','status','verified_by','verified_at','recorded_by','recorded_at','created_at']

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ['id','description','amount','category','notes','date','recorded_by','created_at']
        read_only_fields = ['id','recorded_by','created_at']

class DisciplineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisciplinaryAction
        fields = ['id','user','action_type','reason','issued_by','approved_by','is_approved','legal_reviewed_by','legal_opinion','legal_approved','legal_reviewed_at','created_at']
        read_only_fields = ['id','issued_by','approved_by','is_approved','legal_reviewed_by','legal_opinion','legal_approved','legal_reviewed_at','created_at']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id','event','notif_type','target_type','target_id','title','message','link','is_read','created_at']
        read_only_fields = fields

class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceRegistration
        fields = ['id','token','device_id','platform','app_version','is_active','created_at','updated_at']
        read_only_fields = ['id','created_at','updated_at']

from core.models import FAQ, CommunityReport
from staff.models import Announcement, CommunityOutreach
from donations.models import FinancialReport, AuditReport
class FAQSerializer(serializers.ModelSerializer):
    class Meta: model=FAQ; fields=['id','question','answer','order','is_active','created_at','updated_at']
class CommunityReportSerializer(serializers.ModelSerializer):
    class Meta:
        model=CommunityReport
        fields=['id','reporter_name','reporter_phone','submitted_by','ward','lga','zone','location_details','incident_date','incident_time','category','what_happened','who_was_involved','why_is_it_important','evidence_image','evidence_video','status','info_status','internal_notes','created_at']
        read_only_fields=['id','reporter_name','reporter_phone','submitted_by','zone','status','info_status','internal_notes','created_at']
class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model=Announcement
        fields=['id','title','content','scope','priority','target_zone','target_lga','target_ward','is_active','expires_at','created_by','created_at','updated_at']
        read_only_fields=['id','created_by','created_at','updated_at']
    def validate(self,a):
        fields=('title','content','scope','priority','target_zone','target_lga','target_ward','is_active','expires_at')
        merged={name:getattr(self.instance,name) for name in fields} if self.instance else {}
        merged.update(a)
        obj=Announcement(**merged)
        try:obj.clean()
        except Exception as exc:raise serializers.ValidationError(getattr(exc,'message_dict',{'non_field_errors':exc.messages}))
        request=self.context.get('request')
        if request:
            from staff.forms import AnnouncementForm
            from rest_framework.exceptions import PermissionDenied
            user=request.user
            if user.role!='STATE' and not {'ZONAL':user.zone_id,'LGA':user.lga_id,'WARD':user.ward_id}.get(user.role):
                raise PermissionDenied('Your announcement jurisdiction is not assigned.')
            form=AnnouncementForm(user=user)
            if obj.scope not in dict(form.fields['scope'].choices):raise PermissionDenied('This announcement scope is not authorized for your role.')
            for name in ('target_zone','target_lga','target_ward'):
                target=merged.get(name)
                if target and (name not in form.fields or not form.fields[name].queryset.filter(pk=target.pk).exists()):
                    raise PermissionDenied('An announcement target is outside your jurisdiction.')
        return a
class OutreachSerializer(serializers.ModelSerializer):
    class Meta:
        model=CommunityOutreach
        fields=['id','organization','contact_person','contact_phone','contact_email','engagement_type','status','date','location','purpose','notes','follow_up_date','follow_up_notes','created_by','created_at','updated_at']
        read_only_fields=['id','created_by','created_at','updated_at']
class FinancialReportSerializer(serializers.ModelSerializer):
    class Meta:
        model=FinancialReport
        fields=['id','title','report_period','total_income','total_expenses','report_file','summary','prepared_by','created_at']
        read_only_fields=['id','prepared_by','created_at']
class AuditReportSerializer(serializers.ModelSerializer):
    class Meta:
        model=AuditReport
        fields=['id','title','audit_period','findings','recommendations','compliance_status','status','report_file','submitted_by','submitted_to','reviewed_by','review_notes','created_at','submitted_at','reviewed_at']
        read_only_fields=['id','status','submitted_by','submitted_to','reviewed_by','created_at','submitted_at','reviewed_at']
