"""Per-LGA tracking rollups shared by the intelligence overview and the
dedicated Kebbi tracking map.

Every figure comes from live records — promises in the Public Promise
Tracker (story_intelligence), projects in the Public Project Tracker
(intelligence, Phase 5) and the geographic directory. Nothing is
estimated, projected or padded: an LGA with no records reports honest
zeros. Delayed follows the tracker's own honest test
(`Promise.is_delayed`): explicitly marked DELAYED, or the announced
deadline has passed without verified completion.
"""
from django.db.models import Count
from django.utils import timezone

from leadership.models import LGA
from story_intelligence.models import Promise

from .map_data import LGA_GEOMETRY
from .models import Project

# Choropleth fills — shades of the KPN brand green (--kpn-green /
# --kpn-action family), bucketed by promises tracked in the LGA.
_FILL_STOPS = (
    (0, '#e9f0ea'),
    (1, '#c8e6cf'),
    (2, '#93d3a4'),
    (4, '#57bd78'),
    (7, '#28a745'),
    (11, '#176b36'),
)


def fill_for(tracked):
    fill = _FILL_STOPS[0][1]
    for minimum, colour in _FILL_STOPS:
        if tracked >= minimum:
            fill = colour
    return fill


def empty_counts():
    return {'tracked': 0, 'in_progress': 0, 'delayed': 0, 'verified': 0}


def empty_project_counts():
    return {'pj_tracked': 0, 'pj_delayed_stalled': 0,
            'pj_reported_abandoned': 0, 'pj_verified_abandoned': 0,
            'pj_completed': 0}


def project_counts_by_lga():
    """{lga_pk: project counts} computed from the real Project table.

    Status groups (Phase 5): tracked = every registered project;
    delayed-or-stalled = DELAYED or SUSPENDED; reported abandoned and
    verified abandoned are counted separately — the blueprint's core
    distinction is never merged; completed = COMPLETED_VERIFIED only
    (a completion KPN has verified, mirroring the promise rule).
    """
    counts = {}
    projects = Project.objects.filter(lga__isnull=False).only(
        'lga_id', 'status')
    for project in projects:
        row = counts.setdefault(project.lga_id, empty_project_counts())
        row['pj_tracked'] += 1
        if project.status in ('DELAYED', 'SUSPENDED'):
            row['pj_delayed_stalled'] += 1
        elif project.status == 'REPORTED_ABANDONED':
            row['pj_reported_abandoned'] += 1
        elif project.status == 'VERIFIED_ABANDONED':
            row['pj_verified_abandoned'] += 1
        elif project.status == 'COMPLETED_VERIFIED':
            row['pj_completed'] += 1
    return counts


def promise_counts_by_lga():
    """{lga_pk: counts} computed from the real Promise table."""
    today = timezone.localdate()
    counts = {}
    promises = Promise.objects.filter(lga__isnull=False).only(
        'lga_id', 'status', 'deadline')
    for promise in promises:
        row = counts.setdefault(promise.lga_id, empty_counts())
        row['tracked'] += 1
        if promise.status == 'IN_PROGRESS':
            row['in_progress'] += 1
        elif promise.status == 'COMPLETED_VERIFIED':
            row['verified'] += 1
        if promise.is_delayed(today):
            row['delayed'] += 1
    return counts


def lga_tracking_rows():
    """One row per directory LGA: promise counts, project counts,
    directory counts and map geometry (rows without verified geometry
    carry geometry=None and simply do not draw — the list still
    shows them)."""
    counts = promise_counts_by_lga()
    project_counts = project_counts_by_lga()
    lgas = (
        LGA.objects.select_related('zone')
        .annotate(
            ward_count=Count('wards', distinct=True),
            district_count=Count('districts', distinct=True),
            community_count=Count('communities', distinct=True),
        )
        .order_by('name')
    )
    rows = []
    for lga in lgas:
        row_counts = counts.get(lga.pk) or empty_counts()
        row_projects = project_counts.get(lga.pk) or empty_project_counts()
        rows.append({
            'lga': lga,
            **row_counts,
            **row_projects,
            'ward_count': lga.ward_count,
            'district_count': lga.district_count,
            'community_count': lga.community_count,
            'geometry': LGA_GEOMETRY.get(lga.name),
            'fill': fill_for(row_counts['tracked']),
        })
    return rows


def totals_for(rows):
    totals = empty_counts()
    for row in rows:
        for key in totals:
            totals[key] += row[key]
    return totals


def project_totals_for(rows):
    totals = empty_project_counts()
    for row in rows:
        for key in totals:
            totals[key] += row.get(key, 0)
    return totals
