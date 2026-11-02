from django.urls import path

from . import views

app_name = 'story_intelligence'

urlpatterns = [
    path('<int:article_id>/', views.desk, name='desk'),
    path('<int:article_id>/profile/', views.save_profile, name='save_profile'),
    path('<int:article_id>/updates/', views.add_update, name='add_update'),
    path('<int:article_id>/updates/<int:update_id>/publish/', views.publish_update, name='publish_update'),
    path('<int:article_id>/updates/<int:update_id>/delete/', views.delete_draft_update, name='delete_draft_update'),
    path('<int:article_id>/claims/', views.add_claim, name='add_claim'),
    path('<int:article_id>/claims/<int:claim_id>/status/', views.change_claim_status, name='change_claim_status'),
    path('<int:article_id>/evidence/', views.add_evidence, name='add_evidence'),
    path('<int:article_id>/corrections/', views.add_correction, name='add_correction'),
    path('<int:article_id>/consent/', views.add_consent, name='add_consent'),
    path('<int:article_id>/verification/', views.set_verification, name='set_verification'),
    path('<int:article_id>/redact/', views.redact, name='redact'),
    # Phase 2 — Community Radar (story desk actions + radar desk)
    path('<int:article_id>/reports/link/', views.link_report, name='link_report'),
    path('<int:article_id>/reports/<int:link_id>/unlink/', views.unlink_report, name='unlink_report'),
    path('<int:article_id>/reports/<int:link_id>/claim/', views.claim_from_report, name='claim_from_report'),
    path('radar/', views.radar, name='radar'),
    path('radar/link/', views.radar_link, name='radar_link'),
    # Phase 2 — Promise desk (editorial)
    path('promises/', views.promise_desk, name='promise_desk'),
    path('promises/institutions/add/', views.add_institution, name='add_institution'),
    path('promises/create/', views.promise_create, name='promise_create'),
    path('promises/<int:promise_id>/', views.promise_detail_desk, name='promise_detail_desk'),
    path('promises/<int:promise_id>/save/', views.promise_save, name='promise_save'),
    path('promises/<int:promise_id>/updates/', views.promise_add_update, name='promise_add_update'),
    path('promises/<int:promise_id>/status/', views.promise_change_status, name='promise_change_status'),
    path('promises/<int:promise_id>/verification-claim/', views.promise_save_verification_claim, name='promise_save_verification_claim'),
]
