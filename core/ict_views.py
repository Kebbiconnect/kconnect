"""The ICT Admin console (owner instruction, 2026-11-24).

One page where the ICT Admin — the assigned holder (initially the
Director of Media & Communications) or any super admin — can see,
view and check everything ICT-related across KPN: the member system,
leadership & roles, the editorial/intelligence machinery, content,
Telegram, and the assignment itself.

Every figure on the page is computed live from the site's own
records; panels aggregate and LINK into the existing management
surfaces rather than duplicating their functions. Superuser accounts
are excluded from every member figure and list on this page (the
super admin is never part of the member register views).

The page is READ-ONLY about the assignment (owner clarification,
2026-11-24): it displays the current holder and states that the
assignment is managed by the Super Admin in the Django admin panel.
There is no reassignment form or POST endpoint here — the Super
Admin operates only through /admin/.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from campaigns.models import Campaign
from core.dashboard_charts import bar_rows, count_by
from core.ict_admin import can_access_ict_admin, current_assignment
from core.models import (
    CommunityReport, IctAdminChange, Opportunity, OpportunityReport,
)
from editorial.models import Item as EditorialItem
from editorial.models import Source as EditorialSource
from intelligence.models import (
    AlertDelivery, CollectionRun, Project, SourceHealth,
)
from leadership.access import role_title
from leadership.models import RoleDefinition
from staff.models import User
from story_intelligence.models import Promise
from telegram_integration.models import BotOutbox, TelegramMembership


def _member_base():
    """The member register as ICT sees it — never superuser accounts."""
    return User.objects.filter(is_superuser=False)


def _source_health_summary():
    """Health-state counts over sources that have a health record."""
    summary = {}
    for health in SourceHealth.objects.select_related('source').all():
        state = health.state()
        summary[state] = summary.get(state, 0) + 1
    return [
        {'state': state, 'count': count}
        for state, count in sorted(summary.items())
    ]


def _leadership_rows():
    """Every office in the catalogue with its current holder(s)."""
    holders = (
        _member_base()
        .filter(status='VERIFIED', role_definition__isnull=False)
        .select_related('role_definition', 'zone', 'lga', 'ward')
        .order_by('last_name', 'first_name'))
    by_definition = {}
    for holder in holders:
        by_definition.setdefault(holder.role_definition_id, []).append(holder)
    rows = []
    for definition in RoleDefinition.objects.all():
        rows.append({
            'definition': definition,
            'holders': by_definition.get(definition.pk, []),
        })
    return rows


@login_required
@require_GET
def ict_admin_console(request):
    if not can_access_ict_admin(request.user):
        messages.error(
            request, 'You do not have permission to access this page.')
        return redirect('staff:dashboard')

    members = _member_base()
    verified = members.filter(status='VERIFIED')

    stats = {
        'total_members': members.count(),
        'verified_members': verified.count(),
        'pending_verification': members.filter(
            status__in=('PENDING', 'UNDER_REVIEW')).count(),
        'position_holders': verified.filter(
            role_definition__isnull=False).count(),
        'published_articles': Campaign.objects.filter(
            status='PUBLISHED').count(),
        'open_opportunities': Opportunity.objects.filter(
            status='OPEN').count(),
        'pending_community_reports': CommunityReport.objects.filter(
            status='PENDING').count(),
        'new_listing_reports': OpportunityReport.objects.filter(
            status='NEW').count(),
    }

    assignment = current_assignment()
    holder = assignment.user

    context = {
        'stats': stats,
        'member_status_bars': bar_rows(count_by(
            members, 'status', User.STATUS_CHOICES)),
        'member_zone_bars': bar_rows(count_by(
            verified.filter(zone__isnull=False), 'zone__name')),
        'recent_members': list(
            members.select_related('lga', 'zone', 'role_definition')
            .order_by('-created_at')[:10]),
        'leadership_rows': _leadership_rows(),
        'editorial_item_states': count_by(
            EditorialItem.objects.all(), 'state', EditorialItem.STATE),
        'sources_total': EditorialSource.objects.count(),
        'sources_enabled': EditorialSource.objects.filter(
            enabled=True).count(),
        'sources_failing': EditorialSource.objects.filter(
            consecutive_failures__gt=0).count(),
        'source_health_summary': _source_health_summary(),
        'collection_runs': list(CollectionRun.objects.all()[:8]),
        'alert_failures': AlertDelivery.objects.filter(
            status='FAILED').count(),
        'alerts_total': AlertDelivery.objects.count(),
        'campaign_status_counts': count_by(
            Campaign.objects.all(), 'status', Campaign.STATUS_CHOICES),
        'opportunity_status_counts': count_by(
            Opportunity.objects.all(), 'status',
            Opportunity.STATUS_CHOICES),
        'promises_total': Promise.objects.count(),
        'projects_total': Project.objects.count(),
        'telegram_connected': TelegramMembership.objects.count(),
        'telegram_verified': TelegramMembership.objects.filter(
            is_verified=True).count(),
        'outbox_queued': BotOutbox.objects.filter(state='QUEUED').count(),
        'outbox_sent': BotOutbox.objects.filter(state='SENT').count(),
        'outbox_failed': BotOutbox.objects.filter(state='FAILED').count(),
        'assignment': assignment,
        'holder': holder,
        'holder_title': role_title(holder) if holder else None,
        'change_history': list(_change_history()),
    }
    return render(request, 'core/ict_admin.html', context)


def _change_history():
    return (IctAdminChange.objects
            .select_related('previous_holder', 'new_holder', 'changed_by')
            .order_by('-created_at', '-pk')[:10])
