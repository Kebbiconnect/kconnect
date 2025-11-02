from django.urls import path
from . import views

app_name = 'media'

urlpatterns = [
    path('opinions/create/', views.create_opinion, name='create_opinion'),
    path('opinions/', views.my_opinions, name='my_opinions'),
    path('opinions/<int:pk>/edit/', views.edit_opinion, name='edit_opinion'),
    path('opinions/<int:pk>/delete/', views.delete_opinion, name='delete_opinion'),
]
