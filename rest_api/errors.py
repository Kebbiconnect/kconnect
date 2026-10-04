from rest_framework.views import exception_handler
from rest_framework import status

def api_exception_handler(exc,context):
 response=exception_handler(exc,context)
 if response is None: return response
 codes={400:'validation_error',401:'authentication_failed',403:'permission_denied',404:'not_found',409:'conflict'}
 code=codes.get(response.status_code,'api_error')
 details=response.data
 message='Request failed.'
 if isinstance(details,dict) and 'detail' in details: message=str(details['detail']); details=None
 response.data={'error':{'code':code,'message':message,'details':details}}
 return response
