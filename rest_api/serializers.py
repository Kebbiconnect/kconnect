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
                  'author_name','image','content','content_json','meta_description','views','read_time','published_at','status',
                  'story_id','source_name','source_url']

    def get_read_time(self, obj) -> int:
        return obj.get_read_time()

class OpportunitySerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source='provider')
    # Priority 1 web rule, mirrored: while a listing is
    # VERIFICATION_PENDING its application link is never handed out.
    external_apply_link = serializers.SerializerMethodField()
    application_link = serializers.SerializerMethodField()
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)

    class Meta:
        model = Opportunity
        fields = ['id','slug','title','category','category_label','organization','provider','description','requirements',
                  'benefits','deadline','opens_at','location_text','lga','lga_name','nigerians_eligible',
                  'verification_source','status','status_label','is_featured','external_apply_link',
                  'application_link','created_at','updated_at']

    def _visible_application_link(self, obj) -> str:
        if obj.status == 'VERIFICATION_PENDING':
            return ''
        return obj.application_link or ''

    def get_external_apply_link(self, obj) -> str:
        return self._visible_application_link(obj)

    def get_application_link(self, obj) -> str:
        return self._visible_application_link(obj)

class CommunityInitiativeSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    # Public presentation label (Priority 2): PLANNING reads "Planned"
    # on public surfaces; the stored value and staff label stay as-is.
    public_status_label = serializers.SerializerMethodField()
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True, read_only=True)
    class Meta:
        model = CommunityInitiative
        fields = ['id','title','category','category_label','status','status_label','public_status_label',
                  'description','objective','start_date','end_date','responsible_team','results',
                  'location_text','lga','lga_name','ward','ward_name',
                  'people_reached','image','created_at','updated_at']

    def get_public_status_label(self, obj) -> str:
        return CommunityInitiative.PUBLIC_STATUS_LABELS.get(obj.status, obj.get_status_display())

