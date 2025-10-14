from django.core.management.base import BaseCommand
from staff.models import User
from leadership.models import Zone, LGA, Ward, RoleDefinition

class Command(BaseCommand):
    help = 'Creates test users for all 41 role definitions'

    def handle(self, *args, **options):
        self.stdout.write('Creating test users for all 41 roles...')
        
        password = 'test123'
        
        kebbi_north = Zone.objects.get(name='Kebbi North')
        kebbi_central = Zone.objects.get(name='Kebbi Central')
        kebbi_south = Zone.objects.get(name='Kebbi South')
        
        argungu = LGA.objects.get(name='Argungu', zone=kebbi_north)
        birnin_kebbi = LGA.objects.get(name='Birnin Kebbi', zone=kebbi_central)
        yauri = LGA.objects.get(name='Yauri', zone=kebbi_south)
        
        argungu_ward = Ward.objects.filter(lga=argungu).first()
        birnin_kebbi_ward = Ward.objects.filter(lga=birnin_kebbi).first()
        yauri_ward = Ward.objects.filter(lga=yauri).first()
        
        created_count = 0
        
        for role in RoleDefinition.objects.all().order_by('tier', 'seat_number'):
            base_username = role.title.lower().replace(' ', '_').replace('&', 'and')
            username = f"{role.tier.lower()}_{base_username}"
            
            if User.objects.filter(username=username).exists():
                self.stdout.write(f'  User already exists: {username}')
                continue
            
            zone = None
            lga = None
            ward = None
            
            if role.tier == 'STATE':
                zone = kebbi_north
                lga = argungu
            elif role.tier == 'ZONAL':
                zone = kebbi_north
                lga = argungu
            elif role.tier == 'LGA':
                lga = birnin_kebbi
            elif role.tier == 'WARD':
                ward = argungu_ward
                lga = argungu_ward.lga if argungu_ward else None
                zone = lga.zone if lga else None
            
            user = User.objects.create_user(
                username=username,
                email=f'{username}@kpn.test',
                password=password,
                first_name=role.title.split()[0],
                last_name=role.tier.title(),
                phone=f'080{str(role.id).zfill(8)}',
                role=role.tier,
                role_definition=role,
                status='APPROVED',
                zone=zone,
                lga=lga,
                ward=ward,
                facebook_verified=True
            )
            
            created_count += 1
            self.stdout.write(f'  Created: {username} ({role.tier} - {role.title})')
        
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully created {created_count} test users!'))
        self.stdout.write(self.style.SUCCESS(f'Password for all test users: {password}'))
        
        self.stdout.write('\n=== LOGIN CREDENTIALS ===')
        self.stdout.write('All users have password: test123\n')
        
        for role in RoleDefinition.objects.all().order_by('tier', 'seat_number'):
            base_username = role.title.lower().replace(' ', '_').replace('&', 'and')
            username = f"{role.tier.lower()}_{base_username}"
            self.stdout.write(f'{role.tier:6s} | {role.title:50s} | Username: {username}')
