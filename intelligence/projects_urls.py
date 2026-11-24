"""Public Project Tracker URLs — mounted at /projects/ in the root
URLconf. Kept separate from the staff intelligence URLs (which live
under /editorial/intelligence/) so the public surface stays small
and reader-only, mirroring story_intelligence.promises_urls.
"""
from django.urls import path

from . import public_views

app_name = 'projects'

urlpatterns = [
    path('', public_views.project_list, name='list'),
    path('<int:project_id>/', public_views.project_detail, name='detail'),
]
