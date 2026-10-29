import json
import sys
from django.core.management.base import BaseCommand, CommandError
from editorial.brain import submit_draft, BrainError

class Command(BaseCommand):
    help = 'Import drafts written by Muse (JSON list of {item_id, version, draft}). Drafts land in human REVIEW; nothing is published.'
    def add_arguments(self, p):
        p.add_argument('path', help="JSON file path, or '-' for stdin.")
    def handle(self, *args, **options):
        raw = sys.stdin.read() if options['path'] == '-' else open(options['path'], encoding='utf-8').read()
        try:
            entries = json.loads(raw)
        except ValueError:
            raise CommandError('Input is not valid JSON.')
        if not isinstance(entries, list):
            raise CommandError('Input must be a JSON list of {item_id, version, draft}.')
        ok, failed = 0, 0
        for entry in entries:
            try:
                item = submit_draft(int(entry['item_id']), entry['draft'], int(entry['version']))
                ok += 1
                self.stdout.write(f"item {item.pk}: draft accepted, now in REVIEW (version {item.version}).")
            except (KeyError, TypeError, ValueError):
                failed += 1
                self.stdout.write(f"entry {entry!r}: malformed, skipped.")
            except BrainError as exc:
                failed += 1
                self.stdout.write(f"item {entry.get('item_id')}: rejected ({exc.code}). Nothing was changed.")
        self.stdout.write(f'Done. {ok} accepted, {failed} rejected.')
        if failed:
            raise CommandError(f'{failed} draft(s) were rejected; see lines above.')
