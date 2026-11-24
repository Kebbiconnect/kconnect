"""Bounded, lease-locked collection cycle.

An external scheduler (owner decision D2: free external scheduler) invokes
``run_intelligence`` roughly every 30 minutes. Each invocation:

1. Takes the CollectionControl lease (a second concurrent invocation is
   recorded as SKIPPED_LEASED and returns immediately).
2. Creates exactly one CollectionRun record — including for skipped and
   paused invocations — so missed cycles are visible, never silent.
3. Selects the sources that are due by their per-source poll interval.
4. Visits each due source through its registered connector, isolating
   failures per source and updating SourceHealth either way.

Phase 1 shipped the bookkeeping with an empty connector registry.
Phase 2 registers the RSS/page/official-page adapters (see
``intelligence/connectors.py``, built on the editorial fetcher chassis):
a connector returns the number of new items it stored and raises on
failure. Kinds without a connector (YOUTUBE_CHANNEL until an API key
exists, MANUAL desk submissions) are visited and recorded, never
fetched.
"""
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from editorial.models import Source

from .connectors import CONNECTORS
from .models import CollectionControl, CollectionRun, SourceHealth

LEASE_MINUTES = 20


def expected_cycle_minutes():
    return int(getattr(settings, 'KPN_INTELLIGENCE_CYCLE_MINUTES', 30))


def due_sources(now=None):
    """Enabled sources whose poll interval has elapsed since the last cycle visit."""
    now = now or timezone.now()
    due = []
    sources = (
        Source.objects.filter(enabled=True)
        .prefetch_related('intelligence_health')
        .order_by('pk')
    )
    for source in sources:
        try:
            health = source.intelligence_health
        except SourceHealth.DoesNotExist:
            health = None
        last = health.last_cycle_at if health else None
        if last is None or last + timedelta(minutes=max(1, source.poll_interval_minutes)) <= now:
            due.append(source)
    return due


@transaction.atomic
def _begin(trigger):
    """Acquire the lease and open the run record, or record the skip."""
    CollectionControl.objects.get_or_create(pk=1)
    control = CollectionControl.objects.select_for_update().get(pk=1)
    now = timezone.now()
    if not control.enabled:
        run = CollectionRun.objects.create(
            trigger=trigger, status='PAUSED', started_at=now, finished_at=now,
            error='Collection is paused.')
        return None, run
    if control.lease_until and control.lease_until > now:
        run = CollectionRun.objects.create(
            trigger=trigger, status='SKIPPED_LEASED', started_at=now, finished_at=now,
            error='Another collection cycle holds the lease.')
        return None, run
    token = uuid.uuid4().hex
    control.lease_token = token
    control.lease_until = now + timedelta(minutes=LEASE_MINUTES)
    control.save(update_fields=['lease_token', 'lease_until', 'updated_at'])
    run = CollectionRun.objects.create(trigger=trigger, status='RUNNING', started_at=now)
    return (token, run), None


def run_cycle(trigger='SCHEDULED', max_seconds=600):
    """Run one bounded collection cycle and return its CollectionRun."""
    begun, skipped = _begin(trigger)
    if skipped is not None:
        return skipped
    token, run = begun
    start = time.monotonic()
    ok = failed = items_new = 0
    errors = []
    try:
        due = due_sources()
        run.sources_due = len(due)
        for source in due:
            if time.monotonic() - start > max_seconds:
                errors.append('Time budget exhausted before all due sources were visited.')
                break
            health, _ = SourceHealth.objects.get_or_create(source=source)
            health.last_cycle_at = timezone.now()
            connector = CONNECTORS.get(source.connector_kind)
            try:
                if connector is not None:
                    items_new += int(connector(source) or 0)
                    health.last_success_at = timezone.now()
                    health.last_error = ''
                    health.consecutive_failures = 0
                ok += 1
            except Exception as exc:  # one source must never stop the cycle
                failed += 1
                health.consecutive_failures += 1
                health.last_error = (str(exc) or type(exc).__name__)[:300]
                errors.append(f'{source.name}: {type(exc).__name__}')
            health.save()
            # Mirror the outcome onto the Source row's own monitoring
            # fields (editorial/0003) so both health surfaces agree.
            Source.objects.filter(pk=source.pk).update(
                last_success_at=health.last_success_at,
                last_error=health.last_error,
                consecutive_failures=health.consecutive_failures)
            CollectionControl.objects.filter(pk=1, lease_token=token).update(
                lease_until=timezone.now() + timedelta(minutes=LEASE_MINUTES))
        # Phase 3: process whatever intake is waiting (relevance,
        # categories, dedupe, clustering) inside the same lease and
        # time budget. Processing failures never fail the cycle.
        try:
            from .relevance import process_pending
            process_pending(deadline=start + max_seconds)
        except Exception as exc:  # processing must never stop collection
            errors.append(f'Processing: {type(exc).__name__}')
        run.sources_ok = ok
        run.sources_failed = failed
        run.items_new = items_new
        run.status = 'COMPLETED'
        run.error = '; '.join(errors)[:300]
    except Exception as exc:  # cycle-level failure: record it, never raise
        run.status = 'FAILED'
        run.error = type(exc).__name__
    finally:
        run.finished_at = timezone.now()
        run.save()
        CollectionControl.objects.filter(pk=1, lease_token=token).update(
            lease_token='', lease_until=None)
    # Phase 6: evaluate the source-health / missed-cycle alert rules
    # at the end of every cycle. Idempotent per day; alerting must
    # never fail a completed cycle.
    try:
        from .alerts import evaluate_cycle_alerts
        evaluate_cycle_alerts()
    except Exception:
        pass
    return run


def cycle_health(now=None):
    """Missed-cycle view over the run records.

    Returns a dict with state NO_RUNS_YET / ON_TIME / MISSED, the last
    completed run, the expected interval and the observed gap in minutes.
    """
    now = now or timezone.now()
    expected = expected_cycle_minutes()
    last = (
        CollectionRun.objects.filter(status='COMPLETED')
        .order_by('-started_at', '-pk')
        .first()
    )
    if last is None:
        return {'state': 'NO_RUNS_YET', 'last_run': None,
                'expected_minutes': expected, 'gap_minutes': None, 'missed': False}
    gap = int((now - last.started_at).total_seconds() // 60)
    missed = gap > expected + 15  # grace for approximate free schedulers
    return {'state': 'MISSED' if missed else 'ON_TIME', 'last_run': last,
            'expected_minutes': expected, 'gap_minutes': gap, 'missed': missed}
