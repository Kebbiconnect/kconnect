"""Verification desk services (Phase 4 — Lane 2, human-gated).

The desk works *units*: an :class:`EventCluster` (the natural review
unit) or a standalone :class:`RawPublication` that belongs to no
cluster. Both carry the same workflow fields (``desk_state``,
``assigned_to``, ``article``), so every function here accepts either.

Rules enforced in this layer — never only in templates:

- The state machine is a closed transition table. An action that is
  not legal from the unit's current state raises :class:`DeskError`;
  there is no way to reach a state except through its listed actions.
- Every action checks its capability (Doc 07) against the actor.
- Every action writes exactly one :class:`ReviewDecision` and one
  :class:`IntelligenceAudit` row. Audit detail never carries source
  text or PII (Doc 07 §5).
- REJECT requires a reason; REQUEST_INFO requires a note.
- APPROVE on a unit whose primary category is sensitive additionally
  requires APPROVE_SENSITIVE (Doc 03 §2.5).
- Conversion to the newsroom creates a **DRAFT** Campaign only. This
  module never calls ``publish_campaign`` and never sets a unit to
  PUBLISHED: that state is reached solely via
  :func:`sync_published_units`, driven by the article actually
  publishing through the normal newsroom flow.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.html import escape

from leadership.capabilities import capabilities_for

from .models import (
    ClusterExclusion, EventCluster, IntelligenceAudit, RawPublication,
    ReviewDecision, SourceHealth,
)


class DeskError(Exception):
    """A desk action that cannot be performed (illegal transition,
    missing reason, already converted, ...). Views surface the message."""


# action -> (allowed from-states, to-state, capability, note required)
TRANSITIONS = {
    'TRIAGE': (
        {'DISCOVERED'}, 'UNDER_REVIEW', 'REVIEW_INTELLIGENCE', False),
    'BEGIN_VERIFICATION': (
        {'UNDER_REVIEW'}, 'VERIFICATION_IN_PROGRESS',
        'REVIEW_INTELLIGENCE', False),
    'REQUEST_INFO': (
        {'UNDER_REVIEW', 'VERIFICATION_IN_PROGRESS'}, 'NEEDS_INFO',
        'REVIEW_INTELLIGENCE', True),
    'RESUME': (
        {'NEEDS_INFO'}, 'UNDER_REVIEW', 'REVIEW_INTELLIGENCE', False),
    'VERIFY': (
        {'VERIFICATION_IN_PROGRESS'}, 'VERIFIED', 'VERIFY_INTELLIGENCE', False),
    'DISPUTE': (
        {'VERIFIED'}, 'DISPUTED', 'VERIFY_INTELLIGENCE', False),
    'MARK_UNVERIFIED': (
        {'VERIFIED'}, 'UNVERIFIED', 'VERIFY_INTELLIGENCE', True),
    'REOPEN': (
        {'DISPUTED', 'UNVERIFIED'}, 'VERIFICATION_IN_PROGRESS',
        'VERIFY_INTELLIGENCE', False),
    # Phase 6 security desk: RESTRICTED handling (Doc 03 §2.5 side
    # state). Only units in a sensitive category can be restricted,
    # and only security-desk holders (VIEW_SECURITY_DESK — exactly
    # two staff titles, owner decision D6) can move them in or out.
    'RESTRICT': (
        {'DISCOVERED', 'UNDER_REVIEW', 'VERIFICATION_IN_PROGRESS',
         'NEEDS_INFO'}, 'RESTRICTED', 'VIEW_SECURITY_DESK', False),
    'RELEASE': (
        {'RESTRICTED'}, 'UNDER_REVIEW', 'VIEW_SECURITY_DESK', False),
    'APPROVE': (
        {'VERIFIED'}, 'APPROVED', 'APPROVE_INTELLIGENCE', False),
    'REJECT': (
        {'UNDER_REVIEW', 'VERIFICATION_IN_PROGRESS', 'NEEDS_INFO',
         'VERIFIED', 'DISPUTED'}, 'REJECTED', 'REVIEW_INTELLIGENCE', True),
    'MARK_DUPLICATE': (
        {'DISCOVERED', 'UNDER_REVIEW', 'VERIFICATION_IN_PROGRESS',
         'NEEDS_INFO'}, 'DUPLICATE', 'REVIEW_INTELLIGENCE', False),
    'ARCHIVE': (
        {'REJECTED', 'DUPLICATE', 'DISPUTED'}, 'ARCHIVED',
        'REVIEW_INTELLIGENCE', False),
}

# Imperative button labels for the desk UI (ReviewDecision.ACTIONS
# holds the past-tense labels used in the decision history).
ACTION_BUTTON_LABELS = {
    'TRIAGE': 'Triage into review',
    'BEGIN_VERIFICATION': 'Begin verification',
    'REQUEST_INFO': 'Request more evidence',
    'RESUME': 'Return to review',
    'VERIFY': 'Verify',
    'DISPUTE': 'Dispute',
    'REOPEN': 'Reopen for verification',
    'APPROVE': 'Approve — ready',
    'REJECT': 'Reject',
    'MARK_DUPLICATE': 'Mark duplicate',
    'ARCHIVE': 'Archive',
    'MARK_UNVERIFIED': 'Withdraw verification',
    'RESTRICT': 'Transfer to security desk',
    'RELEASE': 'Release to general desk',
}


# Intelligence category slug -> newsroom (Campaign) category, applied
# when a unit is converted to a draft (Doc 04 entity 16: the newsroom
# vocabulary stays untouched; a mapping translates at conversion).
CATEGORY_MAP = {
    'government-governance': 'GOVERNANCE',
    'politics-elections': 'GOVERNANCE',
    'security-public-safety': 'SECURITY',
    'education': 'EDUCATION',
    'healthcare': 'HEALTH',
    'agriculture-food-security': 'AGRICULTURE',
    'infrastructure-roads': 'INFRASTRUCTURE',
    'water-sanitation': 'INFRASTRUCTURE',
    'electricity-energy': 'INFRASTRUCTURE',
    'economy-employment': 'MARKETS',
    'business-investment': 'MARKETS',
    'environment-climate': 'ENVIRONMENT',
    'community-development': 'COMMUNITY',
    'human-rights-justice': 'CIVIC',
    'youth-sports': 'YOUTH',
    'women-social-development': 'WOMEN',
    'public-accountability': 'GOVERNANCE',
    'traditional-institutions': 'TRADITIONAL',
    'humanitarian-affairs': 'HUMAN_INTEREST',
    'emergencies-disasters': 'EMERGENCY',
    'opportunities-scholarships': 'GENERAL',
    'other': 'GENERAL',
}


def has_capability(user, capability):
    return bool(user is not None and user.is_authenticated
                and (user.is_superuser
                     or capability in capabilities_for(user)))


def require_capability(user, capability):
    if not has_capability(user, capability):
        raise PermissionDenied(
            f'This desk action requires the {capability} capability.')


def _is_cluster(unit):
    return isinstance(unit, EventCluster)


def _target_kwargs(unit):
    return {'cluster': unit} if _is_cluster(unit) else {'publication': unit}


def _audit(actor, action, unit, detail=None):
    IntelligenceAudit.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action=action,
        target_type='EventCluster' if _is_cluster(unit) else 'RawPublication',
        target_id=unit.pk, detail=detail or {})


def _record(actor, unit, action, from_state, to_state, note=''):
    decision = ReviewDecision.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action=action, from_state=from_state, to_state=to_state,
        note=(note or '')[:2000], **_target_kwargs(unit))
    _audit(actor, f'DESK_{action}', unit,
           {'from_state': from_state, 'to_state': to_state})
    return decision


def unit_title(unit):
    return unit.title


def unit_members(unit):
    """The evidence items behind a unit, oldest report first."""
    if _is_cluster(unit):
        return list(unit.publications.select_related('source')
                    .order_by('published_at', 'discovered_at', 'pk'))
    return [unit]


def unit_category(unit):
    if _is_cluster(unit):
        return unit.category
    link = unit.category_links.filter(is_primary=True).select_related(
        'category').first()
    return link.category if link else None


def unit_is_sensitive(unit):
    category = unit_category(unit)
    return bool(category is not None and category.is_sensitive)


def unit_lga(unit):
    if _is_cluster(unit):
        return unit.primary_lga
    location = (unit.locations.filter(match_kind='EXPLICIT')
                .exclude(lga__isnull=True).select_related('lga').first())
    if location is None:
        location = (unit.locations.exclude(lga__isnull=True)
                    .select_related('lga').first())
    return location.lga if location else None


def available_actions(unit, user):
    """The transition actions *user* may legally take on *unit* now."""
    actions = []
    for action, (from_states, _to, capability, _note) in TRANSITIONS.items():
        if unit.desk_state in from_states and has_capability(user, capability):
            if action == 'APPROVE' and unit_is_sensitive(unit) \
                    and not has_capability(user, 'APPROVE_SENSITIVE'):
                continue
            if action == 'RESTRICT' and not unit_is_sensitive(unit):
                continue
            actions.append(action)
    return actions


@transaction.atomic
def apply_transition(unit, actor, action, note=''):
    """Perform one guarded state transition and record the decision."""
    if action not in TRANSITIONS:
        raise DeskError(f'Unknown desk action: {action}')
    from_states, to_state, capability, note_required = TRANSITIONS[action]
    require_capability(actor, capability)
    if action == 'APPROVE' and unit_is_sensitive(unit):
        require_capability(actor, 'APPROVE_SENSITIVE')
    if note_required and not (note or '').strip():
        raise DeskError(
            'A reason is required for this action.'
            if action == 'REJECT' else
            'A note describing the evidence needed is required.'
            if action == 'REQUEST_INFO' else
            'A note is required for this action.')
    if action == 'RESTRICT' and not unit_is_sensitive(unit):
        raise DeskError(
            'Only a unit in a sensitive category can be transferred '
            'to the security desk.')
    passed = unit
    unit = type(unit).objects.select_for_update().get(pk=unit.pk)
    if unit.desk_state not in from_states:
        raise DeskError(
            f'Cannot {action.lower().replace("_", " ")} a unit that is '
            f'{unit.get_desk_state_display().lower()}.')
    from_state = unit.desk_state
    unit.desk_state = to_state
    unit.save(update_fields=['desk_state'])
    passed.desk_state = to_state
    decision = _record(actor, unit, action, from_state, to_state, note)
    if action == 'VERIFY' and unit_is_sensitive(unit):
        # Phase 6 alert rule: a restricted/security unit is verified.
        # Alerting never blocks or breaks a desk decision.
        try:
            from . import alerts as alert_service
            alert_service.fire_security_verified(unit, decision)
        except Exception:
            pass
    return decision


@transaction.atomic
def assign_reviewer(unit, actor, assignee):
    """Assign a unit to a reviewer (no state change; decision recorded)."""
    require_capability(actor, 'REVIEW_INTELLIGENCE')
    if assignee is None or not assignee.is_authenticated \
            or not assignee.is_active:
        raise DeskError('Choose a reviewer.')
    if not (has_capability(assignee, 'REVIEW_INTELLIGENCE')
            or has_capability(assignee, 'VERIFY_INTELLIGENCE')):
        raise DeskError('The assignee does not hold a desk capability.')
    passed = unit
    unit = type(unit).objects.select_for_update().get(pk=unit.pk)
    if unit.desk_state in ('PUBLISHED', 'ARCHIVED'):
        raise DeskError('This unit is closed and cannot be assigned.')
    unit.assigned_to = assignee
    unit.save(update_fields=['assigned_to'])
    passed.assigned_to = assignee
    return _record(actor, unit, 'ASSIGN', unit.desk_state, unit.desk_state,
                   note=f'Assigned to {assignee.get_username()}.')


@transaction.atomic
def merge_clusters(actor, target, source_cluster, note=''):
    """Merge *source_cluster* into *target*; the source retires intact.

    Members move to the target; the source cluster is kept with
    state=MERGED and merged_into set (records are never destroyed).
    Exclusions between the two groups are cleared — a human merge
    overrides an earlier human split.
    """
    require_capability(actor, 'REVIEW_INTELLIGENCE')
    if target.pk == source_cluster.pk:
        raise DeskError('Choose a different cluster to merge.')
    target = EventCluster.objects.select_for_update().get(pk=target.pk)
    source_cluster = EventCluster.objects.select_for_update().get(
        pk=source_cluster.pk)
    for cluster in (target, source_cluster):
        if cluster.state != 'OPEN':
            raise DeskError('Only open clusters can be merged.')
    moved = list(source_cluster.publications.all())
    kept = list(target.publications.all())
    if moved and kept:
        ClusterExclusion.objects.filter(
            publication__in=moved, other_publication__in=kept).delete()
        ClusterExclusion.objects.filter(
            publication__in=kept, other_publication__in=moved).delete()
        ClusterExclusion.objects.filter(
            publication__in=moved, cluster=target).delete()
    RawPublication.objects.filter(pk__in=[p.pk for p in moved]).update(
        cluster=target)
    source_cluster.state = 'MERGED'
    source_cluster.merged_into = target
    source_cluster.save(update_fields=['state', 'merged_into', 'updated_at'])
    decision = _record(
        actor, target, 'MERGE', target.desk_state, target.desk_state,
        note=note or f'Merged cluster #{source_cluster.pk} into this cluster.')
    _record(actor, source_cluster, 'MERGE', source_cluster.desk_state,
            source_cluster.desk_state,
            note=f'Merged into cluster #{target.pk}.')
    _audit(actor, 'CLUSTER_MERGED', target,
           {'merged_cluster_id': source_cluster.pk,
            'items_moved': len(moved)})
    return decision


@transaction.atomic
def split_cluster(actor, cluster, item_pks, note=''):
    """Move selected member items out of *cluster*.

    Two or more items form a new manual cluster (starting at
    DISCOVERED — it needs its own review); a single item becomes a
    standalone unit. Either way, exclusions are written so the
    clustering engine never silently undoes the split.
    """
    require_capability(actor, 'REVIEW_INTELLIGENCE')
    cluster = EventCluster.objects.select_for_update().get(pk=cluster.pk)
    if cluster.state != 'OPEN':
        raise DeskError('Only open clusters can be split.')
    members = list(cluster.publications.all())
    member_ids = {member.pk for member in members}
    chosen_ids = [int(pk) for pk in item_pks if str(pk).isdigit()]
    chosen = [m for m in members if m.pk in chosen_ids]
    if not chosen:
        raise DeskError('Select at least one item to split out.')
    if len(chosen) == len(members):
        raise DeskError('A split must leave at least one item in the cluster.')
    remaining = [m for m in members if m.pk not in {c.pk for c in chosen}]
    reason = (note or 'Split by the verification desk.')[:300]
    new_cluster = None
    if len(chosen) >= 2:
        earliest = min(chosen, key=lambda pub: (pub.event_time, pub.pk))
        new_cluster = EventCluster.objects.create(
            title=earliest.title[:300], category=cluster.category,
            primary_lga=cluster.primary_lga,
            primary_ward=cluster.primary_ward,
            primary_district=cluster.primary_district,
            primary_community=cluster.primary_community,
            primary_geo_entity=cluster.primary_geo_entity,
            created_from='MANUAL')
        RawPublication.objects.filter(
            pk__in=[c.pk for c in chosen]).update(cluster=new_cluster)
    else:
        RawPublication.objects.filter(pk=chosen[0].pk).update(cluster=None)
        ClusterExclusion.objects.create(
            publication=chosen[0], cluster=cluster, created_by=actor,
            reason=reason)
    for moved_item in chosen:
        for kept_item in remaining:
            ClusterExclusion.objects.create(
                publication=moved_item, other_publication=kept_item,
                created_by=actor, reason=reason)
            ClusterExclusion.objects.create(
                publication=kept_item, other_publication=moved_item,
                created_by=actor, reason=reason)
    decision = _record(
        actor, cluster, 'SPLIT', cluster.desk_state, cluster.desk_state,
        note=note or f'Split {len(chosen)} item(s) out of this cluster.')
    if new_cluster is not None:
        _record(actor, new_cluster, 'SPLIT', 'DISCOVERED', 'DISCOVERED',
                note=f'Created by a split from cluster #{cluster.pk}.')
    _audit(actor, 'CLUSTER_SPLIT', cluster,
           {'items_moved': len(chosen),
            'new_cluster_id': new_cluster.pk if new_cluster else None})
    return new_cluster


@transaction.atomic
def convert_to_draft(unit, actor):
    """Convert an APPROVED unit into a newsroom DRAFT Campaign.

    This is the whole of Lane 2's publishing power: a draft an editor
    then handles through the normal newsroom flow. The article is
    created in DRAFT status with no Story ID (IDs are allocated by
    ``publish_campaign`` at real publication), its evidence links are
    copied to ``story_intelligence.EvidenceRecord`` rows, and the unit
    records the link. The unit's state stays APPROVED until the
    article actually publishes (see :func:`sync_published_units`).
    """
    require_capability(actor, 'APPROVE_INTELLIGENCE')
    passed = unit
    unit = type(unit).objects.select_for_update().get(pk=unit.pk)
    if unit.desk_state != 'APPROVED':
        raise DeskError('Only an approved unit can be converted to a draft.')
    if unit.article_id:
        raise DeskError('This unit already has a newsroom draft.')
    from campaigns.models import Campaign
    from editorial.services import unique_slug
    from story_intelligence.models import EvidenceRecord

    members = unit_members(unit)
    if not members:
        raise DeskError('This unit has no source items to convert.')
    paragraphs = []
    if (unit.working_text or '').strip():
        # Phase 6: a prepared working copy governs the draft body —
        # for sensitive units this is the redacted text, never the
        # raw member reports. The originals stay untouched on the
        # restricted record.
        paragraphs = [part.strip() for part in
                      unit.working_text.split('\n') if part.strip()]
    else:
        for member in members:
            body = (member.text or member.summary or '').strip()
            if body:
                paragraphs.extend(
                    part.strip() for part in body.split('\n') if part.strip())
    content = '\n\n'.join(str(escape(part)) for part in paragraphs)
    blocks = [{'type': 'paragraph', 'data': {'text': str(escape(part))}}
              for part in paragraphs]
    category = unit_category(unit)
    campaign_category = CATEGORY_MAP.get(
        category.slug if category else '', 'GENERAL')
    first = members[0]
    lga = unit_lga(unit)
    article = Campaign.objects.create(
        author=actor, title=unit_title(unit)[:300],
        slug=unique_slug(Campaign, unit_title(unit)),
        content=content, content_json={'blocks': blocks},
        category=campaign_category, status='DRAFT',
        verification_status='DEVELOPING', reporter_credit='KPN_EDITORIAL',
        source_name=first.source.name[:200],
        source_url=(first.original_url or '')[:500],
        lga=lga, location=lga.name if lga else '')
    for member in members:
        EvidenceRecord.objects.create(
            article=article, kind='SOURCE_LINK',
            title=member.title[:200], url=(member.original_url or '')[:500],
            description=f'{member.source.name} — collected by the '
                        f'statewide intelligence desk.',
            added_by=actor)
    unit.article = article
    unit.save(update_fields=['article'])
    passed.article = article
    # Phase 7: record the article↔LGA associations the unit's own
    # evidence supports, so the public LGA news pages can ground the
    # story in a stored link (never a render-time guess).
    from . import article_locations
    article_locations.link_from_unit(unit, article, actor=actor)
    _record(actor, unit, 'CONVERT', 'APPROVED', 'APPROVED',
            note=f'Newsroom draft created (article #{article.pk}).')
    return article


def sync_published_units(article):
    """Advance APPROVED units linked to *article* to PUBLISHED.

    Called from a Campaign post_save signal: the only way a unit
    reaches PUBLISHED is its article actually publishing through the
    normal newsroom flow (``publish_campaign``). Lane 1 articles have
    no linked units, so this is a no-op for them.
    """
    actor = article.approved_by
    for model in (EventCluster, RawPublication):
        for unit in model.objects.filter(article=article,
                                         desk_state='APPROVED'):
            unit.desk_state = 'PUBLISHED'
            unit.save(update_fields=['desk_state'])
            _record(actor, unit, 'PUBLISH', 'APPROVED', 'PUBLISHED',
                    note=f'Article #{article.pk} published via the newsroom.')


def source_credibility(source):
    """A source's track record, computed only from records that exist.

    No scores are invented: the panel shows the health record, how
    many items the source has produced, and how the desk decided the
    units those items belonged to (a unit counts once per source,
    however many of the source's items it contains).
    """
    try:
        health = source.intelligence_health
        health_state = health.state()
    except SourceHealth.DoesNotExist:
        health = None
        health_state = 'DISABLED' if not source.enabled else 'NEVER_RUN'
    items = RawPublication.objects.filter(source=source)
    verified_units = rejected_units = 0
    cluster_ids = set(items.exclude(cluster__isnull=True)
                      .values_list('cluster_id', flat=True))
    for cluster in EventCluster.objects.filter(pk__in=cluster_ids):
        if cluster.desk_state in ('VERIFIED', 'APPROVED', 'PUBLISHED'):
            verified_units += 1
        elif cluster.desk_state in ('REJECTED', 'DUPLICATE'):
            rejected_units += 1
    for item in items.filter(cluster__isnull=True):
        if item.desk_state in ('VERIFIED', 'APPROVED', 'PUBLISHED'):
            verified_units += 1
        elif item.desk_state in ('REJECTED', 'DUPLICATE'):
            rejected_units += 1
    return {
        'source': source,
        'health': health,
        'health_state': health_state,
        'items_collected': items.count(),
        'units_verified': verified_units,
        'units_rejected': rejected_units,
    }
