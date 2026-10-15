from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, F, Q

class Command(BaseCommand):
    help='Validate production configuration and optional seat-integrity preflight; never emits secrets.'
    def add_arguments(self,parser): parser.add_argument('--database',action='store_true')
    def handle(self,*args,**options):
        if not settings.IS_PRODUCTION: raise CommandError('Release validation requires KPN_ENV=production.')
        if settings.EMAIL_BACKEND=='staff.lockally_backend.LockallyEmailBackend':
            if not all([settings.LOCKALLY_API_KEY,settings.LOCKALLY_API_URL,settings.LOCKALLY_FROM_EMAIL]):
                raise CommandError('Configure the production Lockally email settings.')
            if not settings.LOCKALLY_API_URL.startswith('https://'): raise CommandError('Lockally API must use HTTPS.')
        elif settings.EMAIL_BACKEND=='django.core.mail.backends.smtp.EmailBackend':
            if not all([settings.EMAIL_HOST,settings.EMAIL_HOST_USER,settings.EMAIL_HOST_PASSWORD]):
                raise CommandError('Configure production SMTP settings.')
        else: raise CommandError('Production requires a real Lockally or SMTP email backend.')
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError('Telegram token and webhook secret are required for the leadership access workflow.')
        if options['database']:
            from staff.models import User
            with connection.cursor() as cursor:cursor.execute('SELECT 1')
            if User._meta.db_table in connection.introspection.table_names():
                mismatches=User.objects.filter(role_definition__isnull=False).exclude(role=F('role_definition__tier')).count()
                if mismatches: raise CommandError(f'{mismatches} member assignments have inconsistent tiers; resolve before migration.')
                invalid=User.objects.filter(status='VERIFIED',role_definition__isnull=False).filter(
                    Q(role='ZONAL',zone__isnull=True)|Q(role='LGA',lga__isnull=True)|Q(role='WARD',ward__isnull=True)).count()
                if invalid: raise CommandError(f'{invalid} verified assignments are missing required scope; resolve before migration.')
                for tier,scope in [('STATE',[]),('ZONAL',['zone_id']),('LGA',['lga_id']),('WARD',['ward_id'])]:
                    duplicates=User.objects.filter(status='VERIFIED',role=tier,role_definition__isnull=False).values('role_definition_id',*scope).annotate(total=Count('id')).filter(total__gt=1).count()
                    if duplicates: raise CommandError(f'{duplicates} duplicate {tier} seat groups exist; no data has been changed.')
        self.stdout.write(self.style.SUCCESS('Release configuration'+(' and database preflight' if options['database'] else '')+' passed. Provider delivery, backup recovery and device acceptance must still be verified.'))
