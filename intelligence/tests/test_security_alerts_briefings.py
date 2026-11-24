"""Phase 6: security desk (restricted handling, D6 holders, working
copy + redaction, attributed claims), the alert engine (idempotency,
existing transports, recorded failures) and template briefings.

Everything runs on local fixtures — network transports are mocked at
their boundaries (the Telegram brain service, django.core.mail).
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Notification
from editorial.tests.helpers import (
    assistant_media, general_member, make_user, media_director, president,
)
from intelligence import alerts, briefings, desk, relevance, security
from intelligence.models import (
    Alert, AlertDelivery, AlertRule, Briefing, CollectionRun,
    EventCluster, IncidentClaim, IntelligenceAudit, IntelligenceCategory,
    PublicationCategory, PublicationLocation, RawPublication,
    SecurityIncident, SourceHealth,
)
from leadership.capabilities import capabilities_for
from leadership.models import LGA
from telegram_integration.models import BotOutbox

from .helpers import seed_directory
from .test_desk import categorise, locate, make_cluster, walk
from .test_processing import make_item, make_source

SECURITY_SLUG = 'security-public-safety'


class SecurityFixture(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('sec_director')
        self.president = president('sec_president')
        self.assistant = assistant_media('sec_assistant')
        self.secretary = make_user(
            'sec_gs', title='General Secretary')
        self.member = general_member('sec_member')
        self.source = make_source('Security Fixture Source')
        self.jega = LGA.objects.get(name='Jega')

    def make_restricted_cluster(self, title='Bandits Attack Village Near Jega'):
        pubs = []
        for index in range(2):
            pub = make_item(
                self.source, f'{title} ({index + 1})',
                text=f'Report {index + 1}: gunmen attacked a village near '
                     f'Jega. The district head of the village confirmed '
                     f'the incident.',
                published_at=timezone.now() - timedelta(hours=index + 1))
            categorise(pub, SECURITY_SLUG)
            locate(pub, self.jega)
            pubs.append(pub)
        return make_cluster(pubs, slug=SECURITY_SLUG, lga=self.jega,
                            title=title)

    def make_plain_cluster(self):
        pub = make_item(
            self.source, 'Jega School Wins State Quiz',
            text='A school in Jega won the state quiz competition.',
            published_at=timezone.now())
        categorise(pub, 'education')
        locate(pub, self.jega)
        return make_cluster([pub], slug='education', lga=self.jega)


class HolderMappingTests(SecurityFixture):
    """D6: exactly two titles hold the security-desk capabilities."""

    def test_director_and_president_are_the_only_holders(self):
        for user in (self.director, self.president):
            caps = capabilities_for(user)
            self.assertIn('VIEW_SECURITY_DESK', caps)
            self.assertIn('HANDLE_SECURITY_ALERTS', caps)

    def test_other_intelligence_roles_are_not_holders(self):
        for user in (self.assistant, self.secretary):
            caps = capabilities_for(user)
            self.assertNotIn('VIEW_SECURITY_DESK', caps)
            self.assertNotIn('HANDLE_SECURITY_ALERTS', caps)
        # The Assistant Director keeps the general intelligence caps.
        self.assertIn('REVIEW_INTELLIGENCE', capabilities_for(self.assistant))


class RestrictedVisibilityTests(SecurityFixture):
    def test_querysets_exclude_restricted_for_non_holders(self):
        restricted = self.make_restricted_cluster()
        plain = self.make_plain_cluster()
        for user in (self.assistant, self.secretary, self.member):
            self.assertNotIn(restricted, list(
                security.visible_clusters(user, EventCluster.objects.all())))
            self.assertIn(plain, list(
                security.visible_clusters(user, EventCluster.objects.all())))
        for user in (self.director, self.president):
            self.assertIn(restricted, list(
                security.visible_clusters(user, EventCluster.objects.all())))

    def test_items_queryset_excludes_restricted_items(self):
        cluster = self.make_restricted_cluster()
        member_item = cluster.publications.first()
        self.assertNotIn(member_item, list(security.visible_items(
            self.assistant, RawPublication.objects.all())))
        self.assertIn(member_item, list(security.visible_items(
            self.president, RawPublication.objects.all())))

    def test_desk_queue_hides_restricted_from_assistant(self):
        restricted = self.make_restricted_cluster()
        self.client.force_login(self.assistant)
        response = self.client.get(reverse('intelligence:desk'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, restricted.title)

    def test_direct_urls_404_for_non_holder(self):
        restricted = self.make_restricted_cluster()
        self.client.force_login(self.assistant)
        for name, args in (
                ('intelligence:desk_cluster', [restricted.pk]),
                ('intelligence:cluster_detail', [restricted.pk])):
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 404, name)

    def test_items_and_clusters_pages_hide_restricted(self):
        restricted = self.make_restricted_cluster()
        self.client.force_login(self.assistant)
        for name in ('intelligence:items', 'intelligence:clusters'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            self.assertNotContains(response, restricted.title)

    def test_overview_counts_exclude_restricted_for_non_holder(self):
        self.make_restricted_cluster()
        self.make_plain_cluster()
        self.client.force_login(self.assistant)
        response = self.client.get(reverse('intelligence:overview'))
        # Two restricted member items + one plain item exist; the
        # assistant's overview counts only the plain one.
        self.assertEqual(response.context['raw_items_total'], 1)
        self.assertEqual(response.context['cluster_total'], 1)
        self.client.force_login(self.director)
        response = self.client.get(reverse('intelligence:overview'))
        self.assertEqual(response.context['raw_items_total'], 3)
        self.assertEqual(response.context['cluster_total'], 2)

    def test_security_desk_gate(self):
        self.make_restricted_cluster()
        self.client.force_login(self.assistant)
        self.assertEqual(
            self.client.get(reverse('intelligence:security')).status_code, 403)
        self.client.force_login(self.secretary)
        self.assertEqual(
            self.client.get(reverse('intelligence:security')).status_code, 403)
        for user in (self.director, self.president):
            self.client.force_login(user)
            response = self.client.get(reverse('intelligence:security'))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Bandits Attack Village Near Jega')

    def test_security_unit_view_is_audited(self):
        restricted = self.make_restricted_cluster()
        self.client.force_login(self.president)
        response = self.client.get(reverse(
            'intelligence:security_unit', args=['cluster', restricted.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='SECURITY_VIEW', target_id=restricted.pk).exists())


class RestrictedStateTests(SecurityFixture):
    def test_restrict_and_release(self):
        unit = self.make_restricted_cluster()
        desk.apply_transition(unit, self.director, 'RESTRICT')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'RESTRICTED')
        decision = unit.review_decisions.get(action='RESTRICT')
        self.assertEqual(decision.to_state, 'RESTRICTED')
        desk.apply_transition(unit, self.president, 'RELEASE')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'UNDER_REVIEW')

    def test_restrict_needs_holder_capability(self):
        unit = self.make_restricted_cluster()
        with self.assertRaises(PermissionDenied):
            desk.apply_transition(unit, self.assistant, 'RESTRICT')

    def test_restrict_refused_for_non_sensitive_unit(self):
        unit = self.make_plain_cluster()
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'RESTRICT')

    def test_mark_unverified_and_reopen(self):
        unit = self.make_restricted_cluster()
        walk(unit, self.assistant, 'VERIFIED')
        with self.assertRaises(desk.DeskError):
            desk.apply_transition(unit, self.director, 'MARK_UNVERIFIED')
        desk.apply_transition(
            unit, self.director, 'MARK_UNVERIFIED',
            note='The second source retracted its report.')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'UNVERIFIED')
        desk.apply_transition(unit, self.assistant, 'REOPEN')
        unit.refresh_from_db()
        self.assertEqual(unit.desk_state, 'VERIFICATION_IN_PROGRESS')


class WorkingCopyRedactionTests(SecurityFixture):
    PASSAGE = 'The district head of the village confirmed the incident.'

    def test_prepare_and_redact(self):
        unit = self.make_restricted_cluster()
        security.prepare_working_copy(unit, self.president)
        unit.refresh_from_db()
        self.assertIn(self.PASSAGE, unit.working_text)
        count = security.redact_passage(unit, self.director, self.PASSAGE)
        self.assertEqual(count, 2)
        unit.refresh_from_db()
        self.assertNotIn(self.PASSAGE, unit.working_text)
        self.assertIn(security.REDACTION_MARKER, unit.working_text)
        # The original evidence is untouched.
        for member in unit.publications.all():
            self.assertIn(self.PASSAGE, member.text)
        # The audit row never carries the redacted text.
        audit = IntelligenceAudit.objects.get(action='SECURITY_REDACTION')
        self.assertNotIn('district head', str(audit.detail))
        self.assertEqual(audit.detail['occurrences'], 2)

    def test_redaction_needs_holder(self):
        unit = self.make_restricted_cluster()
        with self.assertRaises(PermissionDenied):
            security.prepare_working_copy(unit, self.assistant)

    def test_conversion_uses_redacted_working_copy(self):
        unit = self.make_restricted_cluster()
        security.prepare_working_copy(unit, self.director)
        security.redact_passage(unit, self.director, self.PASSAGE)
        walk(unit, self.director, 'APPROVED')
        article = desk.convert_to_draft(unit, self.director)
        self.assertNotIn(self.PASSAGE, article.content)
        self.assertIn(security.REDACTION_MARKER, article.content)
        for member in unit.publications.all():
            self.assertIn(self.PASSAGE, member.text)


class IncidentClaimTests(SecurityFixture):
    def make_incident(self):
        return security.create_incident(
            self.director, title='Attack on Village Near Jega',
            incident_type='Armed attack', lga=self.jega,
            location_text='A village area in Jega LGA')

    def test_no_granular_location_or_fact_figure_fields(self):
        field_names = {field.name for field in SecurityIncident._meta.fields}
        for forbidden in ('ward', 'district', 'community', 'geo_entity',
                          'latitude', 'longitude', 'coordinates',
                          'troop_position', 'affected_count',
                          'casualty_count', 'death_toll'):
            self.assertNotIn(forbidden, field_names)
        self.assertIn('lga', field_names)

    def test_claim_is_stored_and_shown_only_as_attributed(self):
        incident = self.make_incident()
        claim = security.add_claim(
            self.director, incident, label='People reported killed',
            count=4, source_name='Daily Trust',
            source_url='https://example.com/report')
        self.assertEqual(
            claim.attribution,
            'People reported killed: 4 (reported by Daily Trust)')
        self.client.force_login(self.president)
        response = self.client.get(reverse(
            'intelligence:security_incident', args=[incident.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reported by Daily Trust')
        self.assertContains(response, 'never shown as verified facts')

    def test_incident_pages_are_holder_only(self):
        incident = self.make_incident()
        self.client.force_login(self.assistant)
        self.assertEqual(self.client.get(reverse(
            'intelligence:security_incident', args=[incident.pk])).status_code,
            403)

    def test_incident_notes_redaction(self):
        incident = self.make_incident()
        incident.working_notes = 'The convoy passed through Jega at dawn.'
        incident.save(update_fields=['working_notes'])
        security.redact_incident_notes(
            self.director, incident, 'passed through Jega at dawn')
        incident.refresh_from_db()
        self.assertNotIn('dawn', incident.working_notes)
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='SECURITY_REDACTION',
            target_type='SecurityIncident').exists())


class AlertEngineTests(SecurityFixture):
    def fire_once(self, **overrides):
        kwargs = dict(
            dedupe_key='test:event:1', title='Test alert',
            message='Something happened.', target_type='Project',
            target_id=1)
        kwargs.update(overrides)
        return alerts.fire('PROJECT_VERIFIED_ABANDONED', **kwargs)

    def configure(self, key, **fields):
        rule = alerts.get_rule(key)
        for name, value in fields.items():
            setattr(rule, name, value)
        rule.save()
        return rule

    def test_dashboard_delivery_to_capability_holders_once(self):
        self.configure('PROJECT_VERIFIED_ABANDONED', channels=['DASHBOARD'])
        auditor = make_user('alert_auditor',
                            title='Director of Audit & Accountability')
        alert = self.fire_once()
        deliveries = alert.deliveries.filter(channel='DASHBOARD')
        recipients = {d.recipient for d in deliveries}
        # VERIFY_PROJECTS holders: the Director of Media and the
        # Audit Director. The Assistant (no VERIFY_PROJECTS) is not one.
        self.assertEqual(recipients, {'sec_director', 'alert_auditor'})
        self.assertTrue(all(d.status == 'SENT' for d in deliveries))
        self.assertEqual(Notification.objects.filter(
            user=auditor, event='INTEL_PROJECT_VERIFIED_ABANDONED').count(), 1)
        # Re-firing the same event delivers nothing again.
        again = self.fire_once()
        self.assertEqual(again.pk, alert.pk)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(deliveries.count(), 2)
        self.assertEqual(Notification.objects.filter(
            user=auditor, event='INTEL_PROJECT_VERIFIED_ABANDONED').count(), 1)

    def test_disabled_rule_records_but_delivers_nothing(self):
        self.configure('PROJECT_VERIFIED_ABANDONED', enabled=False,
                       channels=['DASHBOARD'])
        alert = self.fire_once()
        self.assertEqual(alert.deliveries.count(), 0)

    def test_email_failure_is_recorded_and_never_retried(self):
        self.configure('PROJECT_VERIFIED_ABANDONED', channels=['EMAIL'],
                       recipient_emails='desk@example.com')
        with mock.patch('intelligence.alerts.send_mail',
                        side_effect=RuntimeError('backend down')):
            alert = self.fire_once()
        delivery = alert.deliveries.get(channel='EMAIL')
        self.assertEqual(delivery.status, 'FAILED')
        self.assertIn('backend down', delivery.error)
        with mock.patch('intelligence.alerts.send_mail') as send:
            self.fire_once()
            send.assert_not_called()
        self.assertEqual(alert.deliveries.count(), 1)

    def test_email_delivery_uses_existing_backend(self):
        self.configure('PROJECT_VERIFIED_ABANDONED', channels=['EMAIL'],
                       recipient_emails='desk@example.com')
        self.fire_once()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['desk@example.com'])
        delivery = Alert.objects.get().deliveries.get(channel='EMAIL')
        self.assertEqual(delivery.status, 'SENT')

    def test_telegram_goes_only_to_configured_chat_ids(self):
        self.configure('SECURITY_VERIFIED', channels=['TELEGRAM'],
                       telegram_chat_ids='424242')
        with mock.patch(
                'telegram_integration.brain_service.send_outbox_row',
                return_value=True) as send:
            alert = alerts.fire(
                'SECURITY_VERIFIED', dedupe_key='sec:tg:1',
                title='Security alert', message='Verified unit.')
        row = BotOutbox.objects.get()
        self.assertEqual(row.chat_id, '424242')
        send.assert_called_once()
        delivery = alert.deliveries.get(channel='TELEGRAM')
        self.assertEqual(delivery.status, 'SENT')
        self.assertEqual(delivery.recipient, '424242')

    def test_telegram_without_chat_ids_is_skipped_never_channel(self):
        self.configure('SECURITY_VERIFIED', channels=['TELEGRAM'],
                       telegram_chat_ids='')
        alert = alerts.fire(
            'SECURITY_VERIFIED', dedupe_key='sec:tg:2',
            title='Security alert', message='Verified unit.')
        delivery = alert.deliveries.get(channel='TELEGRAM')
        self.assertEqual(delivery.status, 'SKIPPED')
        self.assertEqual(BotOutbox.objects.count(), 0)

    def test_security_verified_trigger_fires_once_per_decision(self):
        self.configure('SECURITY_VERIFIED', channels=['DASHBOARD'])
        unit = self.make_restricted_cluster()
        walk(unit, self.assistant, 'VERIFIED')
        alert = Alert.objects.get(kind='SECURITY_VERIFIED')
        self.assertIn('Bandits Attack Village Near Jega', alert.title)
        recipients = {d.recipient for d in
                      alert.deliveries.filter(channel='DASHBOARD')}
        # HANDLE_SECURITY_ALERTS holders (D6): Director + President.
        self.assertEqual(recipients, {'sec_director', 'sec_president'})

    def test_sensitive_confirmed_trigger_from_processing(self):
        self.configure('SENSITIVE_CONFIRMED', channels=['DASHBOARD'])
        make_item(
            self.source, 'Bandits Attack Village Near Jega',
            text='Bandits attacked a village near Jega on Monday. '
                 'Residents said gunmen arrived at night.',
            published_at=timezone.now())
        relevance.process_pending()
        alert = Alert.objects.get(kind='SENSITIVE_CONFIRMED')
        self.assertIn('Bandits Attack Village Near Jega', alert.title)
        # Reprocessing never re-alerts for the same item.
        relevance.process_pending()
        self.assertEqual(Alert.objects.filter(
            kind='SENSITIVE_CONFIRMED').count(), 1)

    def test_cycle_alerts_fire_once_per_day(self):
        self.configure('SOURCE_HEALTH_FAILED', channels=['DASHBOARD'])
        self.configure('CYCLE_MISSED', channels=['DASHBOARD'])
        SourceHealth.objects.create(
            source=self.source, consecutive_failures=2,
            last_error='Feed timeout')
        CollectionRun.objects.create(
            trigger='SCHEDULED', status='COMPLETED',
            started_at=timezone.now() - timedelta(hours=5),
            finished_at=timezone.now() - timedelta(hours=5))
        alerts.evaluate_cycle_alerts()
        self.assertEqual(Alert.objects.filter(
            kind='SOURCE_HEALTH_FAILED').count(), 1)
        self.assertEqual(Alert.objects.filter(
            kind='CYCLE_MISSED').count(), 1)
        alerts.evaluate_cycle_alerts()
        self.assertEqual(Alert.objects.count(), 2)

    def test_project_verified_abandoned_trigger(self):
        from intelligence import projects as project_service
        self.configure('PROJECT_VERIFIED_ABANDONED', channels=['DASHBOARD'])
        auditor = make_user('alert_auditor2',
                            title='Director of Audit & Accountability')
        project = project_service.create_project(
            self.director, title='Abandoned Clinic Project',
            description='A clinic project in Jega.', sector='HEALTH',
            category='HOSPITAL', lga=self.jega)
        project_service.add_evidence(
            project, self.director, kind='FIELD_INSPECTION',
            title='Field inspection, November 2026',
            verification_state='DOCUMENTED',
            captured_at=timezone.now())
        project_service.set_project_status(
            project, 'VERIFIED_ABANDONED', auditor)
        self.assertEqual(Alert.objects.filter(
            kind='PROJECT_VERIFIED_ABANDONED').count(), 1)

    def test_alerts_list_and_rule_configuration_views(self):
        self.configure('PROJECT_VERIFIED_ABANDONED', channels=['DASHBOARD'])
        self.fire_once()
        self.client.force_login(self.director)
        response = self.client.get(reverse('intelligence:alerts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test alert')
        delivery = AlertDelivery.objects.get(
            channel='DASHBOARD', recipient='sec_director')
        response = self.client.post(reverse(
            'intelligence:alert_mark_read', args=[delivery.pk]))
        self.assertEqual(response.status_code, 302)
        delivery.refresh_from_db()
        self.assertTrue(delivery.is_read)
        # Rule configuration is for MANAGE_SOURCES holders.
        self.client.force_login(self.assistant)
        self.assertEqual(self.client.get(
            reverse('intelligence:alert_rules')).status_code, 403)
        self.client.force_login(self.director)
        response = self.client.get(reverse('intelligence:alert_rules'))
        self.assertEqual(response.status_code, 200)
        rule = AlertRule.objects.get(key='PROJECT_VERIFIED_ABANDONED')
        response = self.client.post(
            reverse('intelligence:alert_rule_edit', args=[rule.pk]), {
                'enabled': '', 'channels': ['EMAIL'],
                'recipient_capability': 'VERIFY_PROJECTS',
                'recipient_emails': 'desk@example.com',
                'telegram_chat_ids': ''})
        self.assertEqual(response.status_code, 302)
        rule.refresh_from_db()
        self.assertFalse(rule.enabled)
        self.assertEqual(rule.channels, ['EMAIL'])


class BriefingTests(SecurityFixture):
    def test_empty_period_is_honest(self):
        day = timezone.localdate() - timedelta(days=30)
        briefing = briefings.generate('DAILY', day=day)
        self.assertIn('No activity was recorded in this period.',
                      briefing.body)

    def test_briefing_composes_only_real_records(self):
        item = make_item(
            self.source, 'Bandits Attack Village Near Jega',
            text='Bandits attacked a village near Jega.',
            published_at=timezone.now())
        categorise(item, SECURITY_SLUG)
        locate(item, self.jega)
        item.relevance = 'CONFIRMED'
        item.save(update_fields=['relevance'])
        cluster = make_cluster([item], slug=SECURITY_SLUG, lga=self.jega)
        walk(cluster, self.assistant, 'VERIFIED')
        incident = security.create_incident(
            self.director, title='Attack on Village Near Jega',
            incident_type='Armed attack', lga=self.jega)
        security.add_claim(
            self.director, incident, label='People reported killed',
            count=4, source_name='Daily Trust')
        briefing = briefings.generate('DAILY')
        self.assertIn('Items collected: 1', briefing.body)
        self.assertIn('Security & Public Safety: 1', briefing.body)
        self.assertIn('Jega: 1', briefing.body)
        self.assertIn('Verified: Bandits Attack Village Near Jega',
                      briefing.body)
        # The figure appears only as an attributed, unverified claim.
        self.assertIn('People reported killed: 4 (reported by Daily Trust)',
                      briefing.body)
        self.assertIn('unverified claim', briefing.body)

    def test_generate_is_idempotent_and_command_runs(self):
        call_command('generate_briefing', period='daily', verbosity=0)
        self.assertEqual(Briefing.objects.filter(
            period_kind='DAILY').count(), 1)
        call_command('generate_briefing', period='daily', verbosity=0)
        self.assertEqual(Briefing.objects.filter(
            period_kind='DAILY').count(), 1)
        call_command('generate_briefing', period='weekly', verbosity=0)
        self.assertEqual(Briefing.objects.filter(
            period_kind='WEEKLY').count(), 1)

    def test_email_briefing_uses_existing_backend(self):
        self.director.email = 'director@example.com'
        self.director.save(update_fields=['email'])
        briefing = briefings.generate('DAILY')
        briefings.email_briefing(briefing)
        briefing.refresh_from_db()
        self.assertTrue(briefing.email_status.startswith('Sent to'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('director@example.com', mail.outbox[0].to)

    def test_briefing_views_gated_by_reports_capability(self):
        briefing = briefings.generate('DAILY')
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(
            reverse('intelligence:briefings')).status_code, 403)
        self.client.force_login(self.assistant)
        self.assertEqual(self.client.get(
            reverse('intelligence:briefings')).status_code, 200)
        response = self.client.get(reverse(
            'intelligence:briefing_detail', args=[briefing.pk]))
        self.assertEqual(response.status_code, 200)
