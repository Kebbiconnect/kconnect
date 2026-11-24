"""Run the Phase 3 processing engines over waiting raw publications.

The collection cycle already processes intake at the end of each run;
this command exists for backfills and operator-driven reprocessing
(e.g. after new aliases are approved). Unprocessed items only —
manual classifications are preserved by the engine itself.
"""
from django.core.management.base import BaseCommand

from intelligence.relevance import process_pending


class Command(BaseCommand):
    help = 'Classify, categorise, dedupe and cluster unprocessed raw publications.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=500,
                            help='Maximum items to process in this run.')

    def handle(self, *args, **options):
        stats = process_pending(limit=max(1, options['limit']))
        self.stdout.write(
            'Processed {processed}, failed {failed}, '
            'clusters touched {clusters}, '
            'promise candidates {promise_candidates}.'.format(**stats))
        # Backfill: items processed before the Phase 5 detector
        # existed get their commitment scan too (idempotent).
        from intelligence.promise_detection import detect_pending
        backfill = detect_pending(limit=max(1, options['limit']))
        self.stdout.write(
            'Promise detection backfill: {items} items scanned, '
            '{candidates} candidates on file.'.format(**backfill))
