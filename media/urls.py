from django.urls import path
from . import views

app_name = 'media'

urlpatterns = [
    path('create/', views.create_media, name='create_media'),
    path('my-media/', views.my_media, name='my_media'),
    path('<int:pk>/edit/', views.edit_media, name='edit_media'),
    path('<int:pk>/delete/', views.delete_media, name='delete_media'),
    
    # Media approval workflow (Director only)
    path('review/', views.review_media, name='review_media'),
    path('<int:pk>/approve/', views.approve_media, name='approve_media'),
    path('<int:pk>/reject/', views.reject_media, name='reject_media'),
    
    # Legacy URLs for backwards compatibility
    path('opinions/create/', views.create_media, name='create_opinion'),
    path('opinions/', views.my_media, name='my_opinions'),
    path('opinions/<int:pk>/edit/', views.edit_media, name='edit_opinion'),
    path('opinions/<int:pk>/delete/', views.delete_media, name='delete_opinion'),
]
