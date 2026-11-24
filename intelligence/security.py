"""Security desk services (Phase 6 — restricted handling).

A unit (cluster or standalone item) is RESTRICTED when its primary
category is one of the sensitive categories seeded in Phase 1
(politics, security, human rights, public accountability). Restricted
handling is enforced here, in the queryset layer — never by hiding
links in templates:

- :func:`visible_clusters` / :func:`visible_items` return the
  querysets every general surface (desk queue, items view, clusters
  view, overview counts) must use; for anyone without
  VIEW_SECURITY_DESK the restricted records are simply not in them,
  so counts cannot leak their existence (Doc 07 §4).
- The capability itself is held by exactly two staff titles — the
  Director of Media & Communications and the President (owner
  decision D6, 23 Nov 2026; mapping in leadership/capabilities.py).

Working copies and redaction: a holder can prepare a unit's working
copy from its member reports and blank passages out of it. The
original evidence records are never altered — redaction touches only
the working copy, and conversion to a newsroom draft uses the working
copy when one exists (desk.convert_to_draft). Every redaction writes
an IntelligenceAudit row whose detail records only how much was
removed, never the removed text (Doc 07 §5).
"""
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from . import desk as desk_service
from .models import (
    EventCluster, IncidentClaim, IntelligenceAudit, RawPublication,
    SecurityIncident,
)

REDACTION_MARKER = '[REDACTED]'


class SecurityError(Exception):
    """A security-desk action that cannot be performed."""


def is_holder(user):
    return desk_service.has_capability(user, 'VIEW_SECURITY_DESK')


def require_holder(user):
    if not is_holder(user):
        raise PermissionDenied(
            'This area requires the VIEW_SECURITY_DESK capability.')


def unit_is_restricted(unit):
    """A unit is restricted when its primary category is sensitive."""
    return desk_service.unit_is_sensitive(unit)


# ---------------------------------------------------------------------------
# Visibility — the querysets general surfaces must use
# ---------------------------------------------------------------------------

def restricted_cluster_ids():
    return EventCluster.objects.filter(
        category__is_sensitive=True).values('pk')


def restricted_item_ids():
    """Items restricted in their own right or through their cluster."""
    return RawPublication.objects.filter(
        Q(category_links__is_primary=True,
          category_links__category__is_sensitive=True)
        | Q(cluster__category__is_sensitive=True)).values('pk')


def visible_clusters(user, base=None):
    qs = base if base is not None else EventCluster.objects.all()
    if is_holder(user):
        return qs
    return qs.exclude(pk__in=restricted_cluster_ids())


def visible_items(user, base=None):
    qs = base if base is not None else RawPublication.objects.all()
    if is_holder(user):
        return qs
    return qs.exclude(pk__in=restricted_item_ids())


def restricted_clusters():
    return (EventCluster.objects.filter(state='OPEN', category__is_sensitive=True)
            .select_related('category', 'primary_lga', 'assigned_to')
            .prefetch_related('publications'))


def restricted_items():
    """Standalone items whose own primary category is sensitive."""
    return (RawPublication.objects.filter(cluster__isnull=True)
            .filter(pk__in=RawPublication.objects.filter(
                category_links__is_primary=True,
                category_links__category__is_sensitive=True))
            .select_related('source', 'assigned_to')
            .prefetch_related('category_links__category', 'locations__lga'))


# ---------------------------------------------------------------------------
# Working copy + redaction
# ---------------------------------------------------------------------------

def _audit(actor, action, target_type, target_id, detail=None):
    IntelligenceAudit.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action=action, target_type=target_type, target_id=target_id,
        detail=detail or {})


def _target_type(unit):
    return 'EventCluster' if isinstance(unit, EventCluster) else 'RawPublication'


