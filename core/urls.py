from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('leadership/', views.leadership, name='leadership'),
    path('profile/<int:user_id>/', views.view_profile, name='view_profile'),
    path('impact/', views.impact, name='impact'),
    path('opportunities/', views.opportunities, name='opportunities'),
    path('community/', views.community, name='community'),
    path('advocacy/', views.advocacy, name='advocacy'),
    path('civic/', views.civic, name='civic'),
    path('report-a-story/', views.report_a_story, name='report_a_story'),
    path('gallery/', views.gallery, name='gallery'),
    path('contact/', views.contact, name='contact'),
    path('support-us/', views.support_us, name='support_us'),
    path('faq/', views.faq, name='faq'),
    path('code-of-conduct/', views.code_of_conduct, name='code_of_conduct'),
    path('submit-report/', views.submit_report, name='submit_report'),
    path('review-report/<int:report_id>/', views.review_report, name='review_report'),
    path('network-rankings/', views.network_rankings, name='network_rankings'),
    path('notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
]
