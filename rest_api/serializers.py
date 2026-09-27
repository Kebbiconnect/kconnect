from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from campaigns.models import Campaign
from core.models import Opportunity, CommunityInitiative, AdvocacyCampaign, Patron
from leadership.models import Zone, LGA, Ward, RoleDefinition
from staff.models import User
from telegram_integration.models import TelegramMembership

class CampaignSerializer(serializers.ModelSerializer):
    date = serializers.DateTimeField(source='published_at')
    excerpt = serializers.CharField(source='subheadline')
    body = serializers.CharField(source='content')
    image = serializers.ImageField(source='featured_image')

    class Meta:
        model = Campaign
        fields = ['slug', 'title', 'date', 'excerpt', 'body', 'image']

class OpportunitySerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source='provider')
    external_apply_link = serializers.URLField(source='application_link')

    class Meta:
        model = Opportunity
        fields = ['title', 'category', 'organization', 'deadline', 'description', 'external_apply_link']

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
