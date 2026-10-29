from django.urls import path
from . import brain_api, views
app_name='editorial'
urlpatterns=[
    path('',views.index,name='index'),
    path('items/<int:pk>/',views.detail,name='detail'),
    path('items/<int:pk>/action/',views.action,name='action'),
    path('control/',views.control,name='control'),
    path('sources/new/',views.source_edit,name='source_new'),
    path('sources/<int:pk>/',views.source_edit,name='source_edit'),
    path('jobs/<int:pk>/retry/',views.retry,name='retry'),
    path('brain/outbox/',brain_api.outbox,name='brain_outbox'),
    path('brain/inbox/',brain_api.inbox,name='brain_inbox'),
    path('brain/test-item/',brain_api.test_item,name='brain_test_item'),
    path('brain/submit-item/',brain_api.submit_item,name='brain_submit_item'),
    path('brain/telegram-kb/',brain_api.telegram_kb,name='brain_telegram_kb'),
    path('brain/telegram/post/',brain_api.telegram_post,name='brain_telegram_post'),
    path('brain/telegram/outbox/',brain_api.telegram_outbox,name='brain_telegram_outbox'),
    path('brain/telegram/drain/',brain_api.telegram_drain,name='brain_telegram_drain'),
    path('brain/telegram/questions/',brain_api.telegram_questions,name='brain_telegram_questions'),
    path('brain/telegram/answer/',brain_api.telegram_answer,name='brain_telegram_answer'),
]
