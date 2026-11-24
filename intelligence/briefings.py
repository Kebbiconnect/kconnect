"""Briefings (Phase 6 — Doc 03 §2.10; visual fix round).

Template-composed from REAL records only: no AI, no invented
content, no filler. A briefing covers a day or a week and assembles
what the system's own records show for that period — collection by
LGA and category, desk decisions, a restricted-safe security summary
(counts and LGA-level headlines; any figure phrased as an attributed
report, never as fact), tracker changes, and source health.

Composition produces STRUCTURED section data first
(:func:`compose_data`); every rendering derives from that one data
set, so the dashboard page, the HTML email and the plain-text body
can never disagree:

- ``Briefing.body`` — the plain-text rendering (email text part).
- ``Briefing.data`` — the structured sections the dashboard page and
  the branded HTML email render.
- ``Briefing.telegram_text`` — the short summary delivered to staff
  Telegram chats through the existing BotOutbox machinery.

A period with no activity in a section marks that section empty; a
period with no activity at all says so in one honest line.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from leadership.capabilities import capabilities_for

from . import alerts as alert_service
from . import desk as desk_service
from .models import (
    Briefing, BriefingDelivery, CollectionRun, EventCluster,
    IntelligenceAudit, ProjectMilestone, PublicationCategory,
    PublicationLocation, RawPublication, ReviewDecision,
    SecurityIncident, SourceHealth,
)

_TZ = ZoneInfo(settings.TIME_ZONE)


def period_for(kind, day=None):
    """(start, end) dates for a DAILY or WEEKLY briefing."""
    day = day or timezone.localdate()
    if kind == 'WEEKLY':
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    return day, day


def _window(start, end):
    """Aware datetimes bounding the period (local time)."""
    return (datetime.combine(start, time.min, tzinfo=_TZ),
            datetime.combine(end + timedelta(days=1), time.min, tzinfo=_TZ))


def _site_url():
    return (getattr(settings, 'SITE_URL', '')
            or 'https://www.kpn.com.ng').rstrip('/')


# ---------------------------------------------------------------------------
# Structured section builders. Each returns (section, facts): the
# section is JSON-safe render data; facts feed the hero figures, the
# short summary and the health alert line.
# ---------------------------------------------------------------------------

def _collection_data(start_dt, end_dt):
    items = RawPublication.objects.filter(
        discovered_at__gte=start_dt, discovered_at__lt=end_dt)
    total = items.count()
    section = {
        'key': 'collection', 'title': 'Collection',
        'short_title': 'Collection', 'icon': 'fa-inbox',
        'restricted': False, 'empty': total == 0,
        'empty_text': 'No items were collected in this period.',
        'blocks': [],
    }
    if not total:
        return section, {'total': 0}
    blocks = [{'type': 'stats', 'items': [
        {'key': 'total', 'label': 'Items collected', 'value': total}]}]
    by_category = (
        PublicationCategory.objects.filter(
            is_primary=True,
            publication__discovered_at__gte=start_dt,
            publication__discovered_at__lt=end_dt)
        .values('category__label').annotate(n=Count('publication'))
        .order_by('-n', 'category__label'))
    if by_category:
        blocks.append({'type': 'bars', 'title': None, 'rows': [
            {'label': row['category__label'], 'count': row['n'],
             'pct': round(100 * row['n'] / total)}
            for row in by_category]})
    by_lga = (
        PublicationLocation.objects.filter(
            match_kind='EXPLICIT', lga__isnull=False,
            publication__discovered_at__gte=start_dt,
            publication__discovered_at__lt=end_dt)
        .values('lga__name')
        .annotate(n=Count('publication', distinct=True))
        .order_by('-n', 'lga__name'))
    if by_lga:
        top = max(row['n'] for row in by_lga)
        blocks.append({'type': 'bars',
                       'title': 'By LGA (explicit mentions)', 'rows': [
                           {'label': row['lga__name'], 'count': row['n'],
                            'pct': round(100 * row['n'] / top)}
                           for row in by_lga]})
    section['blocks'] = blocks
    return section, {'total': total}


def _desk_data(start_dt, end_dt):
    decisions = ReviewDecision.objects.filter(
        created_at__gte=start_dt, created_at__lt=end_dt)
    section = {
        'key': 'desk', 'title': 'Verification desk',
        'short_title': 'Verification desk', 'icon': 'fa-clipboard-check',
        'restricted': False, 'empty': True,
        'empty_text': 'No desk decisions were recorded in this period.',
        'blocks': [],
    }
    facts = {'verified': 0}
    if not decisions.exists():
        return section, facts
    counts = {row['action']: row['n'] for row in
              decisions.values('action').annotate(n=Count('pk'))}
    stats = [{'key': action, 'label': label, 'value': counts[action]}
             for action, label in [('TRIAGE', 'Triaged into review'),
                                   ('VERIFY', 'Verified'),
                                   ('APPROVE', 'Approved — ready'),
                                   ('PUBLISH', 'Published via the newsroom'),
                                   ('REJECT', 'Rejected'),
                                   ('MARK_DUPLICATE', 'Marked duplicate')]
             if counts.get(action)]
    verified = (decisions.filter(action='VERIFY')
                .select_related('cluster', 'publication')[:10])
    entries = [{'heading': decision.unit.title, 'detail': ''}
               for decision in verified if decision.unit is not None]
    blocks = []
    if stats:
        blocks.append({'type': 'stats', 'items': stats})
    if entries:
        blocks.append({'type': 'entries', 'title': None,
                       'prefix': 'Verified', 'separator': 'colon',
                       'items': entries})
    section['blocks'] = blocks
    section['empty'] = not blocks
    facts['verified'] = counts.get('VERIFY', 0)
    return section, facts


def _security_data(start_dt, end_dt):
    """Restricted-safe: counts + LGA-level headlines + attributed claims."""
    verified = (ReviewDecision.objects.filter(
        action='VERIFY', created_at__gte=start_dt,
        created_at__lt=end_dt)
        .select_related('cluster', 'publication'))
    headlines = []
    for decision in verified:
        unit = decision.unit
        if unit is None or not desk_service.unit_is_sensitive(unit):
            continue
        lga = desk_service.unit_lga(unit)
        headlines.append({
            'heading': unit.title,
            'detail': f'{lga.name} LGA' if lga else 'Kebbi State'})
    incidents = SecurityIncident.objects.filter(
        created_at__gte=start_dt, created_at__lt=end_dt)
    claims = []
    for incident in incidents.prefetch_related('claims'):
        for claim in incident.claims.all():
            claims.append(
                f'{claim.attribution} — an unverified claim, '
                f'not a confirmed figure.')
    restricted_now = (
        EventCluster.objects.filter(state='OPEN', desk_state='RESTRICTED').count()
        + RawPublication.objects.filter(
            cluster__isnull=True, desk_state='RESTRICTED').count())
    section = {
        'key': 'security',
        'title': 'Security desk (restricted-safe summary)',
        'short_title': 'Security desk', 'icon': 'fa-shield-halved',
        'restricted': True, 'empty': True,
        'empty_text': 'No security activity was recorded in this period.',
        'blocks': [],
    }
    facts = {'headlines': headlines, 'claims': bool(claims)}
    if not headlines and not incidents.exists() and not restricted_now:
        return section, facts
    blocks = []
    if headlines:
        blocks.append({'type': 'entries',
                       'title': 'Security units verified in this period',
                       'prefix': None, 'separator': 'paren',
                       'items': headlines})
    blocks.append({'type': 'stats', 'items': [
        {'key': 'incidents', 'label': 'Incidents opened in this period',
         'value': incidents.count()},
        {'key': 'restricted_now',
         'label': 'Units currently under restricted handling',
         'value': restricted_now}]})
    if claims:
        blocks.append({'type': 'notes',
                       'title': 'Figures reported by sources '
                                '(unverified claims)',
                       'items': claims})
    section['blocks'] = blocks
    section['empty'] = False
    return section, facts


def _tracker_data(start_dt, end_dt):
    from story_intelligence.models import Promise, PromiseUpdate
    section = {
        'key': 'trackers', 'title': 'Promise & project trackers',
        'short_title': 'Promise & project trackers',
        'icon': 'fa-scale-balanced',
        'restricted': False, 'empty': True,
        'empty_text': 'No promise or project changes were recorded '
                      'in this period.',
        'blocks': [],
    }
    new_promises = Promise.objects.filter(
        created_at__gte=start_dt, created_at__lt=end_dt).count()
    updates = PromiseUpdate.objects.filter(
        created_at__gte=start_dt, created_at__lt=end_dt)
    update_entries = [
        {'heading': update.promise.title,
         'detail': update.get_status_after_display()}
        for update in updates.exclude(status_after='')[:10]]
    milestones = (ProjectMilestone.objects.filter(
        created_at__gte=start_dt, created_at__lt=end_dt)
        .select_related('project'))
    status_changes = [m for m in milestones if m.status_after]
    project_entries = [
        {'heading': f'{m.project.project_code} {m.project.title}',
         'detail': m.get_status_after_display()}
        for m in status_changes[:10]]
    stats = []
    if new_promises:
        stats.append({'key': 'new_promises',
                      'label': 'New promises tracked',
                      'value': new_promises})
    if updates.exists():
        stats.append({'key': 'promise_updates',
                      'label': 'Promise updates recorded',
                      'value': updates.count()})
    if status_changes:
        stats.append({'key': 'project_changes',
                      'label': 'Project status changes',
                      'value': len(status_changes)})
    blocks = []
    if stats:
        blocks.append({'type': 'stats', 'items': stats})
    if update_entries:
        blocks.append({'type': 'entries', 'title': None, 'prefix': None,
                       'separator': 'colon', 'items': update_entries})
    if project_entries:
        blocks.append({'type': 'entries',
                       'title': 'Project status changes', 'prefix': None,
                       'separator': 'colon', 'items': project_entries})
    section['blocks'] = blocks
    section['empty'] = not blocks
    changes = new_promises + updates.count() + len(status_changes)
    return section, {'changes': changes}


def _health_data(start_dt, end_dt):
    section = {
        'key': 'health', 'title': 'Sources & collection health',
        'short_title': 'Sources & collection health',
        'icon': 'fa-satellite-dish',
        'restricted': False, 'empty': True,
        'empty_text': 'No collection cycles or source problems were '
                      'recorded in this period.',
        'blocks': [],
    }
    runs = CollectionRun.objects.filter(
        started_at__gte=start_dt, started_at__lt=end_dt)
    failing = [health for health in
               SourceHealth.objects.select_related('source').all()
               if health.state() == 'FAILING']
    blocks = []
    if runs.exists():
        blocks.append({'type': 'stats', 'items': [
            {'key': 'cycles', 'label': 'Collection cycles',
             'value': runs.count()},
            {'key': 'completed', 'label': 'Completed',
             'value': runs.filter(status='COMPLETED').count()},
            {'key': 'failed', 'label': 'Failed',
             'value': runs.filter(status='FAILED').count()}]})
    if failing:
        blocks.append({'type': 'notes', 'title': None, 'items': [
            f'Source failing: {health.source.name} '
            f'({health.consecutive_failures} consecutive failures)'
            for health in failing]})
    section['blocks'] = blocks
    section['empty'] = not blocks
    facts = {'cycles': runs.count() if runs.exists() else 0,
             'failing_sources': [health.source.name for health in failing]}
    return section, facts


def compose_data(kind, start, end):
    """Assemble the structured briefing data for a period.

    Real records only. The same data renders the dashboard page, the
    HTML email, the plain-text body and the Telegram short summary.
    """
    start_dt, end_dt = _window(start, end)
    if kind == 'WEEKLY':
        title = (f'KPN Statewide Intelligence — Weekly Briefing, '
                 f'{start} to {end}')
        period_label = (f'{start.strftime("%d %b %Y")} – '
                        f'{end.strftime("%d %b %Y")}')
    else:
        title = f'KPN Statewide Intelligence — Daily Briefing, {start}'
        period_label = start.strftime('%d %b %Y')
    sections, facts = [], {}
    for builder in (_collection_data, _desk_data, _security_data,
                    _tracker_data, _health_data):
        section, section_facts = builder(start_dt, end_dt)
        sections.append(section)
        facts[section['key']] = section_facts
    from .cycle import cycle_health
    health_now = cycle_health()
    data = {
        'kind': kind,
        'kind_label': 'Weekly' if kind == 'WEEKLY' else 'Daily',
        'title': title,
        'period_label': period_label,
        'period_start': str(start),
        'period_end': str(end),
        'stats': [
            {'icon': 'fa-inbox', 'label': 'Items collected',
             'value': facts['collection']['total']},
            {'icon': 'fa-clipboard-check', 'label': 'Units verified',
             'value': facts['desk']['verified']},
            {'icon': 'fa-scale-balanced', 'label': 'Tracker changes',
             'value': facts['trackers']['changes']},
            {'icon': 'fa-satellite-dish', 'label': 'Collection cycles',
             'value': facts['health']['cycles']},
        ],
        'sections': sections,
        'facts': facts,
        'alerts': {
            'missed_cycle': bool(health_now['missed']),
            'gap_minutes': health_now['gap_minutes'],
            'failing_sources': facts['health']['failing_sources'],
        },
    }
    return data


# ---------------------------------------------------------------------------
# Plain-text rendering (the stored body / email text part).
# ---------------------------------------------------------------------------

def _block_text_lines(section, block):
    lines = []
    if block['type'] == 'stats':
        if section['key'] == 'health':
            values = {item['key']: item['value'] for item in block['items']}
            lines.append(
                f"Collection cycles in this period: {values['cycles']} "
                f"({values['completed']} completed, "
                f"{values['failed']} failed)")
        else:
            lines.extend(f"{item['label']}: {item['value']}"
                         for item in block['items'])
    elif block['type'] == 'bars':
        if block.get('title'):
            lines.append(f"{block['title']}:")
        lines.extend(f"  - {row['label']}: {row['count']}"
                     for row in block['rows'])
    elif block['type'] == 'entries':
        if block.get('title'):
            lines.append(f"{block['title']}:")
        for item in block['items']:
            if block.get('prefix'):
                lines.append(f"  - {block['prefix']}: {item['heading']}")
            elif block.get('separator') == 'paren':
                lines.append(f"  - {item['heading']} ({item['detail']})")
            elif item.get('detail'):
                lines.append(f"  - {item['heading']}: {item['detail']}")
            else:
                lines.append(f"  - {item['heading']}")
    elif block['type'] == 'notes':
        if block.get('title'):
            lines.append(f"{block['title']}:")
        lines.extend(f'  - {item}' for item in block['items'])
    return lines


def section_text_lines(section):
    lines = []
    for block in section['blocks']:
        lines.extend(_block_text_lines(section, block))
    return lines


def render_text(data):
    """Render the plain-text body from structured data."""
    lines = [data['title'], '=' * len(data['title'])]
    for section in data['sections']:
        if section['empty']:
            continue
        lines.append('')
        lines.append(section['title'])
        lines.append('-' * len(section['title']))
        lines.extend(section_text_lines(section))
    if all(section['empty'] for section in data['sections']):
        lines.append('')
        lines.append('No activity was recorded in this period.')
    return '\n'.join(lines)


def compose(kind, start, end):
    """Compose (title, body) for a period from real records only."""
    data = compose_data(kind, start, end)
    return data['title'], render_text(data)


# ---------------------------------------------------------------------------
# Telegram short summary.
# ---------------------------------------------------------------------------

def compose_short(data, link=''):
    """The short-form summary for staff Telegram chats.

    A few lines only, composed from the same structured data: period,
    collection and verification figures, at most one security-verified
    headline (LGA level; no figures — reported casualty figures are
    flagged as unverified claims, never quoted), tracker changes, and
    a health line when a cycle was missed or a source is failing.
    """
    facts = data['facts']
    lines = [f"KPN Intelligence — {data['kind_label']} Briefing, "
             f"{data['period_label']}"]
    total = facts['collection']['total']
    verified = facts['desk']['verified']
    headlines = facts['security']['headlines']
    changes = facts['trackers']['changes']
    alerts = data['alerts']
    if (not total and not verified and not headlines and not changes
            and not alerts['failing_sources']
            and not alerts['missed_cycle']):
        lines.append('No activity was recorded in this period.')
    else:
        lines.append(f'Items collected: {total}')
        if verified:
            lines.append(f'Verified at the desk: {verified}')
        if headlines:
            first = headlines[0]
            line = (f"Security verified: {first['heading']} "
                    f"({first['detail']})")
            if len(headlines) > 1:
                line += (f" (+{len(headlines) - 1} more at the "
                         f'security desk)')
            lines.append(line)
        if facts['security']['claims']:
            lines.append('Reported casualty figures remain unverified '
                         'claims.')
        if changes:
            lines.append(f'Tracker changes: {changes}')
        health_bits = []
        if alerts['failing_sources']:
            names = ', '.join(alerts['failing_sources'][:3])
            health_bits.append(
                f"{len(alerts['failing_sources'])} source(s) failing "
                f'({names})')
        if alerts['missed_cycle']:
            health_bits.append(
                f"collection cycle missed "
                f"(gap {alerts['gap_minutes']} min)")
        if health_bits:
            lines.append('Health: ' + '; '.join(health_bits))
    if link:
        lines.append(f'Full briefing: {link}')
    return '\n'.join(lines)


def briefing_data(briefing):
    """The briefing's structured data, composed on the fly if the
    stored record predates structured briefings."""
    if briefing.data:
        return briefing.data
    return compose_data(briefing.period_kind, briefing.period_start,
                        briefing.period_end)


def briefing_link(briefing):
    if briefing.pk is None:
        return ''
    return _site_url() + reverse(
        'intelligence:briefing_detail', args=[briefing.pk])


def short_text(briefing):
    """The exact short summary for this briefing (stored at
    generation; composed on the fly for older records)."""
    if briefing.telegram_text:
        return briefing.telegram_text
    return compose_short(briefing_data(briefing),
                         link=briefing_link(briefing))


# ---------------------------------------------------------------------------
# Generation and delivery.
# ---------------------------------------------------------------------------

def generate(kind='DAILY', day=None, actor=None, force=False):
    """Generate (or return) the briefing for a period.

    One stored briefing per (kind, period start): regenerating with
    ``force`` recomposes the body from current records; without it an
    existing briefing is returned unchanged, so a scheduler re-run
    never silently rewrites a briefing someone may have read.
    """
    if kind not in dict(Briefing.PERIOD):
        raise ValueError(f'Unknown briefing period: {kind}')
    start, end = period_for(kind, day)
    briefing = Briefing.objects.filter(
        period_kind=kind, period_start=start).first()
    if briefing is not None and not force:
        return briefing
    data = compose_data(kind, start, end)
    if briefing is None:
        briefing = Briefing(period_kind=kind, period_start=start,
                            period_end=end)
    briefing.title = data['title']
    briefing.body = render_text(data)
    briefing.data = data
    briefing.generated_by = (
        actor if actor is not None and actor.is_authenticated else None)
    briefing.save()
    briefing.telegram_text = compose_short(
        data, link=briefing_link(briefing))
    briefing.save(update_fields=['telegram_text', 'updated_at'])
    IntelligenceAudit.objects.create(
        actor=briefing.generated_by, action='BRIEFING_GENERATED',
        target_type='Briefing', target_id=briefing.pk,
        detail={'period_kind': kind, 'period_start': str(start)})
    return briefing


def email_briefing(briefing, actor=None):
    """Email a briefing to the intelligence-reports holders.

    Uses the site's existing EMAIL_BACKEND. The HTML part follows the
    site's branded email pattern (v2.4.3) and renders the same
    structured sections as the dashboard page; the plain-text body is
    the text alternative. The outcome is recorded on the briefing
    itself — sent, or failed with the error — never silently retried.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    recipients = sorted({
        user.email for user in User.objects.filter(
            is_active=True).exclude(email='')
        if user.email and (user.is_superuser or
                           'VIEW_INTELLIGENCE_REPORTS' in capabilities_for(user))
    })
    if not recipients:
        briefing.email_status = 'Not sent: no reports holders have an email address.'
    else:
        try:
            data = briefing_data(briefing)
            html_body = render_to_string(
                'intelligence/emails/briefing.html', {
                    'briefing': briefing, 'data': data,
                    'email_sections': [
                        {'title': section['title'],
                         'lines': section_text_lines(section)}
                        for section in data['sections']
                        if not section['empty']],
                    'site_url': _site_url(),
                    'briefing_url': briefing_link(briefing),
                })
            message = EmailMultiAlternatives(
                briefing.title, briefing.body, None, recipients)
            message.attach_alternative(html_body, 'text/html')
            message.send(fail_silently=False)
            briefing.email_status = (
                f'Sent to {len(recipients)} recipient(s).')
            briefing.emailed_at = timezone.now()
        except Exception as exc:
            briefing.email_status = (
                f'Failed: {(str(exc) or type(exc).__name__)[:240]}')
    briefing.save(update_fields=['email_status', 'emailed_at', 'updated_at'])
    IntelligenceAudit.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action='BRIEFING_EMAILED', target_type='Briefing',
        target_id=briefing.pk, detail={'status': briefing.email_status[:120]})
    return briefing


