from rest_framework import status
from rest_framework.exceptions import ValidationError,AuthenticationFailed,NotAuthenticated,PermissionDenied,Throttled,NotFound
from rest_framework.views import exception_handler

def _strings(value):
 if isinstance(value,list): return [str(x) for x in value]
 return [str(value)]

def api_exception_handler(exc,context):
 response=exception_handler(exc,context)
 if response is None: return None
 request=context.get("request"); request_id=getattr(request,"request_id",None)
 code="api_error"; message="Request failed."; details=None
 if isinstance(exc,ValidationError):
  code="validation_error"; fields={}; non_field=[]
  if isinstance(response.data,dict):
   for key,value in response.data.items():
    (non_field if key in {"non_field_errors","detail"} else fields.setdefault(key,[])).extend(_strings(value)) if key in {"non_field_errors","detail"} else None
    if key not in {"non_field_errors","detail"}: fields[key]=_strings(value)
  else: non_field=_strings(response.data)
  message=non_field[0] if non_field else "Please correct the highlighted fields."
  details={"fields":fields,"non_field":non_field}
 elif isinstance(exc,Throttled):
  code="throttled"; message=str(exc.detail); details={"retry_after_seconds":exc.wait}
 elif isinstance(exc,(AuthenticationFailed,NotAuthenticated)):
  code="authentication_failed"; message=str(exc.detail)
 elif isinstance(exc,PermissionDenied):
  codes=exc.get_codes(); code=codes if isinstance(codes,str) else "permission_denied"; message=str(exc.detail)
 elif isinstance(exc,NotFound): code="not_found"; message=str(exc.detail)
 elif response.status_code==409: code="conflict"; message=str(response.data)
 response.data={"error":{"code":code,"message":message,"details":details},"request_id":request_id}
 return response
