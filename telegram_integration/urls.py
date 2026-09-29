from django.urls import path
from . import views

app_name = 'telegram_integration'

urlpatterns = [
    # User-facing flow
    path('join/telegram/', views.telegram_connect, name='connect'),
    path('join/telegram/callback/', views.telegram_callback, name='callback'),
    path('join/telegram/verify/', views.telegram_verify, name='verify'),
    path('join/telegram/disconnect/', views.telegram_disconnect, name='disconnect'),
    path('join/telegram/bypass/', views.telegram_dev_bypass, name='dev_bypass'),
    
    # Webhook endpoint (Must be protected via secret token in request header, handled in views/webhook)
    path('telegram/webhook/', views.webhook_handler, name='webhook'),
]
