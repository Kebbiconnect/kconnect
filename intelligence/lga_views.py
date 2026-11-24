"""Public LGA news pages (Phase 7) — /newsroom/lga/ and /newsroom/lga/<slug>/.

Reader-only, like the trackers. Everything on these pages is read
from stored records:

- a story appears because an explicit ``ArticleLocation`` row links
  it to the LGA (written at desk conversion, mirrored from the
  article's own LGA field, or tagged by staff) — the page never
  scans article text to guess a location;
- the tracker picture comes from the same rollups the tracking map
  uses (``intelligence.tracking``), so the numbers agree everywhere;
- an LGA with nothing yet shows an honest, premium empty state.
"""
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from leadership.models import LGA, Ward
from story_intelligence.models import Promise

from . import article_locations, tracking as tracking_service
from .models import Community, District, Project

STORIES_PER_PAGE = 12
RECENT_TRACKER_ROWS = 4


def _tracker_picture(lga):
    """Promise + project counts for one LGA, from the shared rollups."""
    promises = tracking_service.promise_counts_by_lga().get(
        lga.pk, tracking_service.empty_counts())
    projects = tracking_service.project_counts_by_lga().get(
        lga.pk, tracking_service.empty_project_counts())
    return promises, projects


def lga_index(request):
    story_counts = article_locations.story_counts_by_lga()
    promise_counts = tracking_service.promise_counts_by_lga()
    project_counts = tracking_service.project_counts_by_lga()
    rows = []
    for lga in LGA.objects.select_related('zone').order_by(
            'zone__name', 'name'):
        promises = promise_counts.get(
            lga.pk, tracking_service.empty_counts())
        projects = project_counts.get(
            lga.pk, tracking_service.empty_project_counts())
        rows.append({
            'lga': lga,
            'zone': lga.zone.name,
            'slug': article_locations.lga_slug(lga),
            'stories': story_counts.get(lga.pk, 0),
            'promises': promises['tracked'],
            'projects': projects['pj_tracked'],
        })
    return render(request, 'intelligence/lga_news_index.html', {
        'rows': rows,
        'total_stories': sum(row['stories'] for row in rows),
        'total_promises': sum(row['promises'] for row in rows),
        'total_projects': sum(row['projects'] for row in rows),
    })


def lga_detail(request, slug):
    lga = article_locations.lga_for_slug(slug)
    if lga is None:
        raise Http404('Unknown LGA.')
    stories_qs = article_locations.published_stories(lga)
    paginator = Paginator(stories_qs, STORIES_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))
    promise_counts, project_counts = _tracker_picture(lga)
    promises = (Promise.objects.filter(lga=lga)
                .select_related('institution')
                .order_by('-created_at', '-pk')[:RECENT_TRACKER_ROWS])
    projects = (Project.objects.filter(lga=lga)
                .select_related('institution')
                .order_by('-updated_at', '-pk')[:RECENT_TRACKER_ROWS])
    return render(request, 'intelligence/lga_news_detail.html', {
        'lga': lga,
        'slug': slug,
        'district_count': District.objects.filter(lga=lga).count(),
        'community_count': Community.objects.filter(lga=lga).count(),
        'ward_count': Ward.objects.filter(lga=lga).count(),
        'stories': page_obj,
        'story_total': paginator.count,
        'promise_counts': promise_counts,
        'project_counts': project_counts,
        'promises': promises,
        'projects': projects,
        'promises_url': f"{reverse('promises:list')}?lga={lga.pk}",
        'projects_url': f"{reverse('projects:list')}?lga={lga.pk}",
    })
