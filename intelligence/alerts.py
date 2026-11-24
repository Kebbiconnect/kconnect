"""Alert engine (Phase 6 — Doc 03 §2.10, Doc 07 §4).

Rules fire :func:`fire` with a stable ``dedupe_key`` per event: the
Alert row is created once (unique key) and deliveries happen only on
that first firing, so re-running a trigger — a reprocessed item, a
repeated cycle evaluation, a retried scheduler — never alerts twice
for the same event.

Transports are the site's existing ones, reused, never rebuilt:

- Dashboard: ``core.Notification`` rows via ``core.notifications``
  for the active holders of the rule's recipient capability.
- Email: ``django.core.mail`` over the site's configured
  EMAIL_BACKEND (Lockally in production).
- Telegram: ``telegram_integration`` BotOutbox rows sent through the
  existing brain service — addressed ONLY to the staff chat IDs
  configured on the rule. Intelligence alerts never fall back to the
  public channel (Doc 07 §4): with no chat IDs configured the
  Telegram delivery is recorded SKIPPED, not rerouted.

A failed delivery is recorded FAILED with its error. Nothing in this
module retries a delivery.
"""
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from . import desk as desk_service
from .models import Alert, AlertDelivery, AlertRule, IntelligenceAudit

# Rule defaults, applied when a rule row is first created. Holders can
# reconfigure everything (enable/disable, channels, recipients) from
# the dashboard; the defaults only seed the first configuration.
RULE_DEFAULTS = {
    'SECURITY_VERIFIED': {
        'recipient_capability': 'HANDLE_SECURITY_ALERTS',
        'channels': ['DASHBOARD', 'EMAIL', 'TELEGRAM'],
    },
    'SENSITIVE_CONFIRMED': {
        'recipient_capability': 'HANDLE_SECURITY_ALERTS',
        'channels': ['DASHBOARD'],
    },
    'SOURCE_HEALTH_FAILED': {
        'recipient_capability': 'MANAGE_SOURCES',
        'channels': ['DASHBOARD', 'EMAIL'],
    },
    'CYCLE_MISSED': {
        'recipient_capability': 'MANAGE_SOURCES',
        'channels': ['DASHBOARD', 'EMAIL'],
    },
    'PROJECT_VERIFIED_ABANDONED': {
        'recipient_capability': 'VERIFY_PROJECTS',
        'channels': ['DASHBOARD', 'EMAIL'],
    },
    # Configuration only (Phase 6 fix): this row holds the staff
    # Telegram chat IDs for the briefing short summary. It is never
    # fired as an alert; briefings.send_telegram reads it.
    'BRIEFING': {
        'recipient_capability': 'VIEW_INTELLIGENCE_REPORTS',
        'channels': ['TELEGRAM'],
    },
}


def get_rule(key):
    defaults = RULE_DEFAULTS[key]
    rule, _created = AlertRule.objects.get_or_create(
        key=key, defaults=defaults)
    return rule


def recipient_users(rule):
    """Active staff holding the rule's recipient capability."""
    User = get_user_model()
    return [user for user in User.objects.filter(is_active=True)
            .order_by('username')
            if desk_service.has_capability(user, rule.recipient_capability)]


def _deliver_dashboard(alert, rule):
    from core.notifications import notify
    users = recipient_users(rule)
    if not users:
        AlertDelivery.objects.create(
            alert=alert, channel='DASHBOARD', recipient='',
            status='SKIPPED',
            error='No active staff hold the recipient capability.')
        return
    for user in users:
        delivery = AlertDelivery.objects.create(
            alert=alert, channel='DASHBOARD', recipient=user.get_username())
        try:
            notify(user, notif_type='WARNING', title=alert.title[:200],
                   message=alert.message, link=alert.link,
                   event=f'INTEL_{alert.kind}', target_type=alert.target_type,
                   target_id=alert.target_id, push=False)
            delivery.status = 'SENT'
            delivery.sent_at = timezone.now()
        except Exception as exc:  # recorded, never retried in a loop
            delivery.status = 'FAILED'
            delivery.error = (str(exc) or type(exc).__name__)[:300]
        delivery.save(update_fields=['status', 'error', 'sent_at'])


def _deliver_email(alert, rule):
    addresses = rule.email_list()
    if not addresses:
        AlertDelivery.objects.create(
            alert=alert, channel='EMAIL', recipient='', status='SKIPPED',
            error='No email recipients configured for this rule.')
        return
    for address in addresses:
        delivery = AlertDelivery.objects.create(
            alert=alert, channel='EMAIL', recipient=address)
        try:
            send_mail(alert.title[:300], alert.message, None, [address],
                      fail_silently=False)
            delivery.status = 'SENT'
            delivery.sent_at = timezone.now()
        except Exception as exc:
            delivery.status = 'FAILED'
            delivery.error = (str(exc) or type(exc).__name__)[:300]
        delivery.save(update_fields=['status', 'error', 'sent_at'])


def _deliver_telegram(alert, rule):
    chat_ids = rule.chat_id_list()
    if not chat_ids:
        AlertDelivery.objects.create(
            alert=alert, channel='TELEGRAM', recipient='', status='SKIPPED',
            error='No staff chat IDs configured; intelligence alerts '
                  'never use the public channel.')
        return
    from telegram_integration import brain_service
    from telegram_integration.models import BotOutbox
    text = f'{alert.title}\n\n{alert.message}'
    for chat_id in chat_ids:
        delivery = AlertDelivery.objects.create(
            alert=alert, channel='TELEGRAM', recipient=chat_id)
        try:
            row = BotOutbox.objects.create(
                kind='CUSTOM', chat_id=chat_id, text=text[:4000])
            if brain_service.send_outbox_row(row):
                delivery.status = 'SENT'
                delivery.sent_at = timezone.now()
            else:
                delivery.status = 'FAILED'
                delivery.error = (row.error or 'Telegram send failed.')[:300]
        except Exception as exc:
            delivery.status = 'FAILED'
            delivery.error = (str(exc) or type(exc).__name__)[:300]
        delivery.save(update_fields=['status', 'error', 'sent_at'])


