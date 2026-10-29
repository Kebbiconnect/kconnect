import uuid
from django.core.management.base import BaseCommand
from editorial.models import Item, Job

class Command(BaseCommand):
    help = 'Create a PRIVATE synthetic WAITING item so the owner can watch the Muse brain loop (outbox -> draft -> inbox -> dismiss). Makes no external request.'
    def handle(self, *args, **options):
        key = 'test:' + uuid.uuid4().hex
        item = Item.objects.create(key=key, kind='NEWS', title='Synthetic KPN test — not real news', original={'title': 'Synthetic KPN test — not real news', 'text': 'This is a fictional test report. A fictional youth reading group in Kebbi State met on a Saturday to discuss a reading programme. No attendance figure, named participants, funding, or verified outcome has been supplied. Do not invent them.', 'source_url': '', 'synthetic': True})
        Job.objects.create(key='generate:' + key, kind='GENERATE', item=item)
        self.stdout.write(f'Synthetic WAITING item #{item.pk} created. Run brain_outbox, have Muse draft it, import with brain_inbox, then dismiss it in /editorial/. Synthetic drafts cannot be handed off or published.')
