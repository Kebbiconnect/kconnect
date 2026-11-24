from django.urls import path, register_converter

from . import views


class UnitKindConverter:
    regex = 'cluster|item'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(UnitKindConverter, 'unitkind')

app_name = 'intelligence'

urlpatterns = [
    path('', views.overview, name='overview'),
    path('items/', views.items, name='items'),
    path('items/<int:pk>/reclassify/', views.item_reclassify, name='item_reclassify'),
    path('clusters/', views.clusters, name='clusters'),
    path('clusters/<int:pk>/', views.cluster_detail, name='cluster_detail'),
    path('desk/', views.desk, name='desk'),
    path('desk/cluster/<int:pk>/', views.desk_cluster, name='desk_cluster'),
    path('desk/item/<int:pk>/', views.desk_item, name='desk_item'),
    path('desk/<unitkind:kind>/<int:pk>/transition/', views.desk_transition, name='desk_transition'),
    path('desk/<unitkind:kind>/<int:pk>/assign/', views.desk_assign, name='desk_assign'),
    path('desk/<unitkind:kind>/<int:pk>/convert/', views.desk_convert, name='desk_convert'),
    path('desk/cluster/<int:pk>/merge/', views.desk_merge, name='desk_merge'),
    path('desk/cluster/<int:pk>/split/', views.desk_split, name='desk_split'),
    path('projects/', views.projects, name='projects'),
    path('projects/new/', views.project_new, name='project_new'),
    path('projects/from-<unitkind:kind>/<int:pk>/', views.project_from_unit, name='project_from_unit'),
    path('projects/<int:pk>/', views.project_detail, name='project_detail'),
    path('projects/<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('projects/<int:pk>/status/', views.project_status, name='project_status'),
    path('projects/<int:pk>/milestone/', views.project_milestone, name='project_milestone'),
    path('projects/<int:pk>/evidence/', views.project_evidence, name='project_evidence'),
    path('promise-candidates/', views.promise_candidates, name='promise_candidates'),
    path('promise-candidates/<int:pk>/confirm/', views.promise_candidate_confirm, name='promise_candidate_confirm'),
    path('promise-candidates/<int:pk>/dismiss/', views.promise_candidate_dismiss, name='promise_candidate_dismiss'),
    path('map/', views.tracking_map, name='map'),
    path('security/', views.security_desk, name='security'),
    path('security/<unitkind:kind>/<int:pk>/', views.security_unit, name='security_unit'),
    path('security/<unitkind:kind>/<int:pk>/transition/', views.security_transition, name='security_transition'),
    path('security/<unitkind:kind>/<int:pk>/working-copy/', views.security_working_copy, name='security_working_copy'),
    path('security/incidents/new/', views.security_incident_new, name='security_incident_new'),
    path('security/incidents/<int:pk>/', views.security_incident, name='security_incident'),
    path('security/incidents/<int:pk>/claim/', views.security_incident_claim, name='security_incident_claim'),
    path('security/incidents/<int:pk>/status/', views.security_incident_status, name='security_incident_status'),
    path('security/incidents/<int:pk>/redact/', views.security_incident_redact, name='security_incident_redact'),
    path('alerts/', views.alerts_list, name='alerts'),
    path('alerts/<int:pk>/read/', views.alert_mark_read, name='alert_mark_read'),
    path('alerts/rules/', views.alert_rules, name='alert_rules'),
    path('alerts/rules/<int:pk>/', views.alert_rule_edit, name='alert_rule_edit'),
    path('briefings/', views.briefings_list, name='briefings'),
    path('briefings/generate/', views.briefing_generate, name='briefing_generate'),
    path('briefings/<int:pk>/', views.briefing_detail, name='briefing_detail'),
    path('briefings/<int:pk>/email/', views.briefing_email, name='briefing_email'),
    path('briefings/<int:pk>/telegram/', views.briefing_telegram, name='briefing_telegram'),
    path('field/', views.field_report_new, name='field_report_new'),
    path('field/mine/', views.field_reports_mine, name='field_reports_mine'),
    path('article-locations/', views.article_locations, name='article_locations'),
    path('article-locations/<int:pk>/add/', views.article_location_add, name='article_location_add'),
    path('article-locations/<int:pk>/remove/', views.article_location_remove, name='article_location_remove'),
    path('sources/', views.sources, name='sources'),
    path('sources/new/', views.source_edit, name='source_new'),
    path('sources/<int:pk>/', views.source_edit, name='source_edit'),
    path('control/', views.control, name='control'),
    path('lgas/', views.lgas, name='lgas'),
    path('lgas/<int:pk>/', views.lga_detail, name='lga_detail'),
    path('lgas/<int:pk>/districts/new/', views.district_add, name='district_add'),
    path('lgas/<int:pk>/communities/new/', views.community_add, name='community_add'),
    path('aliases/', views.aliases, name='aliases'),
    path('aliases/<int:pk>/approve/', views.alias_review, {'decision': 'APPROVED'}, name='alias_approve'),
    path('aliases/<int:pk>/reject/', views.alias_review, {'decision': 'REJECTED'}, name='alias_reject'),
]
