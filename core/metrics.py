"""Impact & Metrics registry (Page-by-Page Upgrade, Priority 5; brief §H).

Every public figure on /impact/ is computed here from the records it
counts — no number is typed into a template. Each metric carries the
four provenance items the brief requires beside every figure:

- ``definition``    — what the number counts, in plain words;
- ``period``        — the reporting period, derived from the actual
                      span of the underlying records (earliest to
                      latest record date), never a period the data
                      cannot back;
- ``last_updated``  — the date of the latest underlying record;
- ``source``        — the system of record the figure comes from.

A metric whose underlying records do not exist is returned with
``value=None`` and ``recorded=False``: the page shows an honest
"Not yet recorded" state rather than a zero dressed as an achievement
(decision D-01 — the page only ever shows what the system computes;
the brief's 327+ / 20-21 / 93-225 figures appear nowhere).

Financial figures are NOT computed here at all: decision D-14's
default is that KPN publishes financial transparency information only
where approved for publication, so the organisational-performance
group carries the brief's own line as an unnumbered entry.
"""
from django.db.models import Count, Max, Min, Sum

from campaigns.models import Campaign
from leadership.models import LGA, Ward
from staff.models import (CommunityOutreach, User, WelfareProgram,
                          WomensProgram, YouthProgram)

from .models import CommunityInitiative, ImpactStory, Opportunity


def _span(queryset, field):
    """(earliest, latest) dates of ``field`` over ``queryset``.

    Returns (None, None) for an empty queryset. Datetimes are reduced
    to dates so period labels read as calendar periods.
    """
    agg = queryset.aggregate(first=Min(field), last=Max(field))
    first, last = agg['first'], agg['last']
    if first is not None and hasattr(first, 'date'):
        first = first.date()
    if last is not None and hasattr(last, 'date'):
        last = last.date()
    return first, last


def _period_label(first, last):
    """Reporting-period label derived from the record span."""
    if first is None or last is None:
        return None
    if first == last:
        return first.strftime('%B %Y')
    return f"{first.strftime('%B %Y')} – {last.strftime('%B %Y')}"


def _metric(key, label, value, definition, source, first=None, last=None,
            suffix='', note=None):
    recorded = value is not None and value > 0
    return {
        'key': key,
        'label': label,
        'value': value if recorded else None,
        'recorded': recorded,
        'suffix': suffix if recorded else '',
        'definition': definition,
        'source': source,
        'period': _period_label(first, last) if recorded else None,
        'last_updated': last if recorded else None,
        'note': note,
    }


def _programme_completion_span():
    """Span across the four staff programme registers."""
    firsts, lasts = [], []
    for model in (WomensProgram, YouthProgram, WelfareProgram,
                  CommunityOutreach):
        first, last = _span(model.objects.all(), 'created_at')
        if first is not None:
            firsts.append(first)
            lasts.append(last)
    if not firsts:
        return None, None
    return min(firsts), max(lasts)


