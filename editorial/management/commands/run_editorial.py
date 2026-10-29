from django.core.management.base import BaseCommand, CommandError
from editorial.worker import run, Paused

class Command(BaseCommand):
    help='Run bounded review-only editorial jobs. Does not approve or publish content.'
    def add_arguments(self,p):
        p.add_argument('--max-jobs',type=int,default=15)
        p.add_argument('--max-seconds',type=int,default=600)
    def handle(self,*args,**options):
        if not 1<=options['max_jobs']<=50 or not 30<=options['max_seconds']<=900:raise CommandError('Use 1–50 jobs and 30–900 seconds.')
        try:count=run(options['max_jobs'],options['max_seconds'])
        except Paused as exc:self.stdout.write(str(exc));return
        self.stdout.write(f'Processed {count} jobs. Inspect the private queue and job errors; no content was auto-published.')
