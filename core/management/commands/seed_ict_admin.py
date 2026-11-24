"""Seed the initial ICT Admin assignment (owner instruction 2026-11-24).

Idempotent and edit-preserving: the Director of Media &
Communications is recorded as the first ICT Admin holder; once any
holder exists — seeded or reassigned by a super admin — the seed
never overwrites it. Wired fail-safe into release_migrate: production
deploys have no shell access, so the seed runs automatically at every
start. The command can still be run manually with the same result.
"""
from django.core.management.base import BaseCommand

from core.ict_admin import current_assignment, seed_ict_admin_assignment


class Command(BaseCommand):
    help = ('Seed the initial ICT Admin holder (the Director of Media '
            '& Communications; idempotent, never overwrites a holder).')

    def handle(self, *args, **options):
        assignment = seed_ict_admin_assignment()
        assignment = current_assignment()
        if assignment.user_id:
            self.stdout.write(
                f'ICT Admin holder: {assignment.user} '
                f'(pk={assignment.user_id}).')
        else:
            self.stdout.write(
                'ICT Admin unassigned: no Director of Media & '
                'Communications account found. The console stays '
                'superuser-only until a super admin assigns a holder.')
