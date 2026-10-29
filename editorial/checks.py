from django.conf import settings
from django.core.checks import Error, register

@register()
def editorial_configuration(app_configs,**kwargs):
    errors=[]
    value=settings.KPN_EDITORIAL_DAILY_DRAFTS
    if not 1<=value<=20:errors.append(Error('KPN_EDITORIAL_DAILY_DRAFTS must be between 1 and 20.',id='editorial.E001'))
    token=settings.KPN_EDITORIAL_BRAIN_TOKEN
    if token and len(token)<32:errors.append(Error('KPN_EDITORIAL_BRAIN_TOKEN is set but shorter than 32 characters; use a long random token.',id='editorial.E002'))
    return errors