def send_telegram(briefing, actor=None):
    """Deliver the short summary to the configured staff chats.

    Goes through the EXISTING Telegram machinery exactly as the
    Phase 6 alerts do: a BotOutbox row per configured staff chat ID,
    sent via ``telegram_integration.brain_service.send_outbox_row``.
    Chat IDs come from the BRIEFING alert-rule row — there is
    deliberately no fallback to the public channel, and an
    unconfigured channel is recorded SKIPPED. Idempotent per
    briefing + chat: a chat that already has a delivery record for
    this briefing is never sent to again, whatever its status.
    Returns the briefing's Telegram delivery records.
    """
    rule = alert_service.get_rule('BRIEFING')
    deliveries = []
    configured = (rule.enabled and 'TELEGRAM' in (rule.channels or []))
    chat_ids = rule.chat_id_list() if configured else []
    if not chat_ids:
        if not configured:
            reason = ('Briefing Telegram delivery is disabled on the '
                      'briefing rule.')
        else:
            reason = ('No staff chat IDs configured for briefings; '
                      'the short summary is never sent to the public '
                      'channel.')
        delivery, _created = BriefingDelivery.objects.get_or_create(
            briefing=briefing, channel='TELEGRAM', recipient='',
            defaults={'status': 'SKIPPED', 'error': reason})
        return [delivery]
    from telegram_integration import brain_service
    from telegram_integration.models import BotOutbox
    text = short_text(briefing)
    created_any = False
    for chat_id in chat_ids:
        existing = BriefingDelivery.objects.filter(
            briefing=briefing, channel='TELEGRAM',
            recipient=chat_id).first()
        if existing is not None:
            deliveries.append(existing)
            continue
        delivery = BriefingDelivery(
            briefing=briefing, channel='TELEGRAM', recipient=chat_id)
        try:
            row = BotOutbox.objects.create(
                kind='CUSTOM', chat_id=chat_id, text=text[:4000])
            if brain_service.send_outbox_row(row):
                delivery.status = 'SENT'
                delivery.sent_at = timezone.now()
            else:
                delivery.status = 'FAILED'
                delivery.error = (row.error or 'Telegram send failed.')[:300]
        except Exception as exc:  # recorded, never retried in a loop
            delivery.status = 'FAILED'
            delivery.error = (str(exc) or type(exc).__name__)[:300]
        delivery.save()
        created_any = True
        deliveries.append(delivery)
    if created_any:
        IntelligenceAudit.objects.create(
            actor=actor if actor is not None and actor.is_authenticated else None,
            action='BRIEFING_TELEGRAM_SENT', target_type='Briefing',
            target_id=briefing.pk,
            detail={'sent': sum(1 for d in deliveries
                                 if d.status == 'SENT'),
                    'failed': sum(1 for d in deliveries
                                  if d.status == 'FAILED')})
    return deliveries
