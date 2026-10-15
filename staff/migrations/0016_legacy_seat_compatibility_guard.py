from django.db import migrations
from ._seat_integrity import install_guard


class Migration(migrations.Migration):
    dependencies = [('staff', '0015_announcement_state_executive_scope')]
    # Also upgrades databases that applied the original strict 0014 already.
    # Reverse keeps the guard; never silently restore incompatible old indexes.
    operations = [migrations.RunPython(install_guard, migrations.RunPython.noop)]
