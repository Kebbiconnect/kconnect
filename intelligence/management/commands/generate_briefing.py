"""Generate an intelligence briefing from real records.

Scheduler-friendly: run it from the same external trigger that
drives the collection cycle, e.g.

    python manage.py generate_briefing --period daily
    python manage.py generate_briefing --period weekly --email

It first evaluates the cycle alert rules (source health, missed
cycles) so a briefing run also keeps the alert log current, then
generates the period's briefing. Generation is idempotent: an
existing briefing for the period is kept unless --force is passed.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from intelligence import briefings
from intelligence.alerts import evaluate_cycle_alerts


class Command(BaseCommand):
    help = 'Generate a daily or weekly intelligence briefing from real records.'

    def add_arguments(self, parser):
        parser.add_argument('--period', choices=['daily', 'weekly'],
                            default='daily')
        parser.add_argument('--date', default='',
                            help='Period anchor date, YYYY-MM-DD '
                                 '(default: today). For weekly, the '
                                 'week containing the date is used.')
        parser.add_argument('--email', action='store_true',
                            help='Email the briefing to the '
                                 'intelligence-reports holders.')
        parser.add_argument('--telegram', action='store_true',
                            help='Send the short summary to the staff '
                                 'Telegram chats configured on the '
                                 'briefing alert rule.')
        parser.add_argument('--force', action='store_true',
                            help='Recompose an existing briefing.')

    def handle(self, *args, **options):
        day = None
        if options['date']:
            try:
                day = date.fromisoformat(options['date'])
            except ValueError:
                raise CommandError('--date must be YYYY-MM-DD')
        evaluate_cycle_alerts()
        briefing = briefings.generate(
            kind=options['period'].upper(), day=day,
            force=options['force'])
        if options['email']:
            briefings.email_briefing(briefing)
        if options['telegram']:
            deliveries = briefings.send_telegram(briefing)
            for delivery in deliveries:
                self.stdout.write(
                    f'Telegram {delivery.recipient or "—"}: '
                    f'{delivery.status}'
                    f'{(" — " + delivery.error) if delivery.error else ""}')
        self.stdout.write(
            f'Briefing #{briefing.pk}: {briefing.title} '
            f'({briefing.period_start} to {briefing.period_end})')
        if briefing.email_status:
            self.stdout.write(f'Email: {briefing.email_status}')
