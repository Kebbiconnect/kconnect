import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

logger=logging.getLogger(__name__)

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
                # KPN Intelligence (v3.0.0): the geographic directory
                # (21 LGAs, zones, starter aliases) is seeded here for
                # the same reason the Story ID backfill lives here —
                # production deploys have no shell access, so no release
                # step may be manual. seed_directory() (behind the
                # seed_intelligence_directory command) is idempotent:
                # get_or_create throughout, a small constant number of
                # indexed lookups when everything already exists, so it
                # is a fast no-op on every start after the first. Unlike
                # the backfill, a seed ERROR must not fail the release:
                # the directory is additive reference data, the public
                # site does not depend on it, and blocking a healthy
                # deploy over it would be worse than a dashboard that is
                # missing reference rows until the next start retries.
                # So the failure is logged loudly and the release
                # continues — the same fail-safe treatment as the
                # advisory coverage report below.
                try:
                    call_command('seed_intelligence_directory')
                except Exception:
                    logger.exception(
                        'seed_intelligence_directory failed during '
                        'release_migrate; continuing the release.')
                    self.stderr.write(
                        'WARNING: intelligence directory seeding failed; '
                        'see the log. The release continues and the seed '
                        'will be retried on the next start.')
                # KPN Intelligence (final package): the starter source
                # directory is seeded here too, for the same reason —
                # production deploys have no shell access, so no release
                # step may be manual. seed_sources() (behind the
                # seed_intelligence_sources command) is idempotent:
                # get_or_create by URL, and it never overwrites an edit
                # made in the dashboard, so re-running on every start is
                # a fast no-op once the rows exist. The starter set is
                # unchanged from Phase 2: the Kebbi State Government
                # Pressroom starts ENABLED (the one audit-verified
                # source); the other eight start DISABLED pending feed
                # validation and owner review (D7). Same fail-safe
                # treatment as the directory seed: an error is logged
                # loudly and the release continues.
                try:
                    call_command('seed_intelligence_sources')
                except Exception:
                    logger.exception(
                        'seed_intelligence_sources failed during '
                        'release_migrate; continuing the release.')
                    self.stderr.write(
                        'WARNING: intelligence source seeding failed; '
                        'see the log. The release continues and the seed '
                        'will be retried on the next start.')
                # KPN Intelligence Phase 7 (final package): the public
                # LGA news pages read explicit ArticleLocation rows.
                # New links are written live (desk conversion, article
                # saves, staff tagging), but articles that already exist
                # need the backfill pass, and a deploy is the only
                # guaranteed moment it can run. backfill_article_locations
                # is idempotent (get_or_create on the unique pair), so
                # on every start after the first it only links articles
                # created since. Same fail-safe treatment: the LGA pages
                # are additive public pages, so a backfill error must not
                # block a healthy deploy; it is logged and retried on
                # the next start.
                try:
                    call_command('backfill_article_locations')
                except Exception:
                    logger.exception(
                        'backfill_article_locations failed during '
                        'release_migrate; continuing the release.')
                    self.stderr.write(
                        'WARNING: article-location backfill failed; '
                        'see the log. The release continues and the '
                        'backfill will be retried on the next start.')
                # ICT Admin console (owner instruction, 2026-11-24):
                # the ICT Admin assignment starts with the Director of
                # Media & Communications. seed_ict_admin records that
                # holder the first time it finds the account; it is
                # idempotent and edit-preserving — once any holder is
                # recorded (by this seed or by a super admin's
                # reassignment on the console) it never overwrites it,
                # and when no Director of Media exists yet it leaves
                # the assignment unassigned (console superuser-only).
                # Same fail-safe treatment as the other seeds: an
                # error is logged loudly and the release continues.
                try:
                    call_command('seed_ict_admin')
                except Exception:
                    logger.exception(
                        'seed_ict_admin failed during release_migrate; '
                        'continuing the release.')
                    self.stderr.write(
                        'WARNING: ICT Admin seeding failed; see the '
                        'log. The release continues and the seed will '
                        'be retried on the next start.')
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
