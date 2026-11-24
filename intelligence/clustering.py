"""Event clustering for raw publications (Phase 3).

Groups items that report the SAME event into an :class:`EventCluster`.
The rule is deliberately conservative — a wrong merge is worse than a
wrong split — so an item joins or forms a cluster only when ALL of
these hold against the cluster (or the partner item):

- a shared LGA (from the item's matched locations),
- the same primary category suggestion,
- title similarity at or above the cluster threshold (or a strong
  shared-token overlap), and
- event times inside the cluster window (72 hours by default).

Items with no matched LGA or no primary category are never
auto-clustered. Clustering links records; it never deletes or edits
them (Doc 03 §2.4). An item already in a cluster is never moved by
the engine, and Phase 4 desk splits are permanent as far as the
engine is concerned: ``ClusterExclusion`` rows written by a split
block the engine from re-joining what staff separated (a human
merge clears them again).
"""
from datetime import timedelta
from difflib import SequenceMatcher

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ClusterExclusion, EventCluster, RawPublication, normalize_alias,
)

WINDOW_HOURS = 72
TITLE_THRESHOLD = 0.55
TOKEN_OVERLAP = 0.35


def _window_hours():
    return int(getattr(settings, 'KPN_INTELLIGENCE_CLUSTER_WINDOW_HOURS', WINDOW_HOURS))


def _title_threshold():
    return float(getattr(settings, 'KPN_INTELLIGENCE_CLUSTER_TITLE_SIMILARITY', TITLE_THRESHOLD))


def title_similarity(first, second):
    return SequenceMatcher(
        None, normalize_alias(first), normalize_alias(second)).ratio()


def _tokens(text):
    return {word for word in normalize_alias(text).split() if len(word) > 2}


def titles_match(first, second):
    if title_similarity(first, second) >= _title_threshold():
        return True
    one, two = _tokens(first), _tokens(second)
    if not one or not two:
        return False
    return len(one & two) / min(len(one), len(two)) >= TOKEN_OVERLAP


def _primary_category_id(pub):
    link = pub.category_links.filter(is_primary=True).first()
    return link.category_id if link else None


def _lga_ids(pub):
    return set(pub.locations.exclude(lga__isnull=True)
               .values_list('lga_id', flat=True))


def _within_window(first, second):
    window = timedelta(hours=_window_hours())
    return abs((first - second).total_seconds()) <= window.total_seconds()


def _pair_matches(pub, other, category_id, lga_ids):
    """The conservative pair rule: shared LGA + category + title + time."""
    if _primary_category_id(other) != category_id:
        return False
    if not (lga_ids & _lga_ids(other)):
        return False
    if not _within_window(pub.event_time, other.event_time):
        return False
    return titles_match(pub.title, other.title)


def _cluster_matches(pub, cluster, category_id, lga_ids):
    members = list(cluster.publications.all())
    if not members:
        return False
    member_lgas = set()
    for member in members:
        member_lgas |= _lga_ids(member)
    if not (lga_ids & member_lgas):
        return False
    earliest, latest = cluster.member_times()
    window = timedelta(hours=_window_hours())
    when = pub.event_time
    if when < earliest - window or when > latest + window:
        return False
    return any(titles_match(pub.title, member.title) for member in members)


def _new_cluster(first, second, category_id, shared_lga_id):
    earlier = min((first, second), key=lambda pub: (pub.event_time, pub.pk))
    cluster = EventCluster.objects.create(
        title=earlier.title[:300], category_id=category_id,
        primary_lga_id=shared_lga_id, created_from='RULE')
    RawPublication.objects.filter(pk__in=[first.pk, second.pk]).update(
        cluster=cluster)
    first.cluster = cluster
    second.cluster = cluster
    return cluster


def _exclusions_for(pub):
    """(cluster ids, partner item ids) a desk split forbids for *pub*."""
    rows = ClusterExclusion.objects.filter(publication=pub)
    cluster_ids = set(rows.exclude(cluster__isnull=True)
                      .values_list('cluster_id', flat=True))
    partner_ids = set(rows.exclude(other_publication__isnull=True)
                      .values_list('other_publication_id', flat=True))
    partner_ids |= set(ClusterExclusion.objects.filter(
        other_publication=pub).values_list('publication_id', flat=True))
    return cluster_ids, partner_ids


@transaction.atomic
def assign_cluster(pub):
    """Join or form a cluster for *pub*; returns the cluster or None.

    Idempotent: an item that already has a cluster keeps it. A
    near-duplicate follows its canonical item's cluster — the same
    story reported twice is one event by definition. Desk splits are
    respected: excluded clusters and excluded partners are skipped.
    """
    if pub.cluster_id:
        return pub.cluster
    excluded_clusters, excluded_partners = _exclusions_for(pub)
    if pub.duplicate_of_id and pub.duplicate_of.cluster_id:
        if pub.duplicate_of.cluster_id not in excluded_clusters:
            pub.cluster = pub.duplicate_of.cluster
            pub.save(update_fields=['cluster'])
            return pub.cluster
    category_id = _primary_category_id(pub)
    lga_ids = _lga_ids(pub)
    if category_id is None or not lga_ids:
        return None

    candidates = (
        EventCluster.objects.filter(state='OPEN', category_id=category_id)
        .prefetch_related('publications', 'publications__locations',
                          'publications__category_links')
        .order_by('-updated_at', '-pk'))
    for cluster in candidates:
        if cluster.pk in excluded_clusters:
            continue  # staff split this item out of that cluster
        members = list(cluster.publications.all())
        if any(member.pk in excluded_partners for member in members):
            continue  # staff separated this item from a member
        if _cluster_matches(pub, cluster, category_id, lga_ids):
            pub.cluster = cluster
            pub.save(update_fields=['cluster'])
            return cluster

    partners = (
        RawPublication.objects.filter(cluster__isnull=True)
        .exclude(pk=pub.pk)
        .filter(discovered_at__gte=timezone.now() - timedelta(days=30))
        .select_related('source')
        .prefetch_related('locations', 'category_links')
        .order_by('discovered_at', 'pk'))
    for other in partners:
        if other.pk in excluded_partners:
            continue  # staff separated these two items
        if other.duplicate_of_id and other.duplicate_of_id == pub.pk:
            continue  # a near-duplicate of this item, not a partner
        if _pair_matches(pub, other, category_id, lga_ids):
            shared = sorted(lga_ids & _lga_ids(other))
            return _new_cluster(pub, other, category_id, shared[0])
    return None
