"""Minimal Render readiness: no account data or exception details."""
import logging
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def readiness(request):
    try:
        with connection.cursor() as cursor: cursor.execute('SELECT 1'); cursor.fetchone()
    except Exception as exc:
        logging.getLogger(__name__).error('Database readiness failed; error type=%s',type(exc).__name__)
        return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'ready'})
