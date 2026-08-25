"""
KPN 2.0 — Data Migration 0011
Renames RoleDefinition title records from old names to KPN 2.0 approved names.

This is a DATA ONLY migration — no schema change, no table drop, no data loss.
All existing User.role_definition foreign key relationships are preserved.
"""
from django.db import migrations


# Complete rename mapping: (old_title, tier) → new_title
# Organised by tier so each entry is unambiguous.
RENAMES = [
    # ─────────────────── STATE TIER ───────────────────
    # No change:
    # President, Vice President, General Secretary, Assistant General Secretary,
    # Legal & Ethics Adviser, Financial Secretary, Auditor General
    ('STATE', 'State Supervisor',
                'Director of Monitoring & Compliance'),
    ('STATE', 'Treasurer',
                'Director of Finance'),
    ('STATE', 'Director of Mobilization',
                'Director of Membership & Mobilization'),
    ('STATE', 'Assistant Director of Mobilization',
                'Assistant Director of Membership & Mobilization'),
    ('STATE', 'Organizing Secretary',
                'Director of Programmes & Events'),
    ('STATE', 'Assistant Organizing Secretary',
                'Assistant Director of Programmes & Events'),
    ('STATE', 'Welfare Officer',
                'Director of Welfare & Community Support'),
    ('STATE', 'Youth Development & Empowerment Officer',
                'Director of Youth Development & Empowerment'),
    ('STATE', 'Women Leader',
                'Director of Women Development'),
    ('STATE', 'Assistant Women Leader',
                'Assistant Director of Women Development'),
    ('STATE', 'Director of Media & Communications',
                'Director of Media & Communications'),
    ('STATE', 'Assistant Director of Media & Communications',
                'Assistant Director of Media & Communications'),
    ('STATE', 'Public Relations & Community Engagement Officer',
                'Director of Public Relations & Community Engagement'),

    # ─────────────────── ZONAL TIER ───────────────────
    ('ZONAL', 'Zonal Coordinator',
                'Senatorial Director'),
    ('ZONAL', 'Zonal Secretary',
                'Senatorial Administrative Officer'),
    ('ZONAL', 'Zonal Publicity Officer',
                'Senatorial Communications Officer'),

    # ─────────────────── LGA TIER ─────────────────────
    ('LGA', 'LGA Coordinator',
                'LGA Network Lead'),
    ('LGA', 'Secretary',
                'LGA Administrative Officer'),
    ('LGA', 'Publicity Officer',
                'LGA Communications Officer'),
    ('LGA', 'LGA Supervisor',
                'LGA Monitoring Officer'),
    ('LGA', 'Director of Contact and Mobilization',
                'LGA Community Engagement Officer'),
    # LGA Adviser — no change
    ('LGA', 'Organizing Secretary',
                'LGA Programmes Officer'),
    ('LGA', 'Welfare Officer',
                'LGA Community Support Officer'),
    ('LGA', 'Women Leader',
                'LGA Women Development Officer'),
    ('LGA', 'Treasurer',
                'LGA Finance Officer'),

    # ─────────────────── WARD TIER ────────────────────
    ('WARD', 'Ward Coordinator',
                'Ward Community Lead'),
    ('WARD', 'Ward Supervisor',
                'Ward Monitoring Officer'),
    # Ward Adviser — no change
    ('WARD', 'Secretary',
                'Ward Administrative Officer'),
    ('WARD', 'Publicity Officer',
                'Ward Communications Officer'),
    ('WARD', 'Organizing Secretary',
                'Ward Programmes Officer'),
    ('WARD', 'Treasurer',
                'Ward Finance Officer'),
    ('WARD', 'Financial Secretary',
                'Ward Community Support Officer'),
]


def rename_role_definitions(apps, schema_editor):
    RoleDefinition = apps.get_model('leadership', 'RoleDefinition')
    renamed = 0
    skipped = 0
    for tier, old_title, new_title in RENAMES:
        updated = RoleDefinition.objects.filter(
            tier=tier, title=old_title
        ).update(title=new_title)
        if updated:
            renamed += 1
            print(f"  [OK] {tier}: '{old_title}' → '{new_title}'")
        else:
            skipped += 1
            print(f"  [SKIP] {tier}: '{old_title}' not found (already renamed or doesn't exist)")
    print(f"\n  Done — {renamed} renamed, {skipped} skipped.")


def reverse_rename_role_definitions(apps, schema_editor):
    """Reverse migration — restores old role titles."""
    RoleDefinition = apps.get_model('leadership', 'RoleDefinition')
    for tier, old_title, new_title in RENAMES:
        RoleDefinition.objects.filter(
            tier=tier, title=new_title
        ).update(title=old_title)


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0010_alter_user_role'),
        ('leadership', '0002_alter_roledefinition_tier'),
    ]

    operations = [
        migrations.RunPython(
            rename_role_definitions,
            reverse_rename_role_definitions,
        ),
    ]
