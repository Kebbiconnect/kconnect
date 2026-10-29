import json
from django.core.management.base import BaseCommand
from editorial.brain import waiting_items

class Command(BaseCommand):
    help = 'Export WAITING editorial items as JSON for Muse, the external drafting brain. Read-only.'
    def add_arguments(self, p):
        p.add_argument('--limit', type=int, default=20)
        p.add_argument('--output', default='', help='Write to this file instead of stdout.')
    def handle(self, *args, **options):
        payload = json.dumps(waiting_items(options['limit']), ensure_ascii=False, indent=1)
        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as fh:
                fh.write(payload + '\n')
            self.stdout.write(f"Wrote {options['output']}")
        else:
            self.stdout.write(payload)
