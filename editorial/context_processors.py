from django.conf import settings
from .access import active, editor

def editorial_navigation(request):
    user=request.user
    return {'editorial_available':bool(settings.KPN_EDITORIAL_ENABLED and active(user) and (editor(user) or user.role in {'LGA','ZONAL'}))}
