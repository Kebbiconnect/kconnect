from django.db import migrations
ALIASES={
'State Supervisor':'Director of Monitoring & Compliance','Director of Mobilization':'Director of Community Engagement','Assistant Director of Mobilization':'Assistant Director of Community Engagement','Youth Development & Empowerment Officer':'Director of Youth Development','Assistant Women Leader':"Assistant Director of Women's Development",'Public Relations & Community Engagement Officer':'Director of Public Relations & Partnerships','Director of Contact and Mobilization':'LGA Community Engagement Officer','Legal & Ethics Adviser':'Director of Legal Affairs & Ethics','Financial Secretary':'Finance Operations Officer','Director of Membership & Mobilization':'Director of Community Engagement','Assistant Director of Membership & Mobilization':'Assistant Director of Community Engagement','Auditor General':'Director of Audit & Accountability','Director of Welfare & Community Support':'Director of Member Support & Welfare','Director of Youth Development & Empowerment':'Director of Youth Development','Director of Women Development':"Director of Women's Development",'Assistant Director of Women Development':"Assistant Director of Women's Development",'Director of Public Relations & Community Engagement':'Director of Public Relations & Partnerships','LGA Women Development Officer':"LGA Women's Development Officer",'LGA Community Support Officer':'LGA Member Support Officer','Organizing Secretary':'Director of Programmes & Events','Assistant Organizing Secretary':'Assistant Director of Programmes & Events','LGA Coordinator':'LGA Network Lead','Ward Coordinator':'Ward Community Lead'}
def forwards(apps,schema_editor):
 Role=apps.get_model('leadership','RoleDefinition'); User=apps.get_model('staff','User')
 for old,new in ALIASES.items():
  for source in Role.objects.filter(title=old):
   target=Role.objects.filter(title=new,tier=source.tier).first()
   if target:
    User.objects.filter(role_definition=source).update(role_definition=target); source.delete()
   else: source.title=new; source.save(update_fields=['title'])
class Migration(migrations.Migration):
 dependencies=[('leadership','0004_fix_role_titles'),('staff','0014_reconcile_user_status')]
 operations=[migrations.RunPython(forwards,migrations.RunPython.noop)]
