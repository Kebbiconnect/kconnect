"""Phase 6 fix round: the visual briefing page (structured sections,
holders-only security panel), the branded HTML email, and the
Telegram short summary (existing outbox machinery, configured staff
chats only, idempotent delivery records).
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from intelligence import alerts, briefings, security
from intelligence.models import Briefing, BriefingDelivery
from telegram_integration.models import BotOutbox

from .test_desk import categorise, locate, make_cluster, walk
from .test_processing import make_item
from .test_security_alerts_briefings import SECURITY_SLUG, SecurityFixture


class VisualBriefingFixture(SecurityFixture):
    """A populated day: one collected security item, verified at the
    desk, plus an incident with an attributed claim."""

    def populate(self):
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
        return cluster


class VisualBriefingViewTests(VisualBriefingFixture):
    def test_detail_renders_structured_sections_with_real_figures(self):
        self.populate()
        briefing = briefings.generate('DAILY', actor=self.director)
        self.assertEqual(len(briefing.data['sections']), 5)
        self.client.force_login(self.director)
        response = self.client.get(reverse(
            'intelligence:briefing_detail', args=[briefing.pk]))
        self.assertEqual(response.status_code, 200)
        # Headline figures and panel titles from the structured data.
        self.assertContains(response, 'Items collected')
        self.assertContains(response, 'Units verified')
        self.assertContains(response, 'Verification desk')
        self.assertContains(response, 'Promise &amp; project trackers')
        self.assertContains(response, 'Sources &amp; collection health')
        # Real breakdown content: category and LGA bars.
        self.assertContains(response, 'Security &amp; Public Safety')
        self.assertContains(response, 'By LGA (explicit mentions)')
        self.assertContains(response, 'Jega')
        # Not the old raw text blob: no title underline, and the
        # text-only section title never appears (the page uses the
        # short panel titles).
        self.assertNotContains(response, '=' * 20)
        self.assertNotContains(
            response, 'Security desk (restricted-safe summary)')

    def test_security_panel_is_holders_only_on_the_new_template(self):
        self.populate()
        briefing = briefings.generate('DAILY', actor=self.director)
        claim = 'People reported killed: 4 (reported by Daily Trust)'
        self.client.force_login(self.director)
        response = self.client.get(reverse(
            'intelligence:briefing_detail', args=[briefing.pk]))
        self.assertContains(response, 'Security desk')
        self.assertContains(response, claim)
        self.assertContains(response, 'Security units verified')
        # The Assistant Director holds VIEW_INTELLIGENCE_REPORTS but
        # is not a security holder (D6): no security panel at all.
        self.client.force_login(self.assistant)
        response = self.client.get(reverse(
            'intelligence:briefing_detail', args=[briefing.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, claim)
        self.assertNotContains(response, 'Security units verified')
        self.assertNotContains(response, 'Holders only')

    def test_empty_period_panels_are_honest(self):
        day = timezone.localdate() - timedelta(days=30)
        briefing = briefings.generate('DAILY', day=day)
        self.client.force_login(self.director)
        response = self.client.get(reverse(
            'intelligence:briefing_detail', args=[briefing.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response,
                            'No items were collected in this period.')
        self.assertContains(
            response, 'No security activity was recorded in this period.')
        self.assertContains(
            response, 'No activity was recorded in this period.')


class ShortSummaryTests(VisualBriefingFixture):
    def test_short_summary_composes_from_real_records_and_stays_short(self):
        self.populate()
        briefing = briefings.generate('DAILY', actor=self.director)
        text = briefings.short_text(briefing)
        self.assertEqual(text, briefing.telegram_text)
        lines = text.splitlines()
        self.assertLessEqual(len(lines), 9)
        self.assertLessEqual(len(text), 900)
        self.assertIn('Items collected: 1', text)
        self.assertIn('Verified at the desk: 1', text)
        self.assertIn(
            'Security verified: Bandits Attack Village Near Jega '
            '(Jega LGA)', text)
        # Figures never travel to Telegram; their status is flagged.
        self.assertIn('Reported casualty figures remain unverified '
                      'claims.', text)
        self.assertNotIn('People reported killed', text)
        self.assertNotIn(': 4', text)

    def test_short_summary_for_empty_period_is_honest(self):
        day = timezone.localdate() - timedelta(days=30)
        briefing = briefings.generate('DAILY', day=day)
        self.assertIn('No activity was recorded in this period.',
                      briefings.short_text(briefing))


class TelegramDeliveryTests(VisualBriefingFixture):
    def configure_chats(self, chat_ids='555123'):
        rule = alerts.get_rule('BRIEFING')
        rule.telegram_chat_ids = chat_ids
        rule.save()
        return rule

    def test_delivery_goes_through_outbox_to_configured_chats_only(self):
        self.populate()
        self.configure_chats()
        briefing = briefings.generate('DAILY', actor=self.director)
        with mock.patch(
                'telegram_integration.brain_service.send_outbox_row',
                return_value=True) as send:
            deliveries = briefings.send_telegram(briefing)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(len(deliveries), 1)
        delivery = deliveries[0]
        self.assertEqual(delivery.status, 'SENT')
        self.assertEqual(delivery.recipient, '555123')
        rows = BotOutbox.objects.filter(chat_id='555123')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().text, briefing.telegram_text)
        # Never the public channel: the only outbox row is the staff chat.
        self.assertEqual(BotOutbox.objects.count(), 1)

    def test_delivery_is_idempotent_per_briefing_and_chat(self):
        self.configure_chats()
        briefing = briefings.generate('DAILY', actor=self.director)
        with mock.patch(
                'telegram_integration.brain_service.send_outbox_row',
                return_value=True) as send:
            briefings.send_telegram(briefing)
            briefings.send_telegram(briefing)
            # Regenerating (without force) and re-sending changes nothing.
            briefings.generate('DAILY')
            briefings.send_telegram(briefing)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(BotOutbox.objects.count(), 1)
        self.assertEqual(
            BriefingDelivery.objects.filter(briefing=briefing).count(), 1)

    def test_unconfigured_chats_record_skipped_and_send_nothing(self):
        briefing = briefings.generate('DAILY', actor=self.director)
        deliveries = briefings.send_telegram(briefing)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].status, 'SKIPPED')
        self.assertIn('never sent to the public channel',
                      deliveries[0].error)
        self.assertEqual(BotOutbox.objects.count(), 0)
        # Re-clicking while still unconfigured stays a single record.
        briefings.send_telegram(briefing)
        self.assertEqual(
            BriefingDelivery.objects.filter(briefing=briefing).count(), 1)

    def test_failed_delivery_is_recorded_and_never_retried(self):
        self.configure_chats()
        briefing = briefings.generate('DAILY', actor=self.director)
        with mock.patch(
                'telegram_integration.brain_service.send_outbox_row',
                return_value=False) as send:
            deliveries = briefings.send_telegram(briefing)
            self.assertEqual(deliveries[0].status, 'FAILED')
            briefings.send_telegram(briefing)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(BotOutbox.objects.count(), 1)

    def test_dashboard_action_sends_and_redirects(self):
        self.configure_chats()
        briefing = briefings.generate('DAILY', actor=self.director)
        self.client.force_login(self.director)
        with mock.patch(
                'telegram_integration.brain_service.send_outbox_row',
                return_value=True):
            response = self.client.post(reverse(
                'intelligence:briefing_telegram', args=[briefing.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BriefingDelivery.objects.filter(
            briefing=briefing, status='SENT').exists())
        # The briefing page surfaces the exact text and its status.
        response = self.client.get(reverse(
            'intelligence:briefing_detail', args=[briefing.pk]))
        self.assertContains(response, 'Telegram short briefing')
        self.assertContains(response, 'Chat 555123')
        self.assertContains(response, 'Sent')

    def test_command_telegram_flag(self):
        self.configure_chats()
        with mock.patch(
                'telegram_integration.brain_service.send_outbox_row',
                return_value=True) as send:
            call_command('generate_briefing', period='daily',
                         telegram=True, verbosity=0)
        self.assertEqual(send.call_count, 1)
        briefing = Briefing.objects.get(period_kind='DAILY')
        self.assertTrue(BriefingDelivery.objects.filter(
            briefing=briefing, status='SENT').exists())


class BrandedEmailTests(VisualBriefingFixture):
    def test_email_carries_branded_html_and_text_alternative(self):
        self.populate()
        self.director.email = 'director@example.com'
        self.director.save(update_fields=['email'])
        briefing = briefings.generate('DAILY', actor=self.director)
        briefings.email_briefing(briefing)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        # Plain-text alternative is the stored body, unchanged.
        self.assertEqual(message.body, briefing.body)
        html_parts = [content for content, mimetype
                      in message.alternatives if mimetype == 'text/html']
        self.assertEqual(len(html_parts), 1)
        self.assertIn('KEBBI PROGRESSIVE YOUTH NETWORK', html_parts[0])
        self.assertIn('Security &amp; Public Safety', html_parts[0])
        self.assertIn('Items collected', html_parts[0])


class BriefingRuleConfigTests(TestCase):
    def test_briefing_rule_defaults_to_telegram_only(self):
        rule = alerts.get_rule('BRIEFING')
        self.assertEqual(rule.channels, ['TELEGRAM'])
        self.assertEqual(rule.recipient_capability,
                         'VIEW_INTELLIGENCE_REPORTS')
        self.assertEqual(rule.chat_id_list(), [])
