import hashlib
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes,force_str
from django.utils.http import urlsafe_base64_encode,urlsafe_base64_decode
from rest_framework import serializers,status
from rest_framework.exceptions import PermissionDenied, APIException
import logging
logger = logging.getLogger(__name__)

class EmailDeliveryUnavailable(APIException):
 status_code = 503
 default_detail = "We could not deliver the reset email at this time. Please try again later or contact support."
 default_code = "email_delivery_unavailable"
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken,TokenError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from staff.models import User
from leadership.access import role_title

class LoginIPThrottle(SimpleRateThrottle):
 scope="auth_login"
 def get_cache_key(self,request,view): return self.cache_format%{"scope":self.scope,"ident":self.get_ident(request)}
class LoginUsernameThrottle(SimpleRateThrottle):
 scope="auth_login"
 def get_cache_key(self,request,view):
  username=str(request.data.get("username","")).strip().casefold()
  ident=hashlib.sha256(username.encode()).hexdigest() if username else self.get_ident(request)
  return self.cache_format%{"scope":self.scope,"ident":ident}

class KpnTokenObtainPairSerializer(TokenObtainPairSerializer):
 def validate(self,attrs):
  attrs[self.username_field]=str(attrs.get(self.username_field,"")).strip()
  inactive=User.objects.filter(username__iexact=attrs[self.username_field],is_active=False).first()
  if inactive and inactive.check_password(attrs.get("password", "")):
   message="This application has been rejected and archived. Contact KPN support." if inactive.status=="REJECTED" else "This account has been dismissed."
   raise PermissionDenied(detail=serializers.ErrorDetail(message,code="account_dismissed"))
  data=super().validate(attrs)
  data["user"]={"id":self.user.id,"status":self.user.status,"role_title":role_title(self.user),"tier":self.user.role}
  return data

class LogoutInputSerializer(serializers.Serializer):
 refresh=serializers.CharField(max_length=8192,trim_whitespace=False,write_only=True)

class LogoutView(APIView):
 def post(self,request):
  payload=LogoutInputSerializer(data=request.data);payload.is_valid(raise_exception=True)
  try: RefreshToken(payload.validated_data['refresh']).blacklist()
  except TokenError: raise serializers.ValidationError({"refresh":"Invalid or expired refresh token."})
  return Response(status=status.HTTP_204_NO_CONTENT)

class PasswordResetRequestView(APIView):
 authentication_classes=[]; permission_classes=[]
 def post(self,request):
  class ResetEmailSerializer(serializers.Serializer):
   email=serializers.EmailField(max_length=254)
  payload=ResetEmailSerializer(data=request.data);payload.is_valid(raise_exception=True)
  email=payload.validated_data['email'].strip().lower()
  user=User.objects.filter(email__iexact=email).first()
  if user:
   token=default_token_generator.make_token(user); uid=urlsafe_base64_encode(force_bytes(user.pk))
   site_url=getattr(settings,"SITE_URL","").rstrip('/') or "https://kpn.com.ng"
   link=f"{site_url}/account/reset-password/{uid}/{token}/"
   name=user.get_full_name() or user.username
   try:
    sent = send_mail("KPN Password Reset Request",f"Hello {name},\n\nYou requested a password reset for your KPN account.\n\nClick the link below to set a new password:\n\n{link}\n\nThis link expires in 24 hours. If you did not request this reset, you can safely ignore this email.\n\nBest regards,\nKebbi Progressive Youth Network (KPN)\n{site_url}",settings.DEFAULT_FROM_EMAIL,[user.email],fail_silently=False)
    if sent != 1:
     raise RuntimeError("Email provider did not accept the reset message.")
   except Exception as exc:
    logger.error("Password reset email delivery failed; error type=%s. Check Lockally configuration/provider dashboard.", type(exc).__name__)
    raise EmailDeliveryUnavailable() from None
  return Response({"message":"If an account with that email exists, password reset instructions have been sent."})

class PasswordResetConfirmInputSerializer(serializers.Serializer):
 uid=serializers.CharField(max_length=512,write_only=True)
 token=serializers.CharField(max_length=512,write_only=True)
 new_password=serializers.CharField(max_length=4096,trim_whitespace=False,write_only=True)

class PasswordResetConfirmView(APIView):
 authentication_classes=[]; permission_classes=[]
 def post(self,request):
  payload=PasswordResetConfirmInputSerializer(data=request.data);payload.is_valid(raise_exception=True)
  data=payload.validated_data
  try:user=User.objects.get(pk=force_str(urlsafe_base64_decode(data['uid'])))
  except (TypeError,ValueError,OverflowError,User.DoesNotExist):user=None
  if not user or not default_token_generator.check_token(user,data['token']):
   raise serializers.ValidationError({"token":"Invalid or expired password reset token."})
  try:validate_password(data['new_password'],user=user)
  except DjangoValidationError as exc:raise serializers.ValidationError({"new_password":exc.messages})
  user.set_password(data['new_password']);user.save(update_fields=['password'])
  return Response({"message":"Your password has been reset successfully."})


class PasswordChangeInputSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=4096
    )
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=4096
    )


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old = serializer.validated_data["old_password"]
        new = serializer.validated_data["new_password"]
        errors = {}
        if not request.user.check_password(old):
            errors["old_password"] = ["Current password is incorrect."]
        try:
            validate_password(new, user=request.user)
        except DjangoValidationError as exc:
            errors["new_password"] = exc.messages
        if errors:
            raise serializers.ValidationError(errors)
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)
