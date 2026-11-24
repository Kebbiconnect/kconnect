"""Seed the intelligence categories (idempotent, additive only).

Only intelligence-owned data is seeded by migration. The geographic
directory (zones/LGAs/aliases) is seeded by the idempotent
``seed_intelligence_directory`` management command instead: leadership.Zone
names are unique and pre-seeding them here would collide with existing
test fixtures that create zones by name.
"""
from django.db import migrations

CATEGORIES = [
    ('government-governance', 'Government & Governance', False),
    ('politics-elections', 'Politics & Elections', True),
    ('security-public-safety', 'Security & Public Safety', True),
    ('education', 'Education', False),
    ('healthcare', 'Healthcare', False),
    ('agriculture-food-security', 'Agriculture & Food Security', False),
    ('infrastructure-roads', 'Infrastructure & Roads', False),
    ('water-sanitation', 'Water & Sanitation', False),
    ('electricity-energy', 'Electricity & Energy', False),
    ('economy-employment', 'Economy & Employment', False),
    ('business-investment', 'Business & Investment', False),
    ('environment-climate', 'Environment & Climate', False),
    ('community-development', 'Community Development', False),
    ('human-rights-justice', 'Human Rights & Justice', True),
    ('youth-sports', 'Youth & Sports', False),
    ('women-social-development', 'Women & Social Development', False),
    ('public-accountability', 'Public Accountability', True),
    ('traditional-institutions', 'Traditional Institutions', False),
    ('humanitarian-affairs', 'Humanitarian Affairs', False),
    ('emergencies-disasters', 'Emergencies & Disasters', False),
    ('opportunities-scholarships', 'Opportunities & Scholarships', False),
    ('other', 'Other', False),
]


def seed(apps, schema_editor):
    Category = apps.get_model('intelligence', 'IntelligenceCategory')
    for slug, label, sensitive in CATEGORIES:
        Category.objects.get_or_create(
            slug=slug, defaults={'label': label, 'is_sensitive': sensitive})


class Migration(migrations.Migration):
    dependencies = [
        ('intelligence', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
