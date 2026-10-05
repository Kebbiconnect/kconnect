
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .auth import KpnTokenObtainPairSerializer,LoginIPThrottle,LoginUsernameThrottle,LogoutView,PasswordResetRequestView,PasswordResetConfirmView,PasswordChangeView
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import views
from . import dashboard_views
from . import workflow_views

urlpatterns = [
    path('newsroom/', views.NewsroomListView.as_view(), name='newsroom-list'),
    path('newsroom/<slug:slug>/', views.NewsroomDetailView.as_view(), name='newsroom-detail'),
    path('opportunities/', views.OpportunityListView.as_view(), name='opportunity-list'),
    path('opportunities/<slug:slug>/', views.OpportunityDetailView.as_view(), name='opportunity-detail'),
    path('community/', views.CommunityInitiativeListView.as_view(), name='community-list'),
    path('community/<int:pk>/', views.CommunityInitiativeDetailView.as_view(), name='community-detail'),
    path('civic/', views.CivicListView.as_view(), name='civic-list'),
    path('advocacy/', views.AdvocacyListView.as_view(), name='advocacy-list'),
    path('advocacy/<int:pk>/', views.AdvocacyDetailView.as_view(), name='advocacy-detail'),
    path('leadership/', views.LeadershipSeatListView.as_view(), name='leadership-seats'),
    path('leadership-directory/', views.LeadershipDirectoryView.as_view(), name='leadership-directory'),
    path('patrons/', views.PatronListView.as_view(), name='patron-list'),
    path('patrons/<int:pk>/', views.PatronDetailView.as_view(), name='patron-detail'),
    path('impact/', views.ImpactMetricsView.as_view(), name='impact-metrics'),
    
    path('locations/zones/', views.ZoneListView.as_view(), name='zone-list'),
    path('locations/lgas/', views.LGAListView.as_view(), name='lga-list'),
    path('locations/wards/', views.WardListView.as_view(), name='ward-list'),
    
    path('roles/', views.RoleDefinitionListView.as_view(), name='role-list'),
    path('registration/vacant-roles/', views.RegistrationVacantRolesView.as_view(), name='registration-vacant-roles'),
    
    path('auth/register/', views.RegisterView.as_view(), name='auth-register'),
    path('auth/login/', TokenObtainPairView.as_view(serializer_class=KpnTokenObtainPairSerializer, throttle_classes=[LoginIPThrottle, LoginUsernameThrottle]), name='auth-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('profile/password/', PasswordChangeView.as_view(), name='password-change'),
    path('auth/me/', views.MeView.as_view(), name='auth-me'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('members/', views.MemberListView.as_view(), name='member-list'),
    path('members/pending/', views.PendingMemberListView.as_view(), name='member-pending'),
    path('members/<int:pk>/', views.MemberDetailView.as_view(), name='member-detail'),
    path('members/<int:pk>/decision/', views.MemberDecisionView.as_view(), name='member-decision'),
    path('reports/', views.ReportListCreateView.as_view(), name='report-list'),
    path('reports/recipient/', views.ReportRecipientView.as_view(), name='report-recipient'),
    path('reports/<int:pk>/', views.ReportDetailView.as_view(), name='report-detail'),
    path('reports/<int:pk>/review/', views.ReportReviewView.as_view(), name='report-review'),
    path('reports/<int:pk>/escalate/', views.ReportEscalateView.as_view(), name='report-escalate'),
    path('articles/mine/', views.MyArticleListCreateView.as_view(), name='article-mine'),
    path('articles/mine/<int:pk>/', views.MyArticleDetailView.as_view(), name='article-mine-detail'),
    path('articles/<int:pk>/submit/', views.ArticleSubmitView.as_view(), name='article-submit'),
    path('articles/review/', views.ArticleReviewListView.as_view(), name='article-review'),
    path('articles/<int:pk>/decision/', views.ArticleDecisionView.as_view(), name='article-decision'),
    path('media/mine/', views.MyMediaListCreateView.as_view(), name='media-mine'),
    path('media/review/', views.MediaReviewListView.as_view(), name='media-review'),
    path('media/<int:pk>/decision/', views.MediaDecisionView.as_view(), name='media-decision'),
    
    


    path('content/about/', workflow_views.PublicAboutView.as_view(), name='content-about'),
    path('content/contact/', workflow_views.PublicContactView.as_view(), name='content-contact'),
    path('content/support/', workflow_views.PublicSupportView.as_view(), name='content-support'),
    path('content/code-of-conduct/', workflow_views.PublicCodeView.as_view(), name='content-code'),
    path('content/faq/', workflow_views.PublicFAQView.as_view(), name='content-faq'),
    path('gallery/', workflow_views.PublicGalleryView.as_view(), name='gallery'),
    path('community-reports/', workflow_views.CommunityReportListCreateView.as_view(), name='community-report-list'),
    path('community-reports/<int:pk>/review/', workflow_views.CommunityReportDecisionView.as_view(), name='community-report-review'),
    path('reporters/', workflow_views.ReporterListView.as_view(), name='reporter-list'),
    path('reporters/<int:pk>/<str:action>/', workflow_views.ReporterActionView.as_view(), name='reporter-action'),
    path('announcements/', workflow_views.AnnouncementListCreateView.as_view(), name='announcement-list'),
    path('announcements/received/', workflow_views.ReceivedAnnouncementView.as_view(), name='announcement-received'),
    path('announcements/<int:pk>/', workflow_views.AnnouncementDetailView.as_view(), name='announcement-detail'),
    path('finance/donations/<int:pk>/verify/', workflow_views.DonationVerifyView.as_view(), name='donation-verify'),
    path('finance/donations/<int:pk>/record/', workflow_views.DonationRecordView.as_view(), name='donation-record'),
    path('finance/reports/', workflow_views.FinancialReportListCreateView.as_view(), name='financial-report-list'),
    path('audit-reports/', workflow_views.AuditReportListCreateView.as_view(), name='audit-report-list'),
    path('audit-reports/<int:pk>/submit/', workflow_views.AuditReportSubmitView.as_view(), name='audit-report-submit'),
    path('discipline/<int:pk>/legal-opinion/', workflow_views.LegalOpinionView.as_view(), name='discipline-legal-opinion'),
    path('outreach/', workflow_views.OutreachListCreateView.as_view(), name='outreach-list'),
    path('outreach/<int:pk>/', workflow_views.OutreachDetailView.as_view(), name='outreach-detail'),

    path('events/', workflow_views.EventListCreateView.as_view(), name='event-list'),
    path('events/<int:pk>/', workflow_views.EventDetailView.as_view(), name='event-detail'),
    path('events/<int:pk>/attendance/', workflow_views.EventAttendanceView.as_view(), name='event-attendance'),
    path('events/<int:pk>/minutes/', workflow_views.EventMinutesView.as_view(), name='event-minutes'),
    path('ward-meetings/', workflow_views.WardMeetingListCreateView.as_view(), name='ward-meeting-list'),
    path('programs/<str:kind>/', workflow_views.ProgramListCreateView.as_view(), name='program-list'),
    path('finance/summary/', workflow_views.FinanceSummaryView.as_view(), name='finance-summary'),
    path('finance/donations/', workflow_views.DonationListCreateView.as_view(), name='donation-list'),
    path('finance/expenses/', workflow_views.ExpenseListCreateView.as_view(), name='expense-list'),
    path('discipline/', workflow_views.DisciplineListCreateView.as_view(), name='discipline-list'),
    path('discipline/<int:pk>/decision/', workflow_views.DisciplineDecisionView.as_view(), name='discipline-decision'),
    path('notifications/', workflow_views.NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/read/', workflow_views.NotificationReadView.as_view(), name='notification-read'),
    path('notifications/read-all/', workflow_views.NotificationReadAllView.as_view(), name='notification-read-all'),
    path('devices/', workflow_views.DeviceListCreateView.as_view(), name='device-list'),
    path('devices/<int:pk>/', workflow_views.DeviceDetailView.as_view(), name='device-detail'),
    path('devices/deactivate/', workflow_views.DeviceDeactivateView.as_view(), name='device-deactivate'),
    path('telegram/status/', workflow_views.TelegramStatusView.as_view(), name='telegram-status'),
    path('telegram/link/', workflow_views.TelegramLinkView.as_view(), name='telegram-link'),
    path('telegram/disconnect/', workflow_views.TelegramDisconnectView.as_view(), name='telegram-disconnect'),

    # Track B: Role Dashboard APIs
    path('media/pipeline/', views.MediaPipelineView.as_view(), name='media-pipeline'),
    path('operations/oversight/', views.VPOversightView.as_view(), name='vp-oversight'),
    
    
    # Track B: Tier-Based Dashboard APIs
    path('dashboards/me/', dashboard_views.MyDashboardView.as_view(), name='dash-me'),
    path('dashboards/secretariat/', dashboard_views.SecretariatDashboardView.as_view(), name='dash-secretariat'),
    path('dashboards/finance/', dashboard_views.FinanceDashboardView.as_view(), name='dash-finance'),
    path('dashboards/community/', dashboard_views.CommunityEngagementDashboardView.as_view(), name='dash-community'),
    path('dashboards/zone/', dashboard_views.ZonalDashboardView.as_view(), name='dash-zone'),
    path('dashboards/lga/', dashboard_views.LgaDashboardView.as_view(), name='dash-lga'),
    path('dashboards/ward/', dashboard_views.WardDashboardView.as_view(), name='dash-ward'),
    
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
