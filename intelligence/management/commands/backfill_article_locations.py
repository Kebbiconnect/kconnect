"""Backfill explicit article↔LGA links for existing articles (Phase 7).

The public LGA news pages read only ``ArticleLocation`` rows. New
rows are written live — at desk conversion and whenever an article's
own stored ``lga`` field is saved — but articles that already exist
need one pass:

- every article whose own ``Campaign.lga`` field is set gains an
  ARTICLE-kind link;
- every article a desk unit was already converted into gains
  CONVERSION-kind links for the LGAs its unit's records evidence.

Idempotent (``get_or_create`` on the unique pair): safe to re-run.
Wired into release_migrate (final package) with fail-safe treatment —
it runs automatically at every start and only ever links articles
created since the previous run. The command can still be run manually
at any time with the same result.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create ArticleLocation rows for existing articles (idempotent).'

    def handle(self, *args, **options):
        from campaigns.models import Campaign

        from intelligence import article_locations
        from intelligence.models import EventCluster, RawPublication

        created = 0
        for article in Campaign.objects.filter(lga__isnull=False):
            _row, was_created = article_locations.link(
                article, article.lga, 'ARTICLE')
            created += int(was_created)
        for model in (EventCluster, RawPublication):
            for unit in model.objects.filter(article__isnull=False) \
                    .select_related('article'):
                for lga in article_locations.unit_lgas(unit):
                    _row, was_created = article_locations.link(
                        unit.article, lga, 'CONVERSION')
                    created += int(was_created)
        total = Campaign.objects.filter(lga_links__isnull=False) \
            .distinct().count()
        self.stdout.write(
            f'ArticleLocation backfill: {created} new link(s); '
            f'{total} article(s) now carry at least one LGA link.')
