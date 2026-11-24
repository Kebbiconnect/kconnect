"""Signal receivers for the intelligence app (module-level on purpose:
receivers connected from ``ready()`` must not be closures, or Django's
weak references let them be garbage-collected)."""
from . import desk


def sync_intelligence_units(sender, instance, **kwargs):
    """Lane 2 honesty rule (Phase 4): a desk unit reaches PUBLISHED
    only when its linked article actually publishes through the
    normal newsroom flow. Every publish path (web queue, REST API,
    brain handoff) saves the Campaign, so this is the single choke
    point; Lane 1 articles have no linked units and are a no-op."""
    if instance.status == 'PUBLISHED':
        desk.sync_published_units(instance)
    # Phase 7: mirror the article's own stored LGA field into the
    # explicit article↔LGA link table the public LGA pages read.
    # Failure-isolated: a link error must never break an article save.
    try:
        from . import article_locations
        article_locations.sync_campaign_field(instance)
    except Exception:
        pass
