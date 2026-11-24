"""Seed the starter intelligence source directory (Doc 05 set).

Idempotent and safe to re-run: rows are matched by URL and existing
rows — including any edits made in the dashboard — are left untouched.
Only the audit-verified Kebbi State Government Pressroom starts
enabled; the publisher feeds start disabled pending feed validation
and owner decision D7. Wired into release_migrate (final package,
owner decision): production deploys have no shell access, so the seed
runs automatically at every start — idempotent and edit-preserving,
so an operator's dashboard changes are never overwritten. The command
can still be run manually at any time with the same result.
"""
from django.core.management.base import BaseCommand

from editorial.models import Source
from intelligence.sources_seed import seed_sources


class Command(BaseCommand):
    help = 'Seed the starter intelligence sources (idempotent; Doc 05 set).'

    def handle(self, *args, **options):
        created = seed_sources()
        self.stdout.write(
            f'Starter sources seeded: {len(created)} created, '
            f'{Source.objects.count()} sources in the directory.')
        for source in created:
            state = 'enabled' if source.enabled else 'disabled'
            self.stdout.write(f'  + {source.name} ({source.connector_kind}, {state})')
