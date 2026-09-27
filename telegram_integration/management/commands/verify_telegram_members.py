import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from telegram_integration.models import TelegramMembership
from telegram_integration.services import verify_telegram_membership

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Periodically verifies KPN Telegram channel membership for all connected users.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sleep',
            type=int,
            default=2,
            help='Sleep time between API calls to respect Telegram rate limits'
        )
        parser.add_argument(
            '--force-all',
            action='store_true',
            help='Verify all members regardless of when they were last checked'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit the number of members to check in this run (0 = no limit)'
        )

    def handle(self, *args, **options):
        sleep_time = options['sleep']
        force_all = options['force_all']
        limit = options['limit']

        memberships = TelegramMembership.objects.all()

        if not force_all:
            # Only check members who haven't been checked in the last 12 hours
            from datetime import timedelta
            threshold = timezone.now() - timedelta(hours=12)
            memberships = memberships.filter(
                last_checked_at__lt=threshold
            ) | memberships.filter(last_checked_at__isnull=True)

        # Order by oldest check first (nulls first)
        memberships = memberships.order_by('last_checked_at')

        if limit > 0:
            memberships = memberships[:limit]

        total = memberships.count()
        self.stdout.write(self.style.SUCCESS(f"Starting verification for {total} members..."))

        success_count = 0
        fail_count = 0
        left_count = 0

        for i, tm in enumerate(memberships, 1):
            self.stdout.write(f"[{i}/{total}] Checking {tm.user.username} (TG: {tm.telegram_user_id})...")
            
            try:
                was_verified = tm.is_verified
                result = verify_telegram_membership(tm.telegram_user_id)
                
                if result['success']:
                    success_count += 1
                    is_now_verified = result['is_member']
                    
                    if was_verified and not is_now_verified:
                        left_count += 1
                        self.stdout.write(self.style.WARNING(f"  -> Member LEFT the channel (Status: {result['status']})"))
                    elif not was_verified and is_now_verified:
                        self.stdout.write(self.style.SUCCESS(f"  -> Member JOINED the channel (Status: {result['status']})"))
                    else:
                        self.stdout.write(f"  -> Unchanged (Verified: {is_now_verified})")
                else:
                    fail_count += 1
                    self.stdout.write(self.style.ERROR(f"  -> API Error: {result['error']}"))
                    
            except Exception as e:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"  -> Exception: {e}"))
                logger.error(f"Error checking {tm.telegram_user_id}: {e}")

            # Sleep to avoid hitting Telegram API rate limits (mostly 30 req/sec, but let's be safe)
            if i < total:
                time.sleep(sleep_time)

        self.stdout.write(self.style.SUCCESS(
            f"\nVerification complete.\n"
            f"Total Checked: {total}\n"
            f"Successful Checks: {success_count}\n"
            f"Failed Checks: {fail_count}\n"
            f"Members newly detected as left: {left_count}"
        ))
