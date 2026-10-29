"""Shared factories for editorial tests."""
from leadership.models import LGA, RoleDefinition, Ward, Zone
from staff.models import User

def geo():
    # Never cache ORM objects across tests: TestCase rollbacks would leave
    # stale ids. Always resolve fresh rows by name.
    zone, _ = Zone.objects.get_or_create(name='Editorial Test Zone')
    lga, _ = LGA.objects.get_or_create(name='Editorial Test LGA', zone=zone)
    ward, _ = Ward.objects.get_or_create(name='Editorial Test Ward', lga=lga)
    return zone, lga, ward


def make_user(username, title=None, tier='STATE', role='STATE', status='VERIFIED', **kw):
    zone, lga, ward = geo()
    rd = None
    if title:
        rd, _ = RoleDefinition.objects.get_or_create(
            title=title, tier=tier, defaults={'seat_number': 1})
    return User.objects.create_user(
        username=username, phone=username, role=role, status=status,
        role_definition=rd, zone=zone, lga=lga, ward=ward, **kw)


def media_director(username='ed_media'):
    return make_user(username, title='Director of Media & Communications')


def assistant_media(username='ed_asst_media'):
    return make_user(username, title='Assistant Director of Media & Communications')


def president(username='ed_president'):
    return make_user(username, title='President')


def general_member(username='ed_member'):
    return make_user(username, title=None, role='GENERAL')
