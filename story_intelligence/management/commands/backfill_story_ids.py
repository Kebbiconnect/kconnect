"""Assign permanent Story IDs to already-published articles.

Idempotent by construction (assessment §7.7): only PUBLISHED articles
with story_id IS NULL are selected, oldest-published first, and each
article is allocated in its OWN transaction using
update_fields=['story_id'] — content, slug, timestamps, authorship and
status are never touched. Re-running skips every article that already
has an ID and can never renumber. Deliberately a management command,
not a data migration: deploys must never block on (or repeat) it.

Usage:
    python manage.py backfill_story_ids --dry-run
    python manage.py backfill_story_ids
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from campaigns.models import Campaign
from story_intelligence.services import allocate_story_id


class Command(BaseCommand):
    help = 'Assign permanent Story IDs to published articles that lack one (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report how many articles would receive a Story ID; change nothing.')

    def handle(self, *args, **options):
        stubs = list(
            Campaign.objects.filter(status='PUBLISHED', story_id__isnull=True)
            .order_by('published_at', 'pk')
            .values('pk', 'title', 'published_at'))
        if options['dry_run']:
            self.stdout.write(
                f'DRY RUN: {len(stubs)} published article(s) would receive a Story ID.')
            for stub in stubs[:20]:
                self.stdout.write(f"  - [{stub['published_at']}] {stub['title']}")
            if len(stubs) > 20:
                self.stdout.write(f'  … and {len(stubs) - 20} more.')
            return
        done = 0
        for stub in stubs:
            with transaction.atomic():
                article = Campaign.objects.select_for_update().get(pk=stub['pk'])
                if article.story_id:
                    continue  # allocated meanwhile; never renumber
                allocate_story_id(article)
                article.save(update_fields=['story_id'])
                done += 1
        self.stdout.write(self.style.SUCCESS(
            f'Backfill complete: {done} article(s) received a Story ID; '
            f'{len(stubs) - done} skipped (already allocated).'))
