"""FCM transport. Credentials remain server-side; absent credentials degrade safely."""
import json, logging, os
from django.conf import settings
from django.utils import timezone
log=logging.getLogger(__name__)

def _firebase_app():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        return None
    if firebase_admin._apps: return firebase_admin.get_app()
    raw=getattr(settings,'FIREBASE_CREDENTIALS_JSON','')
    path=getattr(settings,'FIREBASE_CREDENTIALS_FILE','')
    if not raw and not path: return None
    cred=credentials.Certificate(json.loads(raw) if raw else path)
    return firebase_admin.initialize_app(cred)

def send_notification(notification):
    from core.models import DeviceRegistration, PushDelivery
    devices=DeviceRegistration.objects.filter(user=notification.user,is_active=True)
    app=_firebase_app()
    for device in devices:
        delivery=PushDelivery.objects.create(notification=notification,device=device)
        if app is None:
            delivery.status='FAILED'; delivery.error='FCM is not configured'; delivery.save(update_fields=['status','error']); continue
        try:
            from firebase_admin import messaging
            mid=messaging.send(messaging.Message(notification=messaging.Notification(title=notification.title,body=notification.message),data={'notification_id':str(notification.pk),'event':notification.event,'link':notification.link or ''},token=device.token),app=app)
            delivery.status='SENT'; delivery.provider_message_id=mid; delivery.sent_at=timezone.now(); delivery.save(update_fields=['status','provider_message_id','sent_at'])
        except Exception as exc:
            text=str(exc); delivery.status='INVALID' if 'registration-token' in text.lower() else 'FAILED'; delivery.error=text[:2000]; delivery.save(update_fields=['status','error'])
            if delivery.status=='INVALID': DeviceRegistration.objects.filter(pk=device.pk).update(is_active=False)
