"""Public LGA news URLs — mounted at /newsroom/lga/ in the root
URLconf (Phase 7). A new URL family added alongside the existing
routes; no existing URL changes. Kept separate from the staff
intelligence URLs, mirroring intelligence.projects_urls.
"""
from django.urls import path

from . import lga_views

app_name = 'lga_news'

urlpatterns = [
    path('', lga_views.lga_index, name='index'),
    path('<slug:slug>/', lga_views.lga_detail, name='detail'),
]
