"""Public project tracker services (Phase 5 — blueprint Part G).

All project writes go through this layer, never directly from views,
so the blueprint's integrity rules hold on every path:

- Registration allocates the permanent KPN-PRJ code (Doc 04 §3.4)
  under a row lock, exactly like Story ID allocation.
- Documented-fact fields (contractor, contract amount, dates) are
  only ever what a caller passes in from a source; nothing here
  derives, estimates or fills them.
- Status changes are append-only history: every change writes a
  ProjectMilestone with ``status_after`` set, plus an audit row.
- The guarded statuses — VERIFIED_ABANDONED and COMPLETED_VERIFIED —
  additionally require (Doc 03 §2.6): the VERIFY_PROJECTS capability,
  a qualifying evidence record on the project (kind FIELD_INSPECTION
  or OFFICIAL_RECORD), and a verifier who is not the person who
  reported that evidence (``captured_by``). REPORTED_ABANDONED is a
  source's claim and needs only MANAGE_PROJECTS; it can never be
  reached "as" a verification.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from leadership.capabilities import capabilities_for

from .models import (
    PROJECT_STATUSES, PROJECT_TERMINAL_STATUSES,
    PROJECT_VERIFYING_EVIDENCE_KINDS, IntelligenceAudit, Project,
    ProjectEvidence, ProjectMilestone, ProjectSequence,
)

GUARDED_STATUSES = ('VERIFIED_ABANDONED', 'COMPLETED_VERIFIED')


class ProjectError(Exception):
    """A project action that cannot be performed (illegal transition,
    missing verification basis, ...). Views surface the message."""


def has_capability(user, capability):
    return bool(user is not None and user.is_authenticated
                and (user.is_superuser
                     or capability in capabilities_for(user)))


def require_capability(user, capability):
    if not has_capability(user, capability):
        raise PermissionDenied(
            f'This project action requires the {capability} capability.')


def _audit(actor, action, project, detail=None):
    IntelligenceAudit.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action=action, target_type='Project', target_id=project.pk,
        detail=detail or {})


def format_project_code(year, number):
    return f'KPN-PRJ-{year:04d}-{number:05d}'


@transaction.atomic
def allocate_project_code():
    """Allocate the next KPN-PRJ code for the current year."""
    year = timezone.localdate().year
    sequence, _created = ProjectSequence.objects.get_or_create(year=year)
    sequence = ProjectSequence.objects.select_for_update().get(year=year)
    sequence.last_number += 1
    sequence.save(update_fields=['last_number'])
    return format_project_code(year, sequence.last_number)


@transaction.atomic
def create_project(actor, *, source_cluster=None, source_publication=None,
                   **fields):
    """Register a project and allocate its permanent code.

    ``fields`` carries only what a source documents — the model
    leaves every undocumented fact blank/NULL, and this service never
    invents one.
    """
    require_capability(actor, 'MANAGE_PROJECTS')
    project = Project(
        created_by=actor, source_cluster=source_cluster,
        source_publication=source_publication, **fields)
    project.project_code = allocate_project_code()
    project.save()
    ProjectMilestone.objects.create(
        project=project, date=timezone.localdate(),
        title='Project registered for tracking',
        body='Registered from the project desk.'
        if not (source_cluster or source_publication) else
        'Registered from a verified intelligence desk unit.',
        status_after=project.status, recorded_by=actor)
    _audit(actor, 'PROJECT_CREATED', project,
           {'status': project.status,
            'from_desk_unit': bool(source_cluster or source_publication)})
    return project


def qualifying_evidence(project):
    """Evidence records that can support a guarded verification
    finding: field inspections and official records (Doc 03 §2.6)."""
    return list(project.evidence.filter(
        kind__in=PROJECT_VERIFYING_EVIDENCE_KINDS).order_by('created_at', 'pk'))


def _check_verification_guard(project, actor, new_status):
    """The VERIFIED_ABANDONED / COMPLETED_VERIFIED guard (Doc 03 §2.6).

    Returns the qualifying evidence record the finding rests on.
    Raises ProjectError with nothing saved when any leg fails:
    capability, qualifying evidence on record, or the verifier being
    the same person who reported that evidence.
    """
    require_capability(actor, 'VERIFY_PROJECTS')
    label = dict(PROJECT_STATUSES)[new_status]
    candidates = qualifying_evidence(project)
    if not candidates:
        raise ProjectError(
            f'“{label}” requires a field inspection or official record '
            'on the project’s evidence timeline first.')
    for evidence in candidates:
        if evidence.captured_by_id != actor.pk:
            return evidence
    raise ProjectError(
        f'“{label}” must be verified by someone other than the person '
        'who reported the supporting evidence.')


@transaction.atomic
def set_project_status(project, new_status, actor, note=''):
    """Move a project to a new status, recording the milestone.

    Guarded statuses go through :func:`_check_verification_guard`.
    Terminal (verified-final) statuses can only be challenged into
    DISPUTED, never silently rewritten.
    """
    require_capability(actor, 'MANAGE_PROJECTS')
    if new_status not in dict(PROJECT_STATUSES):
        raise ProjectError(f'Unknown project status: {new_status}')
    project = Project.objects.select_for_update().get(pk=project.pk)
    old = project.status
    if old == new_status:
        return project
    if old in PROJECT_TERMINAL_STATUSES and new_status != 'DISPUTED':
        raise ProjectError(
            f'“{dict(PROJECT_STATUSES)[old]}” is a verified finding. '
            'It can only be challenged by moving the project to Disputed.')
    basis = None
    if new_status in GUARDED_STATUSES:
        basis = _check_verification_guard(project, actor, new_status)
    project.status = new_status
    project.save(update_fields=['status', 'updated_at'])
    body = (note or '').strip()
    if basis is not None:
        basis_line = (f'Verification basis: {basis.get_kind_display()} — '
                      f'“{basis.title}” (evidence #{basis.pk}).')
        body = f'{body}\n{basis_line}'.strip()
    milestone = ProjectMilestone.objects.create(
        project=project, date=timezone.localdate(),
        title=f'Status changed to {project.get_status_display()}',
        body=body[:4000], status_after=new_status, recorded_by=actor)
    if basis is not None and basis.milestone_id is None:
        basis.milestone = milestone
        basis.save(update_fields=['milestone'])
    _audit(actor, 'PROJECT_STATUS_CHANGED', project,
           {'from': old, 'to': new_status,
            'basis_evidence_id': basis.pk if basis else None})
    if new_status == 'VERIFIED_ABANDONED':
        # Phase 6 alert rule (once per verification milestone).
        try:
            from . import alerts as alert_service
            alert_service.fire_project_verified_abandoned(project, milestone)
        except Exception:  # alerting never breaks a guarded transition
            pass
    return project


@transaction.atomic
def add_milestone(project, actor, *, date, title, body=''):
    """Append a timeline entry that does not change the status."""
    require_capability(actor, 'MANAGE_PROJECTS')
    milestone = ProjectMilestone.objects.create(
        project=project, date=date, title=title, body=body,
        recorded_by=actor)
    _audit(actor, 'PROJECT_MILESTONE_ADDED', project,
           {'milestone_id': milestone.pk})
    return milestone


@transaction.atomic
def add_evidence(project, actor, **fields):
    """File one evidence record on a project.

    The filer is recorded as ``captured_by`` (internal only) — the
    guarded-status rule depends on knowing who reported evidence so
    the verifier can be a different person.
    """
    require_capability(actor, 'MANAGE_PROJECTS')
    evidence = ProjectEvidence.objects.create(
        project=project, captured_by=actor, **fields)
    _audit(actor, 'PROJECT_EVIDENCE_ADDED', project,
           {'evidence_id': evidence.pk, 'kind': evidence.kind,
            'verification_state': evidence.verification_state,
            'is_public': evidence.is_public})
    return evidence


@transaction.atomic
def propose_from_unit(actor, unit):
    """Prefill data for registering a project from a verified desk unit.

    Returns a dict of initial form values drawn ONLY from the unit's
    own records (its title, its LGA, its member items' source) — the
    staff member confirms and completes the registration; nothing is
    created by this helper and no fact is inferred.
    """
    from . import desk as desk_service
    if unit.desk_state not in ('VERIFIED', 'APPROVED', 'PUBLISHED'):
        raise ProjectError(
            'A project can only be proposed from a verified desk unit.')
    members = desk_service.unit_members(unit)
    first = members[0] if members else None
    lga = desk_service.unit_lga(unit)
    initial = {
        'title': desk_service.unit_title(unit)[:300],
        'description': '',
        'lga': lga.pk if lga else None,
        'source_url': (first.original_url or '')[:500] if first else '',
    }
    return initial
