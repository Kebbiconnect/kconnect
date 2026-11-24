"""release_migrate: the deployment sequence that runs at every start.

Since v2.9.1 the release also backfills Story IDs automatically, so no
deploy step is manual anymore. These tests pin the ORDER of the steps
inside the PostgreSQL advisory lock and the failure semantics:

- a backfill ERROR propagates and fails the release (Gunicorn never
  starts) — serving traffic with a broken backfill is worse than not
  deploying;
- the advisory unlock still runs when a step fails;
- since v3.0.0 the release also seeds the intelligence geographic
  directory (production deploys have no shell access, so no step may
  be manual); a seed ERROR is fail-safe — logged, never fatal — and
  the real wired path is exercised against the test database below;
- the final package adds two more fail-safe steps on the same terms:
  the starter source seed (seed_intelligence_sources) and the Phase 7
  article-location backfill (backfill_article_locations). Both are
  idempotent; either failing is logged and the release continues;
- the ICT Admin package adds one more fail-safe step on the same
  terms: seed_ict_admin records the Director of Media & Communications
  as the initial ICT Admin holder (idempotent, edit-preserving —
  a super admin's reassignment is never overwritten);
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
             'backfill_story_ids', 'seed_intelligence_directory',
             'seed_intelligence_sources', 'backfill_article_locations',
             'seed_ict_admin', 'check_story_id_coverage'])
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

    def test_seed_failure_is_fail_safe_and_the_release_continues(self):
        # Unlike the backfill, a seeding error must NOT fail the
        # release: it is logged, the coverage report still runs and
        # the advisory unlock still happens.
        calls, connection = self._run(fail_on='seed_intelligence_directory')
        self.assertEqual(
            [name for name, _ in calls],
            ['check_release', 'migrate', 'check_release',
             'backfill_story_ids', 'seed_intelligence_directory',
             'seed_intelligence_sources', 'backfill_article_locations',
             'seed_ict_admin', 'check_story_id_coverage'])
        self.assertEqual(connection.sql[-1], 'SELECT pg_advisory_unlock(%s)')

    def test_source_seed_failure_is_fail_safe(self):
        calls, connection = self._run(fail_on='seed_intelligence_sources')
        self.assertEqual(
            [name for name, _ in calls],
            ['check_release', 'migrate', 'check_release',
             'backfill_story_ids', 'seed_intelligence_directory',
             'seed_intelligence_sources', 'backfill_article_locations',
             'seed_ict_admin', 'check_story_id_coverage'])
        self.assertEqual(connection.sql[-1], 'SELECT pg_advisory_unlock(%s)')

    def test_location_backfill_failure_is_fail_safe(self):
        calls, connection = self._run(fail_on='backfill_article_locations')
        self.assertEqual(
            [name for name, _ in calls],
            ['check_release', 'migrate', 'check_release',
             'backfill_story_ids', 'seed_intelligence_directory',
             'seed_intelligence_sources', 'backfill_article_locations',
             'seed_ict_admin', 'check_story_id_coverage'])
        self.assertEqual(connection.sql[-1], 'SELECT pg_advisory_unlock(%s)')

    def test_ict_seed_failure_is_fail_safe(self):
        calls, connection = self._run(fail_on='seed_ict_admin')
        self.assertEqual(
            [name for name, _ in calls],
            ['check_release', 'migrate', 'check_release',
             'backfill_story_ids', 'seed_intelligence_directory',
             'seed_intelligence_sources', 'backfill_article_locations',
             'seed_ict_admin', 'check_story_id_coverage'])
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


CANONICAL_LGAS = {
    'Aleiro', 'Arewa', 'Argungu', 'Augie', 'Bagudo', 'Birnin Kebbi', 'Bunza',
    'Dandi', 'Fakai', 'Gwandu', 'Jega', 'Kalgo', 'Koko/Besse', 'Maiyama',
    'Ngaski', 'Sakaba', 'Shanga', 'Suru', 'Danko/Wasagu', 'Yauri', 'Zuru',
}


class ReleaseMigrateSeedingTests(TestCase):
    """The wired path itself: release_migrate must leave a fresh
    database with the full intelligence geographic directory, and a
    second start must change nothing.

    Only the connection is doubled (the advisory lock needs
    PostgreSQL); every step is stubbed EXCEPT
    seed_intelligence_directory, which runs for real against the test
    database — migrations have already run there, exactly as they have
    when the release reaches the seed step in production.
    """

    def _run_release(self):
        def dispatch(name, **kwargs):
            if name == 'seed_intelligence_directory':
                call_command(name, **kwargs)

        connection = _FakeConnection()
        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', dispatch):
            call_command('release_migrate')

    def test_release_seeds_exactly_21_canonical_lgas(self):
        from leadership.models import LGA, Zone

        self.assertEqual(LGA.objects.count(), 0)
        self._run_release()
        self.assertEqual(LGA.objects.count(), 21)
        self.assertEqual(
            set(LGA.objects.values_list('name', flat=True)), CANONICAL_LGAS)
        self.assertEqual(Zone.objects.count(), 3)

    def test_second_release_run_is_a_noop(self):
        from leadership.models import LGA, Zone
        from intelligence.models import GeoAlias

        self._run_release()
        before = (
            LGA.objects.count(), Zone.objects.count(),
            GeoAlias.objects.count(),
            list(LGA.objects.values_list('id', 'name', 'zone_id')),
            list(GeoAlias.objects.values_list(
                'id', 'normalized_alias', 'lga_id', 'status')),
        )
        self._run_release()
        after = (
            LGA.objects.count(), Zone.objects.count(),
            GeoAlias.objects.count(),
            list(LGA.objects.values_list('id', 'name', 'zone_id')),
            list(GeoAlias.objects.values_list(
                'id', 'normalized_alias', 'lga_id', 'status')),
        )
        self.assertEqual(before, after)
        self.assertEqual(after[0], 21)


class ReleaseMigrateFinalWiringTests(TestCase):
    """The final package's two added release steps, exercised for real:
    the starter source seed and the article-location backfill.

    Same doubling approach as ReleaseMigrateSeedingTests: only the
    connection is doubled; the three intelligence steps run for real
    against the test database, everything else is stubbed.
    """

    REAL_STEPS = {
        'seed_intelligence_directory', 'seed_intelligence_sources',
        'backfill_article_locations',
    }

    def _run_release(self):
        def dispatch(name, **kwargs):
            if name in self.REAL_STEPS:
                call_command(name, **kwargs)

        connection = _FakeConnection()
        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', dispatch):
            call_command('release_migrate')

    def test_release_seeds_the_nine_starter_sources(self):
        from editorial.models import Source

        self.assertEqual(Source.objects.count(), 0)
        self._run_release()
        self.assertEqual(Source.objects.count(), 9)
        enabled = list(Source.objects.filter(enabled=True))
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0].name, 'Kebbi State Government Pressroom')
        self.assertEqual(enabled[0].connector_kind, 'OFFICIAL_PAGE')
        self.assertEqual(Source.objects.filter(enabled=False).count(), 8)

    def test_source_seed_is_idempotent_and_preserves_edits(self):
        from editorial.models import Source

        self._run_release()
        pressroom = Source.objects.get(
            url='https://kebbistate.gov.ng/governor/pressroom')
        pressroom.name = 'Owner Edited Name'
        pressroom.save()
        self._run_release()
        self.assertEqual(Source.objects.count(), 9)
        pressroom.refresh_from_db()
        self.assertEqual(pressroom.name, 'Owner Edited Name')
        self.assertTrue(pressroom.enabled)

    def test_release_backfills_article_locations_idempotently(self):
        from campaigns.models import Campaign
        from intelligence.models import ArticleLocation
        from leadership.models import LGA, Zone
        from staff.models import User

        zone = Zone.objects.create(name='Rehearsal Zone')
        lga = LGA.objects.create(name='Rehearsal LGA', zone=zone)
        author = User.objects.create_user(
            username='wiring-author', password='not-a-real-password')
        article = Campaign.objects.create(
            title='Wiring Article', slug='wiring-article', author=author,
            status='PUBLISHED', lga=lga)
        Campaign.objects.create(
            title='Untagged Article', slug='untagged-article',
            author=author, status='PUBLISHED')
        # The live post_save path mirrors Campaign.lga immediately;
        # remove that row to simulate an article that predates the
        # live paths — precisely what the release backfill exists for.
        ArticleLocation.objects.all().delete()

        self.assertEqual(ArticleLocation.objects.count(), 0)
        self._run_release()
        self.assertEqual(ArticleLocation.objects.count(), 1)
        link = ArticleLocation.objects.get()
        self.assertEqual(link.article_id, article.pk)
        self.assertEqual(link.lga_id, lga.pk)
        self.assertEqual(link.kind, 'ARTICLE')
        self._run_release()
        self.assertEqual(ArticleLocation.objects.count(), 1)


class ReleaseMigrateIctAdminTests(TestCase):
    """The ICT Admin seed step, exercised for real: release_migrate
    must leave the Director of Media & Communications recorded as the
    ICT Admin holder, and must leave the assignment unassigned (never
    fail) when no such account exists yet.

    Same doubling approach as the other wiring tests: only the
    connection is doubled; seed_ict_admin runs for real against the
    test database, everything else is stubbed.
    """

    REAL_STEPS = {'seed_ict_admin'}

    def _run_release(self):
        def dispatch(name, **kwargs):
            if name in self.REAL_STEPS:
                call_command(name, **kwargs)

        connection = _FakeConnection()
        with mock.patch.object(rm, 'connection', connection), \
                mock.patch.object(rm, 'call_command', dispatch):
            call_command('release_migrate')

    def test_release_assigns_the_director_of_media(self):
        from core.models import IctAdminAssignment
        from leadership.models import RoleDefinition
        from staff.models import User

        rd = RoleDefinition.objects.create(
            title='Director of Media & Communications', tier='STATE',
            seat_number=17)
        director = User.objects.create_user(
            username='wiring-director', password='not-a-real-password',
            phone='wiring-director', role='STATE', status='VERIFIED',
            role_definition=rd)
        self._run_release()
        assignment = IctAdminAssignment.objects.get(pk=1)
        self.assertEqual(assignment.user_id, director.pk)
        # A second start changes nothing.
        self._run_release()
        assignment.refresh_from_db()
        self.assertEqual(assignment.user_id, director.pk)

    def test_release_without_a_director_leaves_it_unassigned(self):
        from core.models import IctAdminAssignment

        self._run_release()
        assignment = IctAdminAssignment.objects.get(pk=1)
        self.assertIsNone(assignment.user_id)