_DELIVERERS = {
    'DASHBOARD': _deliver_dashboard,
    'EMAIL': _deliver_email,
    'TELEGRAM': _deliver_telegram,
}


def fire(kind, *, dedupe_key, title, message, target_type='',
         target_id=None, link=''):
    """Record an alert event once and deliver it per its rule.

    Returns the Alert. If the event was already recorded (same
    dedupe_key), the existing Alert is returned and NOTHING is
    delivered again. A disabled rule still records the event (so the
    moment is not lost from the log) but delivers nothing.
    """
    rule = get_rule(kind)
    alert, created = Alert.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={'rule': rule, 'kind': kind, 'title': title[:300],
                  'message': message, 'target_type': target_type,
                  'target_id': target_id, 'link': link[:300]})
    if not created:
        return alert
    IntelligenceAudit.objects.create(
        actor=None, action='ALERT_FIRED', target_type='Alert',
        target_id=alert.pk, detail={'kind': kind, 'rule_enabled': rule.enabled})
    if rule.enabled:
        for channel in rule.channels or []:
            deliverer = _DELIVERERS.get(channel)
            if deliverer is not None:
                deliverer(alert, rule)
    return alert


# ---------------------------------------------------------------------------
# Rule triggers
# ---------------------------------------------------------------------------

def _unit_target(unit):
    from .models import EventCluster
    if isinstance(unit, EventCluster):
        return 'EventCluster', 'cluster'
    return 'RawPublication', 'item'


def fire_security_verified(unit, decision):
    target_type, kind = _unit_target(unit)
    lga = desk_service.unit_lga(unit)
    category = desk_service.unit_category(unit)
    return fire(
        'SECURITY_VERIFIED',
        dedupe_key=f'security-verified:{target_type}:{unit.pk}'
                   f':decision:{decision.pk}',
        title=f'Security unit verified: {unit.title}',
        message=(f'A unit in the sensitive category '
                 f'“{category.label if category else "—"}”'
                 f'{" in " + lga.name + " LGA" if lga else ""} was verified '
                 f'at the desk (decision #{decision.pk}). It still needs '
                 f'the separate sensitive approval before any story work.'),
        target_type=target_type, target_id=unit.pk,
        link=reverse('intelligence:security_unit', args=[kind, unit.pk]))


def fire_sensitive_confirmed(publication):
    if publication.cluster_id:
        link = reverse('intelligence:security_unit',
                       args=['cluster', publication.cluster_id])
    else:
        link = reverse('intelligence:security_unit',
                       args=['item', publication.pk])
    return fire(
        'SENSITIVE_CONFIRMED',
        dedupe_key=f'sensitive-confirmed:item:{publication.pk}',
        title=f'Confirmed sensitive item: {publication.title}',
        message=(f'A newly collected item from {publication.source.name} '
                 f'was classified Confirmed in a sensitive category. '
                 f'It is visible only to security-desk holders.'),
        target_type='RawPublication', target_id=publication.pk,
        link=link or reverse('intelligence:security'))


def fire_project_verified_abandoned(project, milestone):
    return fire(
        'PROJECT_VERIFIED_ABANDONED',
        dedupe_key=f'project-verified-abandoned:{project.pk}'
                   f':milestone:{milestone.pk}',
        title=f'Project verified abandoned: {project.title}',
        message=(f'{project.project_code} — {project.title} '
                 f'({project.lga.name if project.lga else "Kebbi State"}) '
                 f'was moved to Verified abandoned on the public project '
                 f'tracker. The verification basis is recorded on the '
                 f'project timeline.'),
        target_type='Project', target_id=project.pk,
        link=reverse('projects:detail', args=[project.pk]))


def evaluate_cycle_alerts(now=None):
    """Fire the source-health and missed-cycle rules for today.

    Called at the end of every collection cycle and by the briefing
    command, so a scheduler-driven deployment evaluates these rules
    regularly. Idempotent per source per day / per day: re-evaluating
    never re-alerts.
    """
    from .cycle import cycle_health
    from .models import SourceHealth
    fired = []
    today = timezone.localdate(now) if now else timezone.localdate()
    for health in SourceHealth.objects.select_related('source').all():
        if health.state(now) != 'FAILING':
            continue
        fired.append(fire(
            'SOURCE_HEALTH_FAILED',
            dedupe_key=f'source-health-failed:{health.source_id}:{today}',
            title=f'Source failing: {health.source.name}',
            message=(f'{health.source.name} has failed '
                     f'{health.consecutive_failures} collection '
                     f'attempt(s) in a row. Last error: '
                     f'{health.last_error or "—"}'),
            target_type='Source', target_id=health.source_id,
            link=reverse('intelligence:sources')))
    health = cycle_health(now)
    if health['missed']:
        fired.append(fire(
            'CYCLE_MISSED',
            dedupe_key=f'cycle-missed:{today}',
            title='Collection cycle missed',
            message=(f'No completed collection cycle for '
                     f'{health["gap_minutes"]} minutes '
                     f'(expected every {health["expected_minutes"]} '
                     f'minutes). Check the external scheduler.'),
            target_type='CollectionRun',
            target_id=health['last_run'].pk if health['last_run'] else None,
            link=reverse('intelligence:overview')))
    return fired
