from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

class Command(BaseCommand):
    help='Serialize release preflight/migrations across PostgreSQL instances.'
    def handle(self,*args,**options):
        if connection.vendor!='postgresql':raise CommandError('Release migrations require PostgreSQL.')
        # Stable application-specific, session-level lock released on disconnect.
        lock_id=1263554097
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(%s)',[lock_id])
            try:
                call_command('check_release',database=True)
                call_command('migrate',interactive=False)
                call_command('check_release',database=True)
                # KPN Media (v2.9.1): Story IDs are part of the release,
                # not a manual step. backfill_story_ids is idempotent —
                # it assigns IDs only to PUBLISHED articles missing one
                # (e.g. published by the previous release during the
                # deploy window) and is a fast no-op when coverage is
                # already complete. It runs inside this same advisory
                # lock so concurrent instance startups cannot interleave
                # migrate/backfill. A backfill ERROR fails the release
                # on purpose (the exception propagates and the start
                # script's set -e stops Gunicorn): serving traffic with
                # a broken backfill is worse than not deploying.
                call_command('backfill_story_ids')
                # Advisory only: the coverage report always exits 0 and
                # never fails the release. Right after the backfill, the
                # only possible gap is an article published by a
                # still-draining old instance in the deploy window; that
                # self-heals on the next release's backfill and is also
                # caught by the story_intelligence audit backstop, so it
                # must not block an otherwise healthy deploy. Its output
                # stays visible in the deploy log.
                call_command('check_story_id_coverage')
            finally:cursor.execute('SELECT pg_advisory_unlock(%s)',[lock_id])
