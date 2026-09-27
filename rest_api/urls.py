
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import views

urlpatterns = [
    path('newsroom/', views.NewsroomListView.as_view(), name='newsroom-list'),
    path('newsroom/<slug:slug>/', views.NewsroomDetailView.as_view(), name='newsroom-detail'),
    path('opportunities/', views.OpportunityListView.as_view(), name='opportunity-list'),
    path('community/', views.CommunityInitiativeListView.as_view(), name='community-list'),
    path('civic/', views.CivicListView.as_view(), name='civic-list'),
    path('advocacy/', views.AdvocacyListView.as_view(), name='advocacy-list'),
    path('leadership-directory/', views.LeadershipDirectoryView.as_view(), name='leadership-directory'),
    path('patrons/', views.PatronListView.as_view(), name='patron-list'),
    path('impact/', views.ImpactMetricsView.as_view(), name='impact-metrics'),
    
    path('locations/zones/', views.ZoneListView.as_view(), name='zone-list'),
    path('locations/lgas/', views.LGAListView.as_view(), name='lga-list'),
    path('locations/wards/', views.WardListView.as_view(), name='ward-list'),
    
    path('roles/', views.RoleDefinitionListView.as_view(), name='role-list'),
    
    path('auth/register/', views.RegisterView.as_view(), name='auth-register'),
    path('auth/login/', TokenObtainPairView.as_view(), name='auth-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', views.MeView.as_view(), name='auth-me'),
    
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
