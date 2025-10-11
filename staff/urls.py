from django.urls import path
from . import views

app_name = 'staff'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    
    path('api/check-vacant-roles/', views.check_vacant_roles, name='check_vacant_roles'),
    path('api/get-lgas/', views.get_lgas_by_zone, name='get_lgas'),
    path('api/get-wards/', views.get_wards_by_lga, name='get_wards'),
    
    path('dashboards/president/', views.president_dashboard, name='president_dashboard'),
    path('approve-members/', views.approve_members, name='approve_members'),
    path('review-applicant/<int:user_id>/', views.review_applicant, name='review_applicant'),
    path('manage-staff/', views.manage_staff, name='manage_staff'),
    path('view-reports/', views.view_reports, name='view_reports'),
    path('disciplinary-actions/', views.disciplinary_actions, name='disciplinary_actions'),
    
    path('dashboards/media-director/', views.media_director_dashboard, name='media_director_dashboard'),
    path('dashboards/treasurer/', views.treasurer_dashboard, name='treasurer_dashboard'),
    path('dashboards/financial-secretary/', views.financial_secretary_dashboard, name='financial_secretary_dashboard'),
    path('dashboards/organizing-secretary/', views.organizing_secretary_dashboard, name='organizing_secretary_dashboard'),
    path('dashboards/general-secretary/', views.general_secretary_dashboard, name='general_secretary_dashboard'),
    path('dashboards/zonal-coordinator/', views.zonal_coordinator_dashboard, name='zonal_coordinator_dashboard'),
    path('dashboards/lga-coordinator/', views.lga_coordinator_dashboard, name='lga_coordinator_dashboard'),
    path('dashboards/ward-coordinator/', views.ward_coordinator_dashboard, name='ward_coordinator_dashboard'),
]
