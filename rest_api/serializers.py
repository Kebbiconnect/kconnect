from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from campaigns.models import Campaign
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron
from leadership.models import Zone, LGA, Ward, RoleDefinition
from staff.models import User
from telegram_integration.models import TelegramMembership

class CampaignSerializer(serializers.ModelSerializer):
    author_name=serializers.CharField(source='author.get_full_name',read_only=True)
    lga_name=serializers.CharField(source='lga.name',read_only=True,allow_null=True)
    ward_name=serializers.CharField(source='ward.name',read_only=True,allow_null=True)
    read_time=serializers.IntegerField(source='get_read_time',read_only=True)
    image=serializers.ImageField(source='featured_image',read_only=True)
    class Meta:
        model=Campaign
        fields=['id','slug','title','subheadline','category','location','lga','lga_name','ward','ward_name','verification_status','reporter_credit','author_name','image','content','content_json','views','read_time','published_at']
class OpportunitySerializer(serializers.ModelSerializer):
    organization=serializers.CharField(source='provider',read_only=True)
    external_apply_link=serializers.URLField(source='application_link',read_only=True)
    class Meta:
        model=Opportunity
        fields=['id','slug','title','category','organization','description','requirements','benefits','deadline','status','is_featured','external_apply_link','created_at','updated_at']
class CommunityInitiativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityInitiative
        fields = ['title', 'description', 'status']

class AdvocacyCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvocacyCampaign
        fields = '__all__'

class PatronSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patron
        fields = '__all__'

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

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'bio', 'photo', 'gender', 'role', 'zone', 'lga', 'ward', 'role_definition', 'status', 'reporter_level', 'is_trusted_reporter', 'telegram_membership']

class ImpactMetricsSerializer(serializers.Serializer):
    verified_members = serializers.IntegerField()
    trusted_reporters = serializers.IntegerField()
    community_reports = serializers.IntegerField()
    opportunities = serializers.IntegerField()
    impact_communities_reached = serializers.IntegerField()
    active_lgas = serializers.IntegerField()
    active_wards = serializers.IntegerField()

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

from core.models import Report, Notification, DeviceRegistration
from events.models import Event, EventAttendance, MeetingMinutes
from media.models import MediaItem
from staff.models import DisciplinaryAction, WomensProgram, YouthProgram, WelfareProgram, WardMeeting, WardMeetingAttendance
from donations.models import Donation, Expense, FinancialReport

class MemberSummarySerializer(serializers.ModelSerializer):
    role_title=serializers.CharField(source='role_definition.title',read_only=True,allow_null=True)
    class Meta:
        model=User; fields=['id','username','first_name','last_name','email','phone','photo','gender','role','role_title','zone','lga','ward','status','reporter_level','created_at']
        read_only_fields=['role','status','reporter_level','created_at']
class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model=User; fields=['email','first_name','last_name','phone','bio','photo','facebook_url','twitter_url','instagram_url','tiktok_url']
class PasswordChangeSerializer(serializers.Serializer):
    old_password=serializers.CharField(write_only=True); new_password=serializers.CharField(write_only=True)
    def validate_new_password(self,value): validate_password(value,self.context['request'].user); return value
class ReportSerializer(serializers.ModelSerializer):
    submitted_by_name=serializers.CharField(source='submitted_by.get_full_name',read_only=True)
    submitted_to_name=serializers.CharField(source='submitted_to.get_full_name',read_only=True,allow_null=True)
    class Meta:
        model=Report; fields=['id','title','report_type','content','period','submitted_by','submitted_by_name','submitted_to','submitted_to_name','reviewed_by','parent_report','status','is_reviewed','is_escalated','review_notes','deadline','created_at','submitted_at','reviewed_at','escalated_at']
        read_only_fields=['submitted_by','submitted_to','reviewed_by','parent_report','status','is_reviewed','is_escalated','review_notes','created_at','submitted_at','reviewed_at','escalated_at']
