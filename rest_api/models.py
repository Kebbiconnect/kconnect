from django.conf import settings
from django.db import models
class DeviceRegistration(models.Model):
 PLATFORM_CHOICES=(("ANDROID","Android"),("IOS","iOS"),("WEB","Web"))
 user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="devices")
 token=models.CharField(max_length=512,unique=True)
 device_id=models.CharField(max_length=200,blank=True)
 platform=models.CharField(max_length=10,choices=PLATFORM_CHOICES,default="ANDROID")
 app_version=models.CharField(max_length=30,blank=True)
 is_active=models.BooleanField(default=True)
 created_at=models.DateTimeField(auto_now_add=True)
 updated_at=models.DateTimeField(auto_now=True)
 class Meta: ordering=["-updated_at"]
