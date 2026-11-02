"""Public Future Signal URLs — mounted at /signals/ in the root
URLconf. Kept separate from the editorial story-desk URLs (which live
under /story/) so the public surface stays small and reader-only.
"""
from django.urls import path

from . import future_signal

app_name = 'signals'

urlpatterns = [
    path('', future_signal.signal_list, name='list'),
]