def metric_groups():
    """The six brief §H measurement groups, fully computed.

    Returns a list of {'name': ..., 'metrics': [metric, ...]} in the
    brief's order. Every value traces to the query named in the
    metric's ``source`` and described in the Priority 5 build report.
    """
    # ── Network Reach ────────────────────────────────────────────────
    verified = User.objects.filter(status='VERIFIED')
    first, last = _span(verified, 'created_at')
    verified_members = _metric(
        'verified_members', 'Verified members', verified.count(),
        'Members whose KPN registration has been verified.',
        'KPN member register', first, last)

    member_lgas = LGA.objects.filter(members__status='VERIFIED').distinct()
    active_lgas = _metric(
        'active_lgas', 'Active LGAs', member_lgas.count(),
        'Local government areas with at least one verified member.',
        'KPN member register · LGA directory', first, last,
        suffix=' of 21')

    member_wards = Ward.objects.filter(members__status='VERIFIED').distinct()
    active_wards = _metric(
        'active_wards', 'Active wards', member_wards.count(),
        'Wards with at least one verified member.',
        'KPN member register · Ward directory', first, last,
        suffix=' of 225')

    published_stories = ImpactStory.objects.filter(is_published=True)
    s_first, s_last = _span(published_stories, 'date_achieved')
    communities_total = published_stories.aggregate(
        total=Sum('communities_reached'))['total'] or 0
    communities_reached = _metric(
        'communities_reached', 'Communities reached', communities_total,
        'Communities recorded as reached in KPN\u2019s published '
        'impact stories.',
        'Published impact stories', s_first, s_last)

    # ── Community Development ────────────────────────────────────────
    initiatives = CommunityInitiative.objects.all()
    i_first, i_last = _span(initiatives, 'created_at')
    initiatives_metric = _metric(
        'initiatives', 'Initiatives documented', initiatives.count(),
        'Community initiatives recorded by KPN, at every stage from '
        'planned to completed.',
        'Community initiatives register', i_first, i_last)

    people_total = initiatives.aggregate(
        total=Sum('people_reached'))['total'] or 0
    beneficiaries = _metric(
        'beneficiaries', 'Beneficiaries recorded', people_total,
        'People recorded as reached by KPN community initiatives.',
        'Community initiatives register', i_first, i_last)

    interventions = _metric(
        'interventions', 'Documented interventions',
        published_stories.count(),
        'Published impact stories documenting KPN interventions '
        'and outcomes.',
        'Published impact stories', s_first, s_last)

    # ── Media & Information ──────────────────────────────────────────
    published = Campaign.objects.filter(status='PUBLISHED')
    p_first, p_last = _span(published, 'published_at')
    reports_published = _metric(
        'reports_published', 'Reports published', published.count(),
        'Stories published in the KPN Newsroom.',
        'KPN Newsroom', p_first, p_last)

    impact_filed = published.filter(story_profile__kind='IMPACT')
    community_stories = _metric(
        'community_stories', 'Community stories', impact_filed.count(),
        'Published stories filed as Human Impact Files.',
        'Human Impact Files', *_span(impact_filed, 'published_at'))

    verified_reports_qs = published.filter(verification_status='VERIFIED')
    verified_reports = _metric(
        'verified_reports', 'Verified public-interest reports',
        verified_reports_qs.count(),
        'Published stories carrying KPN Verified status after the '
        'newsroom verification process.',
        'KPN Newsroom verification records',
        *_span(verified_reports_qs, 'published_at'))

    # ── Youth Empowerment ────────────────────────────────────────────
    youth = YouthProgram.objects.all()
    y_first, y_last = _span(youth, 'created_at')
    training = _metric(
        'training', 'Training programmes',
        youth.filter(program_type='TRAINING').count(),
        'Youth training and skills-development programmes recorded '
        'by KPN.',
        'Youth programme records', y_first, y_last)
    mentorship = _metric(
        'mentorship', 'Mentorship programmes',
        youth.filter(program_type='MENTORSHIP').count(),
        'Youth mentorship programmes recorded by KPN.',
        'Youth programme records', y_first, y_last)

    opportunities = Opportunity.objects.all()
    o_first, o_last = _span(opportunities, 'created_at')
    opportunity_programmes = _metric(
        'opportunity_programmes', 'Opportunity programmes shared',
        opportunities.count(),
        'Opportunity listings carried on the KPN Opportunities Hub, '
        'including its expired archive.',
        'Opportunities Hub', o_first, o_last)

    # ── Civic Engagement ─────────────────────────────────────────────
    civic_qs = published.filter(category='CIVIC')
    civic_education = _metric(
        'civic_education', 'Civic education reports', civic_qs.count(),
        'Published Newsroom stories in the Civic category.',
        'KPN Newsroom', *_span(civic_qs, 'published_at'))

    # Election observation has no records system (decision D-12:
    # observer records are built only when KPN runs an observation
    # mission). Until then this metric is honestly unrecorded.
    observer = _metric(
        'observer_participation', 'Observer participation', None,
        'Election observation missions in which KPN has fielded '
        'observers.',
        'Election Observation records')

    from story_intelligence.models import Promise
    promises = Promise.objects.all()
    commitments = _metric(
        'commitments_tracked', 'Commitments tracked', promises.count(),
        'Public commitments recorded in the Promise Tracker.',
        'Promise Tracker', *_span(promises, 'created_at'))

    from intelligence.models import Project
    projects = Project.objects.all()
    projects_tracked = _metric(
        'projects_tracked', 'Public projects tracked', projects.count(),
        'Public projects recorded in the Project Tracker.',
        'Project Tracker', *_span(projects, 'created_at'))

    # ── Organizational Performance ───────────────────────────────────
    completed = (
        WomensProgram.objects.filter(status='COMPLETED').count()
        + YouthProgram.objects.filter(status='COMPLETED').count()
        + WelfareProgram.objects.filter(status='COMPLETED').count()
        + CommunityOutreach.objects.filter(status='COMPLETED').count()
    )
    c_first, c_last = _programme_completion_span()
    programmes_completed = _metric(
        'programmes_completed', 'Programmes completed', completed,
        'Programmes recorded as completed across KPN\u2019s women\u2019s, '
        'youth, welfare and community outreach programmes.',
        'Programme records', c_first, c_last)

    partnerships_qs = CommunityOutreach.objects.filter(
        engagement_type='PARTNERSHIP')
    partnerships = _metric(
        'partnerships', 'Partnership engagements', partnerships_qs.count(),
        'Partnership engagements recorded with organisations and '
        'community groups.',
        'Community outreach records',
        *_span(partnerships_qs, 'created_at'))

    # D-14 default: financial figures are published only where
    # approved for publication. No donation figure is computed here.
    financial = _metric(
        'financial_transparency', 'Financial transparency', None,
        'Financial transparency information, published where approved '
        'for publication.',
        'KPN financial records',
        note='KPN publishes financial figures only where approved '
             'for publication.')

    return [
        {'name': 'Network Reach', 'metrics': [
            verified_members, active_lgas, active_wards,
            communities_reached]},
        {'name': 'Community Development', 'metrics': [
            initiatives_metric, beneficiaries, interventions]},
        {'name': 'Media & Information', 'metrics': [
            reports_published, community_stories, verified_reports]},
        {'name': 'Youth Empowerment', 'metrics': [
            training, mentorship, opportunity_programmes]},
        {'name': 'Civic Engagement', 'metrics': [
            civic_education, observer, commitments, projects_tracked]},
        {'name': 'Organizational Performance', 'metrics': [
            programmes_completed, partnerships, financial]},
    ]


def headline_figures():
    """The four long-standing headline figures, computed exactly as
    the Impact page has always computed them — except that
    ``communities_reached`` no longer carries the removed
    ``max(50, …)`` floor (decision D-02): it is the true recorded sum
    of published impact stories, even when that sum is below 50 or 0.
    """
    verified_members = User.objects.filter(status='VERIFIED').count()
    lgas_active = LGA.objects.filter(
        members__status='VERIFIED').distinct().count()
    wards_active = Ward.objects.filter(
        members__status='VERIFIED').distinct().count()
    communities_reached = ImpactStory.objects.filter(
        is_published=True).aggregate(
            total=Sum('communities_reached'))['total'] or 0
    return {
        'verified_members': verified_members,
        'lgas_active': lgas_active,
        'wards_active': wards_active,
        'communities_reached': communities_reached,
    }
