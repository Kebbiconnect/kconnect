"""Public Promise Tracker URLs — mounted at /promises/ in the root
URLconf. Kept separate from the editorial story-desk URLs (which live
under /story/) so the public surface stays small and reader-only.
"""
from django.urls import path

from . import views

app_name = 'promises'

urlpatterns = [
    path('', views.promise_list, name='list'),
    path('<int:promise_id>/', views.promise_detail, name='detail'),
]
