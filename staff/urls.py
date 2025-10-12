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
    path('disciplinary-actions/create/', views.create_disciplinary_action, name='create_disciplinary_action'),
    path('disciplinary-actions/<int:action_id>/approve/', views.approve_disciplinary_action, name='approve_disciplinary_action'),
    path('disciplinary-actions/<int:action_id>/reject/', views.reject_disciplinary_action, name='reject_disciplinary_action'),
    
    path('dashboards/media-director/', views.media_director_dashboard, name='media_director_dashboard'),
    path('dashboards/treasurer/', views.treasurer_dashboard, name='treasurer_dashboard'),
    path('dashboards/financial-secretary/', views.financial_secretary_dashboard, name='financial_secretary_dashboard'),
    path('dashboards/organizing-secretary/', views.organizing_secretary_dashboard, name='organizing_secretary_dashboard'),
    path('dashboards/general-secretary/', views.general_secretary_dashboard, name='general_secretary_dashboard'),
    path('dashboards/zonal-coordinator/', views.zonal_coordinator_dashboard, name='zonal_coordinator_dashboard'),
    path('dashboards/lga-coordinator/', views.lga_coordinator_dashboard, name='lga_coordinator_dashboard'),
    path('dashboards/ward-coordinator/', views.ward_coordinator_dashboard, name='ward_coordinator_dashboard'),
    
    path('dashboards/vice-president/', views.vice_president_dashboard, name='vice_president_dashboard'),
    path('dashboards/assistant-general-secretary/', views.assistant_general_secretary_dashboard, name='assistant_general_secretary_dashboard'),
    path('dashboards/state-supervisor/', views.state_supervisor_dashboard, name='state_supervisor_dashboard'),
    path('dashboards/legal-ethics-adviser/', views.legal_ethics_adviser_dashboard, name='legal_ethics_adviser_dashboard'),
    path('dashboards/director-of-mobilization/', views.director_of_mobilization_dashboard, name='director_of_mobilization_dashboard'),
    path('dashboards/assistant-director-of-mobilization/', views.assistant_director_of_mobilization_dashboard, name='assistant_director_of_mobilization_dashboard'),
    path('dashboards/assistant-organizing-secretary/', views.assistant_organizing_secretary_dashboard, name='assistant_organizing_secretary_dashboard'),
    path('dashboards/auditor-general/', views.auditor_general_dashboard, name='auditor_general_dashboard'),
    path('dashboards/welfare-officer/', views.welfare_officer_dashboard, name='welfare_officer_dashboard'),
    path('dashboards/youth-empowerment-officer/', views.youth_empowerment_officer_dashboard, name='youth_empowerment_officer_dashboard'),
    path('dashboards/women-leader/', views.women_leader_dashboard, name='women_leader_dashboard'),
    path('dashboards/assistant-women-leader/', views.assistant_women_leader_dashboard, name='assistant_women_leader_dashboard'),
    path('dashboards/assistant-media-director/', views.assistant_media_director_dashboard, name='assistant_media_director_dashboard'),
    path('dashboards/pr-officer/', views.pr_officer_dashboard, name='pr_officer_dashboard'),
    
    path('dashboards/zonal-secretary/', views.zonal_secretary_dashboard, name='zonal_secretary_dashboard'),
    path('dashboards/zonal-publicity-officer/', views.zonal_publicity_officer_dashboard, name='zonal_publicity_officer_dashboard'),
    
    path('dashboards/lga-secretary/', views.lga_secretary_dashboard, name='lga_secretary_dashboard'),
    path('dashboards/lga-organizing-secretary/', views.lga_organizing_secretary_dashboard, name='lga_organizing_secretary_dashboard'),
    path('dashboards/lga-treasurer/', views.lga_treasurer_dashboard, name='lga_treasurer_dashboard'),
    path('dashboards/lga-publicity-officer/', views.lga_publicity_officer_dashboard, name='lga_publicity_officer_dashboard'),
    path('dashboards/lga-supervisor/', views.lga_supervisor_dashboard, name='lga_supervisor_dashboard'),
    path('dashboards/lga-women-leader/', views.lga_women_leader_dashboard, name='lga_women_leader_dashboard'),
    path('dashboards/lga-welfare-officer/', views.lga_welfare_officer_dashboard, name='lga_welfare_officer_dashboard'),
    path('dashboards/lga-contact-mobilization/', views.lga_contact_mobilization_dashboard, name='lga_contact_mobilization_dashboard'),
    path('dashboards/lga-adviser/', views.lga_adviser_dashboard, name='lga_adviser_dashboard'),
    
    path('dashboards/ward-secretary/', views.ward_secretary_dashboard, name='ward_secretary_dashboard'),
    path('dashboards/ward-organizing-secretary/', views.ward_organizing_secretary_dashboard, name='ward_organizing_secretary_dashboard'),
    path('dashboards/ward-treasurer/', views.ward_treasurer_dashboard, name='ward_treasurer_dashboard'),
    path('dashboards/ward-publicity-officer/', views.ward_publicity_officer_dashboard, name='ward_publicity_officer_dashboard'),
    path('dashboards/ward-financial-secretary/', views.ward_financial_secretary_dashboard, name='ward_financial_secretary_dashboard'),
    path('dashboards/ward-supervisor/', views.ward_supervisor_dashboard, name='ward_supervisor_dashboard'),
    path('dashboards/ward-adviser/', views.ward_adviser_dashboard, name='ward_adviser_dashboard'),
    
    path('edit-member/<int:user_id>/', views.edit_member_role, name='edit_member_role'),
    path('promote-member/<int:user_id>/', views.promote_member, name='promote_member'),
    path('demote-member/<int:user_id>/', views.demote_member, name='demote_member'),
    path('dismiss-member/<int:user_id>/', views.dismiss_member, name='dismiss_member'),
    path('suspend-member/<int:user_id>/', views.suspend_member, name='suspend_member'),
    path('reinstate-member/<int:user_id>/', views.reinstate_member, name='reinstate_member'),
    path('swap-positions/', views.swap_positions, name='swap_positions'),
]
