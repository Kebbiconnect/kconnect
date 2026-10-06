"""Firebase Cloud Messaging provider. Credentials stay server-side.

Set FIREBASE_CREDENTIALS_FILE to a Firebase service-account JSON path. The Android
`google-services.json` is intentionally not accepted because it is client config,
not a server credential.
"""
import logging
from django.conf import settings
logger=logging.getLogger(__name__)

def send_to_devices(devices, *, title, body, data=None):
    tokens=list(devices.filter(is_active=True,platform='ANDROID').values_list('token',flat=True))
    if not tokens:return {'sent':0,'failed':0,'configured':bool(getattr(settings,'FIREBASE_CREDENTIALS_FILE',''))}
    credential_file=getattr(settings,'FIREBASE_CREDENTIALS_FILE','')
    if not credential_file:
        logger.info('FCM not sent: FIREBASE_CREDENTIALS_FILE is not configured.')
        return {'sent':0,'failed':0,'configured':False}
    try:
        import firebase_admin
        from firebase_admin import credentials,messaging
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(credential_file))
        message=messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title,body=body),
            data={str(k):str(v) for k,v in (data or {}).items() if v is not None},
            android=messaging.AndroidConfig(priority='high',notification=messaging.AndroidNotification(channel_id='kpn_updates',icon='ic_notification')),
        )
        response=messaging.send_each_for_multicast(message)
        for token,result in zip(tokens,response.responses):
            if not result.success and result.exception and 'registration-token-not-registered' in str(result.exception).lower():
                devices.filter(token=token).update(is_active=False)
        return {'sent':response.success_count,'failed':response.failure_count,'configured':True}
    except Exception:
        logger.exception('FCM delivery failed')
        return {'sent':0,'failed':len(tokens),'configured':True}
