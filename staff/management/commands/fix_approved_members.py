"""
One-time management command to migrate any users stuck at 'APPROVED' status to 'VERIFIED'.
Run: python manage.py fix_approved_members
"""
from django.core.management.base import BaseCommand
from staff.models import User


class Command(BaseCommand):
    help = 'Migrates users with APPROVED status to VERIFIED so they can log in'

    def handle(self, *args, **options):
        stuck = User.objects.filter(status='APPROVED')
        count = stuck.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No stuck APPROVED members found. All good!'))
            return

        self.stdout.write(f'Found {count} member(s) stuck at APPROVED status:')
        for u in stuck:
            self.stdout.write(f'  - {u.get_full_name()} ({u.username})')

        stuck.update(status='VERIFIED')
        self.stdout.write(self.style.SUCCESS(
            f'✅ Successfully updated {count} member(s) from APPROVED → VERIFIED. They can now log in.'
        ))
