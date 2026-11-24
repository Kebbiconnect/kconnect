"""Seed the intelligence geographic directory (21 LGAs + starter aliases).

Idempotent and safe to re-run. ``release_migrate`` runs this automatically
on every start (production deploys have no shell access); it can also be
run by hand, e.g. after a restore. Existing variant spellings of LGA names
are kept; the canonical spellings are added as approved aliases.
"""
from django.core.management.base import BaseCommand

from intelligence.seeding import seed_directory
from leadership.models import LGA


class Command(BaseCommand):
    help = 'Seed the 21 Kebbi LGAs and starter geographic aliases (idempotent).'

    def handle(self, *args, **options):
        seed_directory()
        self.stdout.write(
            f'Geographic directory seeded: {LGA.objects.count()} LGAs present.')
