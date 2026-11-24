"""Public KPN coverage by LGA (Page-by-Page Upgrade, Priority 5).

Powers the public Kebbi State map on /impact/. Every figure is a live
count from public-facing records:

- ``members``     — verified members registered in the LGA
                    (``staff.User`` geography; counts only, never names);
- ``wards_active``— wards in the LGA with at least one verified member,
                    out of ``wards_total`` wards on record;
- ``stories``     — published stories placed in the LGA by an explicit
                    ``intelligence.ArticleLocation`` record (the same
                    recorded links the public LGA news pages read —
                    never guessed from a story's words);
- ``initiatives`` — community initiatives recorded in the LGA
                    (``core.CommunityInitiative``);
- ``promises``    — commitments tracked in the LGA (Promise Tracker);
- ``projects``    — public projects tracked in the LGA (Project Tracker).

Coverage strength is the number of those five record types present in
the LGA (0–5) and drives the choropleth: an LGA with no records is
shaded as not yet covered and counted as such — nothing is shaded or
counted that does not exist. Boundary geometry is the validated HDX
COD-AB dataset already used by the intelligence tracking map
(``intelligence.map_data``); LGAs without verified geometry simply do
not draw, and still appear in the list.
"""
from django.db.models import Count

from leadership.models import LGA
from staff.models import User

from .models import CommunityInitiative

# Choropleth fills — shades of the KPN brand green, bucketed by how
# many of the five coverage record types are present in the LGA.
_FILL_STOPS = (
    (0, '#e9f0ea'),
    (1, '#c8e6cf'),
    (2, '#93d3a4'),
    (3, '#57bd78'),
    (4, '#28a745'),
    (5, '#176b36'),
)


def fill_for(strength):
    fill = _FILL_STOPS[0][1]
    for minimum, colour in _FILL_STOPS:
        if strength >= minimum:
            fill = colour
    return fill


def _count_by_lga(queryset, lga_field='lga_id'):
    return {
        row[lga_field]: row['n']
        for row in queryset.values(lga_field).annotate(n=Count('id'))
    }


def coverage_rows():
    """One coverage row per LGA in the leadership directory."""
    from intelligence.models import ArticleLocation, Project
    from story_intelligence.models import Promise

    members = _count_by_lga(
        User.objects.filter(status='VERIFIED', lga__isnull=False))
    wards_active = {
        row['lga_id']: row['n']
        for row in User.objects.filter(
            status='VERIFIED', ward__isnull=False)
        .values('lga_id').annotate(n=Count('ward_id', distinct=True))
    }
    stories = {
        row['lga_id']: row['n']
        for row in ArticleLocation.objects.filter(
            article__status='PUBLISHED')
        .values('lga_id').annotate(n=Count('article_id', distinct=True))
    }
    initiatives = _count_by_lga(
        CommunityInitiative.objects.filter(lga__isnull=False))
    promises = _count_by_lga(Promise.objects.filter(lga__isnull=False))
    projects = _count_by_lga(Project.objects.filter(lga__isnull=False))

    from intelligence.article_locations import lga_slug
    from intelligence.map_data import LGA_GEOMETRY

    rows = []
    lgas = (
        LGA.objects.select_related('zone')
        .annotate(wards_total=Count('wards', distinct=True))
        .order_by('name')
    )
    for lga in lgas:
        row = {
            'lga': lga,
            'members': members.get(lga.pk, 0),
            'wards_active': wards_active.get(lga.pk, 0),
            'wards_total': lga.wards_total,
            'stories': stories.get(lga.pk, 0),
            'initiatives': initiatives.get(lga.pk, 0),
            'promises': promises.get(lga.pk, 0),
            'projects': projects.get(lga.pk, 0),
        }
        row['strength'] = sum(
            1 for key in ('members', 'stories', 'initiatives',
                          'promises', 'projects')
            if row[key] > 0)
        row['covered'] = row['strength'] > 0
        row['geometry'] = LGA_GEOMETRY.get(lga.name)
        row['fill'] = fill_for(row['strength'])
        row['news_slug'] = lga_slug(lga)
        rows.append(row)
    return rows


def coverage_totals(rows):
    """Statewide summary over the coverage rows."""
    return {
        'lgas_total': len(rows),
        'lgas_covered': sum(1 for row in rows if row['covered']),
        'members': sum(row['members'] for row in rows),
        'stories': sum(row['stories'] for row in rows),
        'initiatives': sum(row['initiatives'] for row in rows),
        'promises': sum(row['promises'] for row in rows),
        'projects': sum(row['projects'] for row in rows),
    }
