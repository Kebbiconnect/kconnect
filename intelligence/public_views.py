"""Public Project Tracker pages (Phase 5 — blueprint Part G).

Reader-only, like the Promise Tracker: every figure is computed from
real Project records, filters validate against real vocabularies and
ignore anything else, and documented-fact fields (contractor,
contract amount, dates) are rendered ONLY when a source stated them —
the templates receive them as-is and show nothing in their place.
Private evidence (is_public=False) is never queried here at all.
"""
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from leadership.models import LGA
from story_intelligence.models import Institution, Promise

from .models import PROJECT_CATEGORIES, PROJECT_STATUSES, Project


def _project_stats():
    base = Project.objects.all()
    return {
        'total': base.count(),
        'in_progress': base.filter(status='IN_PROGRESS').count(),
        'delayed_stalled': base.filter(
            status__in=['DELAYED', 'SUSPENDED']).count(),
        'reported_abandoned': base.filter(
            status='REPORTED_ABANDONED').count(),
        'verified_abandoned': base.filter(
            status='VERIFIED_ABANDONED').count(),
        'completed_verified': base.filter(
            status='COMPLETED_VERIFIED').count(),
    }


def project_list(request):
    params = {
        'q': request.GET.get('q', '').strip(),
        'status': request.GET.get('status', ''),
        'sector': request.GET.get('sector', ''),
        'lga': request.GET.get('lga', ''),
        'institution': request.GET.get('institution', ''),
    }
    # Validate every filter against real vocabularies; anything else
    # is ignored rather than erroring or silently filtering to none.
    if params['status'] not in dict(PROJECT_STATUSES):
        params['status'] = ''
    if params['sector'] not in dict(Promise.SECTOR_CHOICES):
        params['sector'] = ''
    for key, model in (('lga', LGA), ('institution', Institution)):
        try:
            params[key] = int(params[key])
        except (TypeError, ValueError):
            params[key] = ''
        else:
            if not model.objects.filter(pk=params[key]).exists():
                params[key] = ''

    projects = (Project.objects
                .select_related('institution', 'lga', 'ward', 'district',
                                'community')
                .annotate(last_milestone_date=Max('milestones__date')))
    if params['q']:
        q = params['q']
        projects = projects.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
            | Q(project_code__icontains=q)
            | Q(institution__name__icontains=q)
            | Q(contractor_name__icontains=q)
            | Q(lga__name__icontains=q) | Q(ward__name__icontains=q)
            | Q(district__name__icontains=q)
            | Q(community__name__icontains=q))
    if params['status']:
        projects = projects.filter(status=params['status'])
    if params['sector']:
        projects = projects.filter(sector=params['sector'])
    if params['lga']:
        projects = projects.filter(lga_id=params['lga'])
    if params['institution']:
        projects = projects.filter(institution_id=params['institution'])
    projects = projects.distinct()

    from .models import ProjectMilestone
    last_updated = None
    latest_project = (Project.objects.order_by('-updated_at')
                      .values_list('updated_at', flat=True).first())
    latest_milestone = (ProjectMilestone.objects.order_by('-created_at')
                        .values_list('created_at', flat=True).first())
    stamps = [s for s in (latest_project, latest_milestone) if s]
    if stamps:
        last_updated = max(stamps)

    project_rows = list(projects)
    context = {
        'projects': project_rows,
        'result_count': len(project_rows),
        'stats': _project_stats(),
        'status_choices': PROJECT_STATUSES,
        'sector_choices': Promise.SECTOR_CHOICES,
        'category_choices': PROJECT_CATEGORIES,
        'lgas': LGA.objects.select_related('zone').order_by('name'),
        'institutions': Institution.objects.all(),
        'params': params,
        'has_filters': any(params.values()),
        'last_updated': last_updated,
        'today': timezone.localdate(),
    }
    return render(request, 'intelligence/project_list.html', context)


def project_detail(request, project_id):
    project = get_object_or_404(
        Project.objects.select_related('institution', 'lga', 'ward',
                                       'district', 'community'),
        pk=project_id)
    context = {
        'project': project,
        'milestones': project.milestones.select_related('recorded_by'),
        # Only evidence cleared for publication is ever queried here;
        # private evidence does not reach the template at all.
        'evidence': project.evidence.filter(is_public=True),
        'stories': project.stories.filter(status='PUBLISHED'),
    }
    return render(request, 'intelligence/project_detail.html', context)
