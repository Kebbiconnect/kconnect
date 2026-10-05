import hashlib
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes,force_str
from django.utils.http import urlsafe_base64_encode,urlsafe_base64_decode
from rest_framework import serializers,status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken,TokenError
from rest_framework.views import APIView
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
  if inactive: raise PermissionDenied(detail=serializers.ErrorDetail("This account has been dismissed.",code="account_dismissed"))
  data=super().validate(attrs)
  data["user"]={"id":self.user.id,"status":self.user.status,"role_title":role_title(self.user),"tier":self.user.role}
  return data

class LogoutView(APIView):
 def post(self,request):
  refresh=request.data.get("refresh")
  if not refresh: raise serializers.ValidationError({"refresh":"This field is required."})
  try: RefreshToken(refresh).blacklist()
  except TokenError: raise serializers.ValidationError({"refresh":"Invalid or expired refresh token."})
  return Response(status=status.HTTP_204_NO_CONTENT)

class PasswordResetRequestView(APIView):
 authentication_classes=[]; permission_classes=[]
 def post(self,request):
  email=str(request.data.get("email","")).strip().lower()
  if not email: raise serializers.ValidationError({"email":"This field is required."})
  user=User.objects.filter(email__iexact=email).first()
  if user:
   token=default_token_generator.make_token(user); uid=urlsafe_base64_encode(force_bytes(user.pk))
   site_url=getattr(settings,"SITE_URL","").rstrip('/') or "https://kpn.com.ng"
   link=f"{site_url}/account/reset-password/{uid}/{token}/"
   name=user.get_full_name() or user.username
   send_mail("KPN Password Reset Request",f"Hello {name},\n\nYou requested a password reset for your KPN account.\n\nClick the link below to set a new password:\n\n{link}\n\nThis link expires in 24 hours. If you did not request this reset, you can safely ignore this email.\n\nBest regards,\nKebbi Progressive Youth Network (KPN)\n{site_url}",settings.DEFAULT_FROM_EMAIL,[user.email],fail_silently=False)
  return Response({"message":"If an account with that email exists, password reset instructions have been sent."})

class PasswordResetConfirmView(APIView):
 authentication_classes=[]; permission_classes=[]
 def post(self,request):
  uid,token=request.data.get("uid"),request.data.get("token")
  password=request.data.get("new_password","")
  try: user=User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
  except (TypeError,ValueError,OverflowError,User.DoesNotExist): user=None
  if not user or not default_token_generator.check_token(user,token):
   raise serializers.ValidationError({"token":"Invalid or expired password reset token."})
  if len(password)<6: raise serializers.ValidationError({"new_password":"Password must be at least 6 characters long."})
  user.set_password(password); user.save(update_fields=["password"])
  return Response({"message":"Your password has been reset successfully."})

class PasswordChangeView(APIView):
 def post(self,request):
  old=request.data.get("old_password",""); new=request.data.get("new_password","")
  errors={}
  if not request.user.check_password(old): errors["old_password"]="Current password is incorrect."
  if len(new)<6: errors["new_password"]="Password must be at least 6 characters long."
  if errors: raise serializers.ValidationError(errors)
  request.user.set_password(new); request.user.save(update_fields=["password"])
  return Response(status=status.HTTP_204_NO_CONTENT)
