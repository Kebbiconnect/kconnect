from django.urls import path
from . import views

app_name = 'campaigns'

urlpatterns = [
    # Public Newsroom
    path('', views.newsroom, name='newsroom'),
    path('article/<slug:slug>/', views.article_detail, name='article_detail'),
    
    # CMS: Writers
    path('write/', views.write_article, name='write_article'),
    path('my-articles/', views.my_articles, name='my_articles'),
    path('edit/<int:article_id>/', views.edit_article, name='edit_article'),
    path('delete/<int:article_id>/', views.delete_article, name='delete_article'),
    path('submit-review/<int:article_id>/', views.submit_for_review, name='submit_for_review'),
    
    # CMS: Editors
    path('review-queue/', views.review_queue, name='review_queue'),
    path('publish/<int:article_id>/', views.publish_article, name='publish_article'),
    path('return/<int:article_id>/', views.return_article, name='return_article'),
    
    # APIs
    path('api/upload-image/', views.image_upload, name='image_upload'),
    path('api/get-wards/', views.get_wards_for_lga, name='get_wards_for_lga'),
    
    # Legacy aliases (to prevent broken links from other pages)
    path('create/', views.create_campaign, name='create_campaign'),
    path('my-campaigns/', views.my_campaigns, name='my_campaigns'),
    path('edit-legacy/<int:campaign_id>/', views.edit_campaign, name='edit_campaign'),
    path('delete-legacy/<int:campaign_id>/', views.delete_campaign, name='delete_campaign'),
    path('submit/<int:campaign_id>/', views.submit_for_approval, name='submit_for_approval'),
    path('approval-queue/', views.approval_queue, name='approval_queue'),
    path('approve/<int:campaign_id>/', views.approve_campaign, name='approve_campaign'),
    path('reject/<int:campaign_id>/', views.reject_campaign, name='reject_campaign'),
    path('all/', views.all_campaigns, name='all_campaigns'),
    path('<slug:slug>/', views.view_campaign, name='view_campaign'),
]
