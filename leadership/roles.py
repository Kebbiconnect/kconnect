"""Canonical KPN role contract.

This module is the runtime source of truth.  Migrations preserve historical names,
but application code must compare against the constants below.
"""
STATE_ROLES = (
    'President', 'Vice President', 'General Secretary', 'Assistant General Secretary',
    'Director of Monitoring & Compliance', 'Director of Legal Affairs & Ethics',
    'Director of Finance', 'Finance Operations Officer', 'Director of Community Engagement',
    'Assistant Director of Community Engagement', 'Director of Programmes & Events',
    'Assistant Director of Programmes & Events', 'Director of Audit & Accountability',
    'Director of Member Support & Welfare', 'Director of Youth Development',
    "Director of Women's Development", "Assistant Director of Women's Development",
    'Director of Media & Communications', 'Assistant Director of Media & Communications',
    'Director of Public Relations & Partnerships',
)
ZONAL_ROLES = ('Senatorial Director', 'Senatorial Administrative Officer', 'Senatorial Communications Officer')
LGA_ROLES = (
    'LGA Network Lead', 'LGA Administrative Officer', 'LGA Programmes Officer',
    'LGA Finance Officer', 'LGA Communications Officer', 'LGA Monitoring Officer',
    "LGA Women's Development Officer", 'LGA Member Support Officer',
    'LGA Community Engagement Officer', 'LGA Adviser',
)
WARD_ROLES = (
    'Ward Community Lead', 'Ward Administrative Officer', 'Ward Programmes Officer',
    'Ward Finance Officer', 'Ward Communications Officer', 'Ward Monitoring Officer',
    'Ward Community Support Officer', 'Ward Adviser',
)
ROLES_BY_TIER = {'STATE': STATE_ROLES, 'ZONAL': ZONAL_ROLES, 'LGA': LGA_ROLES, 'WARD': WARD_ROLES}
ALL_ROLES = tuple(r for roles in ROLES_BY_TIER.values() for r in roles)
ROLE_ALIASES = {
    'State Supervisor': 'Director of Monitoring & Compliance',
    'Director of Mobilization': 'Director of Community Engagement',
    'Assistant Director of Mobilization': 'Assistant Director of Community Engagement',
    'Youth Development & Empowerment Officer': 'Director of Youth Development',
    'Assistant Women Leader': "Assistant Director of Women's Development",
    'Public Relations & Community Engagement Officer': 'Director of Public Relations & Partnerships',
    'Director of Contact and Mobilization': 'LGA Community Engagement Officer',
    'State Coordinator': 'President', 'State Secretary': 'General Secretary',
    'State Publicity Secretary': 'Director of Media & Communications', 'Treasurer': 'Director of Finance',
    'Financial Secretary': 'Finance Operations Officer', 'Organizing Secretary': 'Director of Programmes & Events',
    'Assistant Organizing Secretary': 'Assistant Director of Programmes & Events',
    'Welfare Officer': 'Director of Member Support & Welfare', "Women Leader": "Director of Women's Development",
    'Legal & Ethics Adviser': 'Director of Legal Affairs & Ethics',
    'Director of Membership & Mobilization': 'Director of Community Engagement',
    'Assistant Director of Membership & Mobilization': 'Assistant Director of Community Engagement',
    'Auditor General': 'Director of Audit & Accountability',
    'Director of Welfare & Community Support': 'Director of Member Support & Welfare',
    'Director of Youth Development & Empowerment': 'Director of Youth Development',
    'Director of Women Development': "Director of Women's Development",
    'Assistant Director of Women Development': "Assistant Director of Women's Development",
    'Director of Public Relations & Community Engagement': 'Director of Public Relations & Partnerships',
    'Zonal Coordinator': 'Senatorial Director', 'Zonal Secretary': 'Senatorial Administrative Officer',
    'Zonal Publicity Officer': 'Senatorial Communications Officer', 'LGA Coordinator': 'LGA Network Lead',
    'LGA Secretary': 'LGA Administrative Officer', 'LGA Organizing Secretary': 'LGA Programmes Officer',
    'LGA Treasurer': 'LGA Finance Officer', 'LGA Publicity Officer': 'LGA Communications Officer',
    'LGA Supervisor': 'LGA Monitoring Officer', 'LGA Women Development Officer': "LGA Women's Development Officer",
    'LGA Community Support Officer': 'LGA Member Support Officer', 'Ward Coordinator': 'Ward Community Lead',
    'Ward Secretary': 'Ward Administrative Officer', 'Ward Organizing Secretary': 'Ward Programmes Officer',
    'Ward Treasurer': 'Ward Finance Officer', 'Ward Publicity Officer': 'Ward Communications Officer',
    'Ward Supervisor': 'Ward Monitoring Officer',
}
EDITOR_ROLES = ('President', 'General Secretary', 'Director of Media & Communications', 'Assistant Director of Media & Communications')
PUBLICITY_ROLES = ('Director of Media & Communications', 'Assistant Director of Media & Communications', 'Senatorial Communications Officer', 'LGA Communications Officer', 'Ward Communications Officer')
EVENT_MANAGER_ROLES = ('Director of Programmes & Events', 'Assistant Director of Programmes & Events')
TELEGRAM_REQUIRED_ROLE_TITLES = STATE_ROLES + ZONAL_ROLES + ('LGA Network Lead', 'Ward Community Lead')

def canonical_role_title(title):
    return ROLE_ALIASES.get(title, title)
