"""Public Human Impact Files URLs — mounted at /impact/stories/ in
the root URLconf (the /impact/ address itself is core's long-standing
organisational impact page and is preserved untouched). Kept separate
from the editorial story-desk URLs so the public surface stays small
and reader-only.
"""
from django.urls import path

from . import impact_files

app_name = 'impact_files'

urlpatterns = [
    path('', impact_files.impact_list, name='list'),
]