def prepare_working_copy(unit, actor):
    """(Re)build a unit's working copy from its member reports."""
    require_holder(actor)
    if not unit_is_restricted(unit):
        raise SecurityError(
            'Working copies are prepared on the security desk, for '
            'restricted units only.')
    parts = []
    for member in desk_service.unit_members(unit):
        body = (member.text or member.summary or '').strip()
        parts.append(f'{member.title}\n{body}' if body else member.title)
    unit.working_text = '\n\n'.join(parts)
    unit.save(update_fields=['working_text'])
    _audit(actor, 'SECURITY_WORKING_COPY', _target_type(unit), unit.pk,
           {'characters': len(unit.working_text)})
    return unit


def redact_passage(unit, actor, passage):
    """Blank every occurrence of *passage* in a unit's working copy.

    The original evidence records are untouched; only the working
    copy changes. The audit row records the number of occurrences and
    the passage length — never the passage itself.
    """
    require_holder(actor)
    passage = (passage or '').strip()
    if not passage:
        raise SecurityError('Enter the exact passage to blank out.')
    if not (unit.working_text or '').strip():
        raise SecurityError(
            'Prepare the working copy before redacting it.')
    occurrences = unit.working_text.count(passage)
    if not occurrences:
        raise SecurityError(
            'That passage does not appear in the working copy.')
    unit.working_text = unit.working_text.replace(passage, REDACTION_MARKER)
    unit.save(update_fields=['working_text'])
    _audit(actor, 'SECURITY_REDACTION', _target_type(unit), unit.pk,
           {'occurrences': occurrences, 'passage_length': len(passage)})
    return occurrences


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

def create_incident(actor, **fields):
    require_holder(actor)
    unit = fields.pop('unit', None)
    if unit is not None:
        if isinstance(unit, EventCluster):
            fields['cluster'] = unit
        else:
            fields['publication'] = unit
        fields.setdefault('title', unit.title[:300])
        fields.setdefault('lga', desk_service.unit_lga(unit))
    incident = SecurityIncident.objects.create(created_by=actor, **fields)
    _audit(actor, 'SECURITY_INCIDENT_CREATED', 'SecurityIncident',
           incident.pk, {'status': incident.status})
    return incident


def add_claim(actor, incident, *, label, count, source_name, source_url=''):
    """Record one figure as an attributed claim — never as fact."""
    require_holder(actor)
    claim = IncidentClaim.objects.create(
        incident=incident, label=label, count=count,
        source_name=source_name, source_url=source_url or '',
        created_by=actor)
    _audit(actor, 'SECURITY_CLAIM_ADDED', 'SecurityIncident', incident.pk,
           {'claim_id': claim.pk})
    return claim


def set_incident_status(actor, incident, status):
    require_holder(actor)
    if status not in dict(SecurityIncident.STATUS):
        raise SecurityError(f'Unknown incident status: {status}')
    old = incident.status
    incident.status = status
    incident.save(update_fields=['status', 'updated_at'])
    _audit(actor, 'SECURITY_INCIDENT_STATUS', 'SecurityIncident',
           incident.pk, {'from': old, 'to': status})
    return incident


def redact_incident_notes(actor, incident, passage):
    """Blank a passage in an incident's working notes (audit-logged)."""
    require_holder(actor)
    passage = (passage or '').strip()
    if not passage:
        raise SecurityError('Enter the exact passage to blank out.')
    occurrences = (incident.working_notes or '').count(passage)
    if not occurrences:
        raise SecurityError(
            'That passage does not appear in the working notes.')
    incident.working_notes = incident.working_notes.replace(
        passage, REDACTION_MARKER)
    incident.save(update_fields=['working_notes', 'updated_at'])
    _audit(actor, 'SECURITY_REDACTION', 'SecurityIncident', incident.pk,
           {'occurrences': occurrences, 'passage_length': len(passage)})
    return occurrences


def claims_lines(incident):
    """Every figure on an incident, in its only permitted form."""
    return [claim.attribution for claim in incident.claims.all()]
