"""Explicit cleanup for inbox copies of previously deleted announcements."""
from django.core.management.base import BaseCommand
from core.models import Notification
from staff.models import Announcement


class Command(BaseCommand):
    help = 'Count orphaned announcement inbox copies; delete only with --apply.'
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
    def handle(self, *args, **options):
        rows = Notification.objects.filter(
            event='ANNOUNCEMENT', target_type='announcement', target_id__isnull=False,
        ).exclude(target_id__in=Announcement.objects.values('pk'))
        self.stdout.write(f'Orphaned linked announcement notifications: {rows.count()}')
        if options['apply']:
            rows.delete()
            self.stdout.write(self.style.SUCCESS('Deleted only orphaned linked announcement notifications.'))
        else:
            self.stdout.write('Dry run only. No records changed. Use --apply after review and backup.')
