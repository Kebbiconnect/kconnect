from django.core.management.base import BaseCommand, CommandError

from intelligence.cycle import run_cycle


class Command(BaseCommand):
    help = ('Run one bounded intelligence collection cycle: lease, run '
            'record, due-source visits through the registered connectors '
            '(RSS/page/official-page), raw-item intake and source health.')

    def add_arguments(self, parser):
        parser.add_argument('--max-seconds', type=int, default=600)
        parser.add_argument('--trigger', choices=['SCHEDULED', 'MANUAL'], default='SCHEDULED')

    def handle(self, *args, **options):
        if not 30 <= options['max_seconds'] <= 900:
            raise CommandError('Use 30–900 seconds.')
        run = run_cycle(trigger=options['trigger'], max_seconds=options['max_seconds'])
        self.stdout.write(
            f'Collection run {run.pk}: {run.status} — due {run.sources_due}, '
            f'ok {run.sources_ok}, failed {run.sources_failed}, new items {run.items_new}.'
            + (f' {run.error}' if run.error else ''))
