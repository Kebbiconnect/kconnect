"""Shared helpers for intelligence tests."""
from django.core.management import call_command


def seed_directory():
    call_command('seed_intelligence_directory', verbosity=0)
