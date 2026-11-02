"""release_migrate: the deployment sequence that runs at every start.

Since v2.9.1 the release also backfills Story IDs automatically, so no
deploy step is manual anymore. These tests pin the ORDER of the steps
inside the PostgreSQL advisory lock and the failure semantics:

- a backfill ERROR propagates and fails the release (Gunicorn never
  starts) — serving traffic with a broken backfill is worse than not
  deploying;
- the advisory unlock still runs when a step fails;
- the coverage report runs last and is advisory by contract (see
  story_intelligence's coverage tests: it reports and exits 0).

The command module's `connection` and `call_command` are replaced with
test doubles: the real advisory lock needs PostgreSQL, while the unit
suite runs on SQLite. The real end-to-end sequence is exercised by the
deployment simulation recorded in the v2.9.1 working notes.
"""
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.management.commands import release_migrate as rm


class _FakeCursor:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._log.append(sql)


class _FakeConnection:
    vendor = 'postgresql'

    def __init__(self):
        self.sql = []

    def cursor(self):
        return _FakeCursor(self.sql)


class ReleaseMigrateSequenceTests(TestCase):
    def _run(self, fail_on=None):
        """Run release_migrate with doubled connection/call_command.

        Returns (calls, connection) where calls is the ordered list of
        (command_name, kwargs) the release invoked. If fail_on names a
        command, that invocation raises CommandError.
        """
        calls = []

        def fake_call_command(name, **kwargs):
            calls.append((name, kwargs))
            if name == fail_on:
                raise CommandError(f'{name} failed (test double)')

        connection = _FakeConnection()
        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', fake_call_command):
            call_command('release_migrate')
        return calls, connection

    def test_full_sequence_in_order_inside_the_lock(self):
        calls, connection = self._run()
        self.assertEqual(
            [name for name, _ in calls],
            ['check_release', 'migrate', 'check_release',
             'backfill_story_ids', 'check_story_id_coverage'])
        # Preflight/postflight keep their database checks; migrate
        # stays non-interactive.
        self.assertEqual(calls[0][1], {'database': True})
        self.assertEqual(calls[1][1], {'interactive': False})
        self.assertEqual(calls[2][1], {'database': True})
        # Lock first, unlock last — everything above ran between them.
        self.assertEqual(
            connection.sql,
            ['SELECT pg_advisory_lock(%s)', 'SELECT pg_advisory_unlock(%s)'])

    def test_backfill_failure_fails_the_release(self):
        with self.assertRaises(CommandError):
            self._run(fail_on='backfill_story_ids')

    def test_backfill_failure_skips_coverage_but_still_unlocks(self):
        calls = []
        connection = _FakeConnection()

        def fake_call_command(name, **kwargs):
            calls.append(name)
            if name == 'backfill_story_ids':
                raise CommandError('backfill failed (test double)')

        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', fake_call_command):
            with self.assertRaises(CommandError):
                call_command('release_migrate')
        self.assertNotIn('check_story_id_coverage', calls)
        self.assertEqual(connection.sql[-1], 'SELECT pg_advisory_unlock(%s)')

    def test_migrate_failure_never_reaches_the_backfill(self):
        calls = []
        connection = _FakeConnection()

        def fake_call_command(name, **kwargs):
            calls.append(name)
            if name == 'migrate':
                raise CommandError('migrate failed (test double)')

        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', fake_call_command):
            with self.assertRaises(CommandError):
                call_command('release_migrate')
        self.assertNotIn('backfill_story_ids', calls)
        self.assertEqual(connection.sql[-1], 'SELECT pg_advisory_unlock(%s)')

    def test_non_postgres_is_rejected(self):
        connection = _FakeConnection()
        connection.vendor = 'sqlite'
        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', lambda *a, **k: None):
            with self.assertRaises(CommandError):
                call_command('release_migrate')
        self.assertEqual(connection.sql, [])
