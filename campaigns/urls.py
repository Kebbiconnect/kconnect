from django.urls import path
from . import views

app_name = 'campaigns'

urlpatterns = [
    path('create/', views.create_campaign, name='create_campaign'),
    path('my-campaigns/', views.my_campaigns, name='my_campaigns'),
    path('edit/<int:campaign_id>/', views.edit_campaign, name='edit_campaign'),
    path('delete/<int:campaign_id>/', views.delete_campaign, name='delete_campaign'),
    path('submit/<int:campaign_id>/', views.submit_for_approval, name='submit_for_approval'),
    
    path('approval-queue/', views.approval_queue, name='approval_queue'),
    path('approve/<int:campaign_id>/', views.approve_campaign, name='approve_campaign'),
    path('reject/<int:campaign_id>/', views.reject_campaign, name='reject_campaign'),
    
    path('all/', views.all_campaigns, name='all_campaigns'),
    path('<slug:slug>/', views.view_campaign, name='view_campaign'),
]
