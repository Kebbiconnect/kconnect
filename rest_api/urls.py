from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import views, dashboard_views, mobile_views
router=DefaultRouter()
router.register('events',mobile_views.EventViewSet,basename='events')
router.register('ward-meetings',mobile_views.WardMeetingViewSet,basename='ward-meetings')
urlpatterns=[
 path('',include(router.urls)),
 path('newsroom/',views.NewsroomListView.as_view(),name='newsroom-list'), path('newsroom/<slug:slug>/',views.NewsroomDetailView.as_view(),name='newsroom-detail'),
 path('opportunities/',views.OpportunityListView.as_view(),name='opportunity-list'), path('community/',views.CommunityInitiativeListView.as_view(),name='community-list'), path('civic/',views.CivicListView.as_view(),name='civic-list'), path('advocacy/',views.AdvocacyListView.as_view(),name='advocacy-list'), path('leadership-directory/',views.LeadershipDirectoryView.as_view(),name='leadership-directory'), path('patrons/',views.PatronListView.as_view(),name='patron-list'), path('impact/',views.ImpactMetricsView.as_view(),name='impact-metrics'),
 path('locations/zones/',views.ZoneListView.as_view()),path('locations/lgas/',views.LGAListView.as_view()),path('locations/wards/',views.WardListView.as_view()),path('roles/',views.RoleDefinitionListView.as_view()),
 path('auth/register/',views.RegisterView.as_view(),name='auth-register'),path('auth/login/',TokenObtainPairView.as_view(),name='auth-login'),path('auth/refresh/',TokenRefreshView.as_view(),name='auth-refresh'),path('auth/me/',views.MeView.as_view(),name='auth-me'),path('profile/',mobile_views.ProfileView.as_view()),path('profile/password/',mobile_views.PasswordChangeView.as_view()),
 path('members/',mobile_views.MemberListView.as_view()),path('members/pending/',mobile_views.PendingApplicantsView.as_view()),path('members/<int:pk>/',mobile_views.MemberDetailView.as_view()),path('members/<int:pk>/decision/',mobile_views.ApplicantDecisionView.as_view()),
 path('reports/',mobile_views.ReportListCreateView.as_view()),path('reports/<int:pk>/',mobile_views.ReportDetailView.as_view()),path('reports/<int:pk>/review/',mobile_views.ReportReviewView.as_view()),path('reports/<int:pk>/escalate/',mobile_views.ReportEscalateView.as_view()),
 path('articles/mine/',mobile_views.MyArticleListCreateView.as_view()),path('articles/mine/<int:pk>/',mobile_views.MyArticleDetailView.as_view()),path('articles/<int:pk>/submit/',mobile_views.ArticleSubmitView.as_view()),path('articles/review/',mobile_views.EditorialQueueView.as_view()),path('articles/<int:pk>/decision/',mobile_views.EditorialDecisionView.as_view()),
 path('media/mine/',mobile_views.MyMediaView.as_view()),path('media/mine/<int:pk>/',mobile_views.MyMediaDetailView.as_view()),path('media/review/',mobile_views.MediaReviewQueueView.as_view()),path('media/<int:pk>/decision/',mobile_views.MediaDecisionView.as_view()),
 path('devices/',mobile_views.DeviceRegistrationView.as_view()),path('devices/<int:pk>/',mobile_views.DeviceRemoveView.as_view()),path('notifications/',mobile_views.NotificationListView.as_view()),path('notifications/<int:pk>/read/',mobile_views.NotificationReadView.as_view()),path('notifications/read-all/',mobile_views.NotificationReadView.as_view()),
 path('programs/<str:kind>/',mobile_views.ProgramViewSet.as_view({'get':'list','post':'create'})),path('programs/<str:kind>/<int:pk>/',mobile_views.ProgramViewSet.as_view({'get':'retrieve','patch':'partial_update','put':'update','delete':'destroy'})),
 path('finance/summary/',mobile_views.FinanceSummaryView.as_view()),path('finance/donations/',mobile_views.DonationListCreateView.as_view()),path('finance/expenses/',mobile_views.ExpenseListCreateView.as_view()),
 path('discipline/',mobile_views.DisciplineListCreateView.as_view()),path('discipline/<int:pk>/decision/',mobile_views.DisciplineDecisionView.as_view()),
 path('manage/<str:kind>/',mobile_views.HubManagementViewSet.as_view({'get':'list','post':'create'})),path('manage/<str:kind>/<int:pk>/',mobile_views.HubManagementViewSet.as_view({'get':'retrieve','patch':'partial_update','put':'update','delete':'destroy'})),
 path('media/pipeline/',views.MediaPipelineView.as_view()),path('operations/oversight/',views.VPOversightView.as_view()),
 path('dashboards/secretariat/',dashboard_views.SecretariatDashboardView.as_view()),path('dashboards/finance/',dashboard_views.FinanceDashboardView.as_view()),path('dashboards/community/',dashboard_views.CommunityEngagementDashboardView.as_view()),path('dashboards/zone/',dashboard_views.ZonalDashboardView.as_view()),path('dashboards/lga/',dashboard_views.LgaDashboardView.as_view()),path('dashboards/ward/',dashboard_views.WardDashboardView.as_view()),
 path('schema/',SpectacularAPIView.as_view(),name='schema'),path('docs/',SpectacularSwaggerView.as_view(url_name='schema'),name='swagger-ui')]