class ReportSubmitSerializer(serializers.Serializer):
    title=serializers.CharField(max_length=300); content=serializers.CharField(); period=serializers.CharField(required=False,allow_blank=True); deadline=serializers.DateField(required=False,allow_null=True); report_type=serializers.ChoiceField(choices=Report.REPORT_TYPE_CHOICES,required=False)
class CampaignWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model=Campaign; fields=['id','slug','title','subheadline','category','location','lga','ward','verification_status','reporter_credit','meta_description','content','content_json','featured_image','status','rejection_note','created_at','updated_at','published_at']
        read_only_fields=['slug','status','rejection_note','created_at','updated_at','published_at']
    def validate(self,attrs):
        user=self.context['request'].user; lga=attrs.get('lga',getattr(self.instance,'lga',None)); ward=attrs.get('ward',getattr(self.instance,'ward',None))
        if ward and lga and ward.lga_id != lga.id: raise serializers.ValidationError({'ward':'Ward must belong to the selected LGA.'})
        if user.role=='ZONAL' and lga and lga.zone_id != user.zone_id: raise serializers.ValidationError({'lga':'LGA is outside your zone.'})
        if user.role=='LGA' and ((lga and lga.id!=user.lga_id) or (ward and ward.lga_id!=user.lga_id)): raise serializers.ValidationError({'location':'Location is outside your LGA.'})
        if user.role=='WARD' and ((ward and ward.id!=user.ward_id) or (lga and lga.id!=user.lga_id)): raise serializers.ValidationError({'location':'Location is outside your ward jurisdiction.'})
        return attrs
class MediaItemSerializer(serializers.ModelSerializer):
    class Meta:
        model=MediaItem; fields=['id','title','description','media_type','file','thumbnail','uploaded_by','status','approved_by','created_at','updated_at']; read_only_fields=['uploaded_by','status','approved_by','created_at','updated_at']
class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model=Event; fields='__all__'; read_only_fields=['created_by','created_at','updated_at']
class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model=EventAttendance; fields='__all__'; read_only_fields=['recorded_by','recorded_at']
class MinutesSerializer(serializers.ModelSerializer):
    class Meta:
        model=MeetingMinutes; fields='__all__'; read_only_fields=['recorded_by','recorded_at','updated_at','published_at']
class WardMeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model=WardMeeting; fields='__all__'; read_only_fields=['ward','created_by','created_at','updated_at']
class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model=DeviceRegistration; fields=['id','token','device_id','platform','app_version','is_active','updated_at']; read_only_fields=['id','updated_at']
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model=Notification; fields=['id','event','notif_type','title','message','link','is_read','created_at']; read_only_fields=['id','event','notif_type','title','message','link','created_at']
class DisciplinarySerializer(serializers.ModelSerializer):
    class Meta:
        model=DisciplinaryAction; fields='__all__'; read_only_fields=['issued_by','approved_by','legal_reviewed_by','legal_reviewed_at','is_approved','created_at']
class WomensProgramSerializer(serializers.ModelSerializer):
    class Meta: model=WomensProgram; fields='__all__'; read_only_fields=['created_by','created_at','updated_at']
class YouthProgramSerializer(serializers.ModelSerializer):
    class Meta: model=YouthProgram; fields='__all__'; read_only_fields=['created_by','created_at','updated_at']
class WelfareProgramSerializer(serializers.ModelSerializer):
    class Meta: model=WelfareProgram; fields='__all__'; read_only_fields=['created_by','created_at','updated_at']
class DonationSerializer(serializers.ModelSerializer):
    class Meta: model=Donation; fields='__all__'; read_only_fields=['verified_by','verified_at','recorded_by','recorded_at','created_at']
class ExpenseSerializer(serializers.ModelSerializer):
    class Meta: model=Expense; fields='__all__'; read_only_fields=['recorded_by','created_at']
class FinancialReportSerializer(serializers.ModelSerializer):
    class Meta: model=FinancialReport; fields='__all__'; read_only_fields=['prepared_by','created_at']

class GenericObjectSerializer(serializers.Serializer):
    pass
