from django.db import migrations, models

def normalize(apps, schema_editor):
    User=apps.get_model('staff','User')
    User.objects.filter(status='APPROVED').update(status='VERIFIED')
class Migration(migrations.Migration):
    dependencies=[('staff','0013_user_is_trusted_reporter_user_reporter_level')]
    operations=[migrations.RunPython(normalize,migrations.RunPython.noop),migrations.AlterField(model_name='user',name='status',field=models.CharField(choices=[('PENDING','Pending'),('UNDER_REVIEW','Under Review'),('VERIFIED','Verified'),('REJECTED','Rejected'),('SUSPENDED','Suspended'),('DISMISSED','Dismissed')],default='PENDING',max_length=20))]
