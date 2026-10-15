"""Firebase Cloud Messaging provider. Credentials stay server-side.

Set FIREBASE_CREDENTIALS_FILE to a Firebase service-account JSON path. The Android
`google-services.json` is intentionally not accepted because it is client config,
not a server credential.
"""
import logging
from django.conf import settings
logger=logging.getLogger(__name__)

def _push_preview(value, max_bytes):
    text=str(value)
    encoded=text.encode('utf-8')
    return text if len(encoded)<=max_bytes else encoded[:max_bytes-3].decode('utf-8',errors='ignore')+'…'

def send_to_devices(devices, *, title, body, data=None):
    rows=list(devices.filter(is_active=True,platform='ANDROID').values_list('token','user_id'))
    tokens=[token for token,user_id in rows]
    owners={}
    for token,user_id in rows:owners.setdefault(user_id,[]).append(token)
    if not tokens:
        logger.info('FCM dispatch skipped: no active Android device registrations for these recipients.')
        return {'sent':0,'failed':0,'configured':bool(getattr(settings,'FIREBASE_CREDENTIALS_FILE',''))}
    credential_file=getattr(settings,'FIREBASE_CREDENTIALS_FILE','')
    if not credential_file:
        logger.info('FCM not sent: FIREBASE_CREDENTIALS_FILE is not configured.')
        return {'sent':0,'failed':0,'configured':False}
    sent=failed=0
    try:
        import firebase_admin
        from firebase_admin import credentials,messaging
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(credential_file))
        # Data-only Android delivery lets the app check session and permission
        # before display; an OS auto-display payload bypasses those checks.
        payload={str(k):str(v) for k,v in (data or {}).items() if v is not None}
        payload.update(title=_push_preview(title,300),message=_push_preview(body,2000))
        for user_id,user_tokens in owners.items():
            scoped_payload=dict(payload,recipient_user_id=str(user_id))
            for offset in range(0,len(user_tokens),500):
                batch=user_tokens[offset:offset+500]
                message=messaging.MulticastMessage(tokens=batch,data=scoped_payload,android=messaging.AndroidConfig(priority='high'))
                response=messaging.send_each_for_multicast(message)
                sent+=response.success_count;failed+=response.failure_count
                if response.failure_count:
                    from collections import Counter
                    errors=Counter(getattr(result.exception, 'code', type(result.exception).__name__)
                                   for result in response.responses if not result.success)
                    logger.warning('FCM batch failed=%s sent=%s error_codes=%s', response.failure_count, response.success_count, dict(errors))
                invalid=[token for token,result in zip(batch,response.responses) if not result.success and result.exception and (type(result.exception).__name__=='UnregisteredError' or 'registration-token-not-registered' in str(result.exception).lower())]
                if invalid:devices.filter(token__in=invalid).update(is_active=False)
        logger.info('FCM dispatch completed: sent=%s failed=%s registered_devices=%s', sent, failed, len(tokens))
        return {'sent':sent,'failed':failed,'configured':True}
    except Exception:
        logger.exception('FCM delivery failed')
        return {'sent':sent,'failed':len(tokens)-sent,'configured':True}
