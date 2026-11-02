"""Report Story ID coverage: published articles with and without an ID.

Run after a deploy + backfill to confirm the Phase 1 invariant holds
(no PUBLISHED article without a permanent Story ID).
"""
from django.core.management.base import BaseCommand

from campaigns.models import Campaign


class Command(BaseCommand):
    help = 'Report how many published articles have a permanent Story ID.'

    def handle(self, *args, **options):
        published = Campaign.objects.filter(status='PUBLISHED')
        total = published.count()
        with_id = published.exclude(story_id__isnull=True).exclude(story_id='').count()
        missing = published.filter(story_id__isnull=True)
        self.stdout.write(f'Published articles: {total}')
        self.stdout.write(f'With a Story ID:    {with_id}')
        self.stdout.write(f'Without a Story ID: {missing.count()}')
        for article in missing.order_by('published_at', 'pk')[:20]:
            self.stdout.write(f'  MISSING: {article.slug} (published {article.published_at})')
        if missing.exists():
            self.stdout.write(self.style.WARNING(
                'Run: python manage.py backfill_story_ids'))
        else:
            self.stdout.write(self.style.SUCCESS('Coverage complete.'))
