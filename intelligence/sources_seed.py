"""Idempotent starter source directory for the collection engine.

The starter set follows Doc 05 (Source Connector Feasibility):

- The one source the audit verified live — the Kebbi State Government
  Pressroom, a server-rendered HTML listing with no RSS — is seeded
  ENABLED as an official-page connector.
- The national publisher feeds are seeded DISABLED. Doc 05's honesty
  rule: no feed is treated as working until the feed-validation step
  records a successful poll, and owner decision D7 (starter source
  list approval) is still open. A source is enabled from the source
  directory UI once its feed validates.

Every row is a normal ``editorial.Source`` — editable and deletable in
the dashboard source directory. Seeding is ``get_or_create`` by URL:
re-running never duplicates a row and never overwrites an edit.
"""
from editorial.models import Source

STARTER_SOURCES = [
    {
        'name': 'Kebbi State Government Pressroom',
        'url': 'https://kebbistate.gov.ng/governor/pressroom',
        'connector_kind': 'OFFICIAL_PAGE', 'feed': False, 'enabled': True,
    },
    {
        'name': 'News Agency of Nigeria (NAN)',
        'url': 'https://nannews.ng/feed/',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'Premium Times',
        'url': 'https://www.premiumtimesng.com/feed',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'Daily Trust',
        'url': 'https://dailytrust.com/feed',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'The Punch',
        'url': 'https://punchng.com/feed/',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'Vanguard',
        'url': 'https://www.vanguardngr.com/feed/',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'Channels Television',
        'url': 'https://www.channelstv.com/feed/',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'Leadership',
        'url': 'https://leadership.ng/feed/',
        'connector_kind': 'RSS', 'feed': True, 'enabled': False,
    },
    {
        'name': 'INEC News',
        'url': 'https://inecnigeria.org/news/',
        'connector_kind': 'OFFICIAL_PAGE', 'feed': False, 'enabled': False,
    },
]


def seed_sources():
    """Create any missing starter sources; return the rows created."""
    created = []
    for spec in STARTER_SOURCES:
        source, was_created = Source.objects.get_or_create(
            url=spec['url'],
            defaults={
                'name': spec['name'], 'kind': 'NEWS',
                'feed': spec['feed'], 'enabled': spec['enabled'],
                'connector_kind': spec['connector_kind'],
                'poll_interval_minutes': 30, 'max_items': 5,
            })
        if was_created:
            created.append(source)
    return created
