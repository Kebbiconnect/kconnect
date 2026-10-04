"""
URL configuration for KPN project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import TemplateView
from django.conf.urls.static import static
from django.views.defaults import permission_denied

# Custom 403 handler — replaces Django's raw Forbidden page with a friendly KPN page.
# This is triggered by django-ratelimit's block=True and any other PermissionDenied exceptions.
def custom_403(request, exception=None):
    from django.template import loader
    from django.http import HttpResponseForbidden
    template = loader.get_template('403.html')
    return HttpResponseForbidden(template.render(request=request))

handler403 = custom_403

urlpatterns = [
    path('api/v1/', include('rest_api.urls')),
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('account/', include('staff.urls')),
    path('campaigns/', include('campaigns.urls')),
    path('events/', include('events.urls')),
    path('finance/', include('donations.urls')),
    path('media/', include(('media.urls', 'media'), namespace='media')),
    path('', include('telegram_integration.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
