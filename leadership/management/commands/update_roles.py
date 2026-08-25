from django.core.management.base import BaseCommand
from leadership.models import RoleDefinition

class Command(BaseCommand):
    help = 'Updates existing roles to match the KPN 2.0 Constitution without deleting users.'

    def handle(self, *args, **kwargs):
        # 1. State Executive Team (20 roles)
        state_roles = [
            'President', 'Vice President', 'General Secretary', 'Assistant General Secretary',
            'Director of Monitoring & Compliance', 'Director of Legal Affairs & Ethics',
            'Director of Finance', 'Finance Operations Officer', 'Director of Community Engagement',
            'Assistant Director of Community Engagement', 'Director of Programmes & Events',
            'Assistant Director of Programmes & Events', 'Director of Audit & Accountability',
            'Director of Member Support & Welfare', 'Director of Youth Development',
            'Director of Women\'s Development', 'Assistant Director of Women\'s Development',
            'Director of Media & Communications', 'Assistant Director of Media & Communications',
            'Director of Public Relations & Partnerships'
        ]
        
        # 2. Senatorial Leadership Teams (3 roles)
        zonal_roles = [
            'Senatorial Director', 'Senatorial Administrative Officer', 'Senatorial Communications Officer'
        ]

        # 3. Local Government Network Team (10 roles)
        lga_roles = [
            'LGA Network Lead', 'LGA Administrative Officer', 'LGA Programmes Officer',
            'LGA Finance Officer', 'LGA Communications Officer', 'LGA Monitoring Officer',
            'LGA Women\'s Development Officer', 'LGA Member Support Officer',
            'LGA Community Engagement Officer', 'LGA Adviser'
        ]

        # 4. Ward Community Team (8 roles)
        ward_roles = [
            'Ward Community Lead', 'Ward Administrative Officer', 'Ward Programmes Officer',
            'Ward Finance Officer', 'Ward Communications Officer', 'Ward Monitoring Officer',
            'Ward Community Support Officer', 'Ward Adviser'
        ]

        # Legacy mappings (Best effort based on previous known names in code)
        legacy_mapping = {
            # State
            'State Coordinator': 'President',
            'State Secretary': 'General Secretary',
            'State Publicity Secretary': 'Director of Media & Communications',
            'Treasurer': 'Director of Finance',
            'Financial Secretary': 'Finance Operations Officer',
            'Organizing Secretary': 'Director of Programmes & Events',
            'Welfare Officer': 'Director of Member Support & Welfare',
            'Women Leader': 'Director of Women\'s Development',
            
            # Senatorial
            'Zonal Coordinator': 'Senatorial Director',
            'Zonal Secretary': 'Senatorial Administrative Officer',
            'Zonal Publicity Officer': 'Senatorial Communications Officer',
            
            # LGA
            'LGA Coordinator': 'LGA Network Lead',
            'LGA Secretary': 'LGA Administrative Officer',
            'LGA Publicity Officer': 'LGA Communications Officer',
            
            # Ward
            'Ward Coordinator': 'Ward Community Lead',
            'Ward Secretary': 'Ward Administrative Officer',
            'Ward Publicity Officer': 'Ward Communications Officer'
        }

        # Let's first apply known mappings
        for old_title, new_title in legacy_mapping.items():
            roles = RoleDefinition.objects.filter(title=old_title)
            for role in roles:
                role.title = new_title
                role.save()
                self.stdout.write(self.style.SUCCESS(f"Updated '{old_title}' to '{new_title}'"))

        # Now, ensure all constitutional roles exist.
        def ensure_roles(titles, tier):
            for idx, title in enumerate(titles):
                role, created = RoleDefinition.objects.get_or_create(
                    title=title, tier=tier, 
                    defaults={'seat_number': idx + 1}
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created missing role: {title} ({tier})"))

        ensure_roles(state_roles, 'STATE')
        ensure_roles(zonal_roles, 'ZONAL')
        ensure_roles(lga_roles, 'LGA')
        ensure_roles(ward_roles, 'WARD')
        
        self.stdout.write(self.style.SUCCESS('Role migration complete!'))
