from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('leadership/', views.leadership, name='leadership'),
    path('campaigns/', views.campaigns, name='campaigns'),
    path('campaign/<slug:slug>/', views.campaign_detail, name='campaign_detail'),
    path('gallery/', views.gallery, name='gallery'),
    path('contact/', views.contact, name='contact'),
    path('support-us/', views.support_us, name='support_us'),
    path('faq/', views.faq, name='faq'),
    path('code-of-conduct/', views.code_of_conduct, name='code_of_conduct'),
]
