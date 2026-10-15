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
            finally:cursor.execute('SELECT pg_advisory_unlock(%s)',[lock_id])
