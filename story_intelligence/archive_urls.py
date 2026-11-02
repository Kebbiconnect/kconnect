"""Public Searchable Story Archive URLs — mounted at /archive/ in the
root URLconf (KPN Media Phase 3). Kept separate from the editorial
story-desk URLs (under /story/) and the Promise Tracker URLs (under
/promises/) so each public surface stays small and reader-only.
"""
from django.urls import path

from . import archive as archive_views

app_name = 'archive'

urlpatterns = [
    path('', archive_views.archive_home, name='home'),
]
