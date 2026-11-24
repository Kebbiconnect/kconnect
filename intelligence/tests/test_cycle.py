"""Collection cycle: lease locking, run records, due selection, health."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from editorial.models import Source
from intelligence import cycle
from intelligence.models import CollectionControl, CollectionRun, SourceHealth


def make_source(name='Test Source', **kw):
    defaults = {'kind': 'NEWS', 'url': f'https://example.com/{name.replace(" ", "-").lower()}',
                'enabled': True}
    defaults.update(kw)
    return Source.objects.create(name=name, **defaults)


class RegistryIsolation:
    """Snapshot the connector registry and restore it after the test.

    Phase 2 registered real connectors in cycle.CONNECTORS; tests that
    assert bookkeeping-only behaviour (or substitute their own
    connectors) must not leak registry changes into other tests.
    """
    def setUp(self):
        self._saved_connectors = dict(cycle.CONNECTORS)

    def tearDown(self):
        cycle.CONNECTORS.clear()
        cycle.CONNECTORS.update(self._saved_connectors)


class RunRecordTests(RegistryIsolation, TestCase):
    def setUp(self):
        super().setUp()
        # Bookkeeping assertions predate live connectors: pin the
        # registry empty so no real fetch is attempted.
        cycle.CONNECTORS.clear()
    def test_cycle_creates_completed_run_record(self):
        make_source()
        run = cycle.run_cycle()
        self.assertEqual(run.status, 'COMPLETED')
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.sources_due, 1)
        self.assertEqual(run.sources_ok, 1)
        self.assertEqual(run.sources_failed, 0)
        self.assertEqual(CollectionRun.objects.count(), 1)

    def test_disabled_sources_are_not_due(self):
        make_source('Off Source', enabled=False)
        run = cycle.run_cycle()
        self.assertEqual(run.sources_due, 0)

    def test_source_not_due_again_within_its_interval(self):
        make_source()
        cycle.run_cycle()
        second = cycle.run_cycle()
        self.assertEqual(second.sources_due, 0)
        self.assertEqual(CollectionRun.objects.count(), 2)

    def test_source_due_again_after_interval(self):
        source = make_source()
        health, _ = SourceHealth.objects.get_or_create(source=source)
        health.last_cycle_at = timezone.now() - timedelta(minutes=31)
        health.save()
        self.assertIn(source, cycle.due_sources())
        health.last_cycle_at = timezone.now() - timedelta(minutes=10)
        health.save()
        self.assertNotIn(source, cycle.due_sources())

    def test_command_creates_run(self):
        out = StringIO()
        call_command('run_intelligence', '--trigger', 'MANUAL', stdout=out)
        self.assertEqual(CollectionRun.objects.count(), 1)
        self.assertEqual(CollectionRun.objects.get().trigger, 'MANUAL')
        self.assertIn('COMPLETED', out.getvalue())


class LeaseTests(TestCase):
    def test_second_cycle_refused_while_lease_held(self):
        control, _ = CollectionControl.objects.get_or_create(pk=1)
        control.lease_token = 'someone-else'
        control.lease_until = timezone.now() + timedelta(minutes=10)
        control.save()
        run = cycle.run_cycle()
        self.assertEqual(run.status, 'SKIPPED_LEASED')
        # The skip is itself recorded — a refused cycle is never silent.
        self.assertEqual(CollectionRun.objects.filter(status='SKIPPED_LEASED').count(), 1)

    def test_lease_released_after_cycle(self):
        cycle.run_cycle()
        control = CollectionControl.objects.get(pk=1)
        self.assertEqual(control.lease_token, '')
        self.assertIsNone(control.lease_until)

    def test_paused_control_records_paused_run(self):
        control, _ = CollectionControl.objects.get_or_create(pk=1)
        control.enabled = False
        control.save()
        run = cycle.run_cycle()
        self.assertEqual(run.status, 'PAUSED')


class FailureIsolationTests(RegistryIsolation, TestCase):
    def test_one_failing_source_does_not_stop_the_cycle(self):
        failing = make_source('Failing Source', connector_kind='RSS')
        healthy = make_source('Healthy Source', connector_kind='PAGE')

        def boom(source):
            raise RuntimeError('feed unreachable')

        def fine(source):
            return 3

        cycle.CONNECTORS.update({'RSS': boom, 'PAGE': fine})
        run = cycle.run_cycle()
        self.assertEqual(run.status, 'COMPLETED')
        self.assertEqual(run.sources_ok, 1)
        self.assertEqual(run.sources_failed, 1)
        self.assertEqual(run.items_new, 3)
        fail_health = SourceHealth.objects.get(source=failing)
        self.assertEqual(fail_health.consecutive_failures, 1)
        self.assertIn('feed unreachable', fail_health.last_error)
        self.assertEqual(fail_health.state(), 'FAILING')
        ok_health = SourceHealth.objects.get(source=healthy)
        self.assertIsNotNone(ok_health.last_success_at)
        self.assertEqual(ok_health.state(), 'OK')


class MissedCycleTests(TestCase):
    def test_no_runs_yet(self):
        health = cycle.cycle_health()
        self.assertEqual(health['state'], 'NO_RUNS_YET')
        self.assertFalse(health['missed'])

    def test_recent_run_is_on_time(self):
        CollectionRun.objects.create(status='COMPLETED', started_at=timezone.now())
        health = cycle.cycle_health()
        self.assertEqual(health['state'], 'ON_TIME')
        self.assertFalse(health['missed'])

    def test_gap_is_flagged_as_missed(self):
        CollectionRun.objects.create(
            status='COMPLETED', started_at=timezone.now() - timedelta(hours=3))
        health = cycle.cycle_health()
        self.assertEqual(health['state'], 'MISSED')
        self.assertTrue(health['missed'])
        self.assertGreaterEqual(health['gap_minutes'], 179)
