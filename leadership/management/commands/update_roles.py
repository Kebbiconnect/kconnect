from django.core.management.base import BaseCommand
from django.db import transaction
from leadership.models import RoleDefinition
from leadership.roles import ROLES_BY_TIER, ROLE_ALIASES
from staff.models import User
class Command(BaseCommand):
 help='Safely canonicalizes and creates KPN constitutional roles without deleting users.'
 @transaction.atomic
 def handle(self,*args,**kwargs):
  for old,new in ROLE_ALIASES.items():
   for source in RoleDefinition.objects.filter(title=old):
    target=RoleDefinition.objects.filter(title=new,tier=source.tier).first()
    if target: User.objects.filter(role_definition=source).update(role_definition=target); source.delete()
    else: source.title=new; source.save(update_fields=['title'])
  for tier,titles in ROLES_BY_TIER.items():
   for seat,title in enumerate(titles,1): RoleDefinition.objects.get_or_create(title=title,tier=tier,defaults={'seat_number':seat})
  self.stdout.write(self.style.SUCCESS('Canonical KPN roles reconciled.'))