class AdvocacyCampaignSerializer(serializers.ModelSerializer):
    # Round 2 (screen 45): mirror the web advocacy detail page
    # (core.views.advocacy_detail) — objective, proposed action, the
    # lifecycle status with its label, and the evidence articles,
    # PUBLISHED only exactly as the web page filters them, each with
    # its Story ID.
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    evidence_articles = serializers.SerializerMethodField()

    class Meta:
        model = AdvocacyCampaign
        fields = ['id','title','issue','background','kpn_position','actions_taken','government_response',
                  'outcome','is_active','image','created_at','updated_at',
                  'objective','proposed_action','affected_communities','responsible_team',
                  'status','status_label','evidence_articles']

    def get_evidence_articles(self, obj) -> list:
        return [{
            'id': article.pk, 'title': article.title, 'slug': article.slug,
            'story_id': article.story_id,
        } for article in obj.evidence_articles.all() if article.status == 'PUBLISHED']

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
    # Round 2 (screen 115): tier is the member's role tier, the same
    # value UserSerializer exposes as `tier`.
    tier = serializers.CharField(source='role', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'role', 'tier', 'role_definition', 'photo']

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
    def validate_photo(self,photo):
        if photo and photo.size > 400 * 1024:
            raise serializers.ValidationError('Profile photo must not exceed 400 KiB.')
        return photo

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
    # App 2.0.5: gender arrives as 'M'/'F' from some clients and as the
    # full words 'Male'/'Female' (any case) from others. Accept both and
    # normalise to the model's 'M'/'F' codes; anything else is rejected.
    gender = serializers.CharField(required=False, allow_blank=True, max_length=10)

    def validate_gender(self, value):
        normalised = str(value or '').strip().upper()
        if normalised in ('', 'M', 'MALE'):
            return 'M' if normalised else ''
        if normalised in ('F', 'FEMALE'):
            return 'F'
        raise serializers.ValidationError("Gender must be 'M', 'F', 'Male' or 'Female'.")

    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False, max_length=4096)
    password_confirm = serializers.CharField(write_only=True, required=True, trim_whitespace=False, max_length=4096)
    photo = serializers.ImageField(required=True)
    # role_definition is optional ONLY for an explicit General Member
    # application (general_member=true, sent by the mobile app — owner,
    # 27 Nov 2026). The website form always submits a leadership
    # role_definition and never sets general_member, so website
    # registration remains leadership-only.
    role_definition = serializers.PrimaryKeyRelatedField(queryset=RoleDefinition.objects.all(), required=False, allow_null=True)
    general_member = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm', 'first_name', 'last_name', 'phone', 'gender', 'photo', 'zone', 'lga', 'ward', 'role_definition', 'bio', 'general_member']

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

        # Authoritative leadership-only and parent/child location validation.
        from staff.services.assignments import validate_location
        role_def=attrs.get('role_definition')
        general=bool(attrs.get('general_member'))
        if role_def is None and not general:
            raise serializers.ValidationError({'role_definition':'Choose a position, or apply as a General Member.'})
        if role_def is None and general and not attrs.get('ward'):
            # A General Member's ward/LGA/zone decide which leaders
            # review the application, so the ward is required.
            raise serializers.ValidationError({'ward':'Select your ward so the right leaders can review your application.'})
        try:
            assigned=validate_location(role_def,attrs.get('zone'),attrs.get('lga'),attrs.get('ward'),registration=True,allow_general=general)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'non_field_errors':exc.messages})
        attrs.update({k:v for k,v in assigned.items() if k != 'role'})
        role=assigned['role']; zone=assigned['zone']; lga=assigned['lga']; ward=assigned['ward']
        for key in ('first_name','last_name','email','phone'):
            if not str(attrs.get(key,'')).strip():
                raise serializers.ValidationError({key:'This field is required.'})
        for key in ('email','phone'):
            if User.objects.filter(**{key+'__iexact':attrs[key]}).exists():
                raise serializers.ValidationError({key:'This value is already registered.'})

        # 5. Position availability check (leadership seats only — a
        # General Member application holds no seat).
        if role_def is not None:
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
        validated_data.pop('general_member', None)
        password = validated_data.pop('password')
        role_def = validated_data.get('role_definition')
        validated_data['role'] = role_def.tier if role_def else 'GENERAL'
        validated_data['status'] = 'PENDING'
        validated_data['facebook_verified'] = False # For backward compatibility in DB

        from django.db import transaction
        photo=validated_data.pop('photo')
        with transaction.atomic():
            # Establish the unique account before any external file upload.
            user=User.objects.create_user(password=password, **validated_data)
            user.photo=photo
            user.save(update_fields=['photo'])
            # Notify the leaders who can decide this application
            # (owner, 27 Nov 2026) once the registration commits. The
            # service never raises, so a notification failure cannot
            # break a registration.
            from staff.services.application_notifications import notify_application_approvers
            transaction.on_commit(lambda uid=user.pk: notify_application_approvers(uid))
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
    role_title = serializers.SerializerMethodField()

    def get_role_title(self, obj):
        return role_title(obj)
    zone_name = serializers.CharField(source='zone.name', allow_null=True, read_only=True)
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True, read_only=True)
    class Meta:
        model = User
        fields = ['id','username','first_name','last_name','email','phone','photo','gender','bio','role','role_title',
                  'zone','zone_name','lga','lga_name','ward','ward_name','status','reporter_level','created_at','archived_at']
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
    # Round 2 (screen 73): the Report model carries report_type and
    # submitted_to (the recipient). The workflow derives both from the
    # submitter (core.services.reports.create_report); they are
    # accepted here so the client can send them, and the create view
    # validates them against the derived values — a mismatch is a 400,
    # never a silent reroute.
    report_type = serializers.ChoiceField(
        choices=['WARD_TO_LGA', 'LGA_TO_ZONAL', 'ZONAL_TO_STATE'],
        required=False)
    submitted_to = serializers.IntegerField(required=False, allow_null=True)

class ArticleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ['id','slug','status','rejection_note','title','subheadline','category','location','lga','ward','verification_status','reporter_credit','content','content_json','featured_image','meta_description','story_id','source_name','source_url']
        read_only_fields = ['id','slug','status','rejection_note','story_id']
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
        fields = ['id','title','description','location','audience','start_date','end_date','created_by','created_at','updated_at']
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
        fields = ['id','donor_name','amount','reference','notes','status','verified_by','verified_at','recorded_by','recorded_at','rejected_by','rejected_at','rejection_reason','created_at']
        read_only_fields = ['id','status','verified_by','verified_at','recorded_by','recorded_at','rejected_by','rejected_at','rejection_reason','created_at']

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
    # Registration upserts by token; uniqueness remains enforced by the database.
    token = serializers.CharField(max_length=512)
    class Meta:
        model = DeviceRegistration
        fields = ['id','token','device_id','platform','app_version','is_active','created_at','updated_at']
        read_only_fields = ['id','created_at','updated_at']

from core.models import FAQ, CommunityReport
from staff.models import Announcement, CommunityOutreach
from donations.models import FinancialReport, AuditReport
class FAQSerializer(serializers.ModelSerializer):
    # Part B (screen 53): category comes from the server-side mapping
    # extracted verbatim from the public FAQ web template — see
    # core/faq_categories.py (the one documented place for it).
    category = serializers.SerializerMethodField()
    class Meta: model=FAQ; fields=['id','question','answer','category','order','is_active','created_at','updated_at']
    def get_category(self,obj) -> str:
        from core.faq_categories import faq_category
        return faq_category(obj.question)
class CommunityReportSerializer(serializers.ModelSerializer):
    # Round 2 (screen 43): the Community Voice payload names the LGA
    # and ward, as the web page renders them ("<Ward> Ward, <LGA>
    # LGA"). Reporter identity fields are unchanged.
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True, read_only=True)
    class Meta:
        model=CommunityReport
        fields=['id','reporter_name','reporter_phone','submitted_by','ward','lga','lga_name','ward_name','zone','location_details','incident_date','incident_time','category','what_happened','who_was_involved','why_is_it_important','evidence_image','evidence_video','status','info_status','internal_notes','created_at']
        read_only_fields=['id','reporter_name','reporter_phone','submitted_by','zone','status','info_status','internal_notes','created_at']
class PublicCommunityReportSerializer(serializers.ModelSerializer):
    # Public Community Voice payload (GET civic/community-voice/):
    # the same field names as CommunityReportSerializer so the app
    # model parses it, minus everything private. The staff serializer
    # above exposes reporter_name, reporter_phone, submitted_by and
    # internal_notes, so it must never be reused on a public route —
    # the web Community Voice page never renders reporter identity
    # either (core.views.community_voice).
    lga_name = serializers.CharField(source='lga.name', allow_null=True, read_only=True)
    ward_name = serializers.CharField(source='ward.name', allow_null=True, read_only=True)
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    info_status_label = serializers.CharField(source='get_info_status_display', read_only=True)
    class Meta:
        model=CommunityReport
        fields=['id','ward','lga','lga_name','ward_name','zone','location_details','incident_date','incident_time','category','category_label','what_happened','who_was_involved','why_is_it_important','evidence_image','evidence_video','status','info_status','info_status_label','voice_published_at','created_at']
        read_only_fields=fields
class AnnouncementSerializer(serializers.ModelSerializer):
    # Part B (screen 81): per-user read state from staff.AnnouncementRead
    # receipts. Anonymous / context-less serialisation is always False.
    is_read = serializers.SerializerMethodField()
    class Meta:
        model=Announcement
        fields=['id','title','content','scope','priority','target_zone','target_lga','target_ward','is_active','expires_at','is_read','created_by','created_at','updated_at']
        read_only_fields=['id','is_read','created_by','created_at','updated_at']
    def get_is_read(self,obj) -> bool:
        request=self.context.get('request')
        user=getattr(request,'user',None)
        if user is None or not getattr(user,'is_authenticated',False):
            return False
        # Prefer the annotation set by the received-list queryset.
        annotated=getattr(obj,'_is_read',None)
        if annotated is not None:
            return bool(annotated)
        from staff.models import AnnouncementRead
        return AnnouncementRead.objects.filter(announcement=obj,user=user).exists()
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
        read_only_fields=['id','status','submitted_by','submitted_to','reviewed_by','review_notes','created_at','submitted_at','reviewed_at']
