from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('editorial', '0001_initial')]
    operations = [
        migrations.DeleteModel(name='Usage'),
        migrations.DeleteModel(name='Budget'),
    ]
