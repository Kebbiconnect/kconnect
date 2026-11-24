"""Article ↔ LGA associations (Phase 7).

The public LGA news pages must never guess which LGA a story belongs
to from its wording at render time. They read :class:`ArticleLocation`
rows — explicit associations written at the moments the association
is actually known:

- when the verification desk converts a unit into a newsroom draft
  (:func:`link_from_unit` — the unit's own evidence records carry the
  locations);
- when an article's own stored ``Campaign.lga`` field is set
  (:func:`sync_campaign_field` — wired to the Campaign save signal so
  Lane 1 and Lane 2 articles alike are mirrored);
- when a staff member tags an article by hand through the dashboard
  control (kind MANUAL, in the views).

The ``backfill_article_locations`` management command replays the
first two paths over existing records, idempotently.
"""
from django.db.models import Count
from django.utils.text import slugify

from leadership.models import LGA

from .models import ArticleLocation


def lga_slug(lga):
    """The public URL slug for an LGA, derived from its recorded name."""
    return slugify(lga.name)


def lga_for_slug(slug):
    """Resolve a public slug back to an LGA record, or None."""
    for lga in LGA.objects.all():
        if lga_slug(lga) == slug:
            return lga
    return None


def link(article, lga, kind, actor=None, upgrade=False):
    """Record an article↔LGA association; returns (row, created).

    The unique (article, lga) pair means the first writer normally
    wins the ``kind`` attribution. A desk conversion passes
    ``upgrade=True``: the article-field mirror fires during the
    conversion's own ``Campaign`` create (a moment earlier, kind
    ARTICLE), and the conversion is the more precise origin, so it
    may re-attribute that row to CONVERSION.
    """
    row, created = ArticleLocation.objects.get_or_create(
        article=article, lga=lga,
        defaults={'kind': kind,
                  'created_by': actor if actor is not None
                  and getattr(actor, 'is_authenticated', False) else None})
    if not created and upgrade and row.kind == 'ARTICLE':
        row.kind = kind
        if actor is not None and getattr(
                actor, 'is_authenticated', False):
            row.created_by = actor
        row.save(update_fields=['kind', 'created_by'])
        created = True
    return row, created


def unit_lgas(unit):
    """Every LGA a desk unit's own records evidence, primary first.

    Clusters: the cluster's primary LGA plus every LGA on its member
    publications' location rows. Standalone items: every LGA on the
    item's location rows. This is recorded evidence (engine matches
    and manual rows alike), not a fresh guess.
    """
    from .desk import unit_members
    ordered, seen = [], set()

    def add(lga):
        if lga is not None and lga.pk not in seen:
            seen.add(lga.pk)
            ordered.append(lga)

    add(getattr(unit, 'primary_lga', None))
    for member in unit_members(unit):
        for location in member.locations.select_related('lga') \
                .exclude(lga__isnull=True).order_by('pk'):
            add(location.lga)
    return ordered


def link_from_unit(unit, article, actor=None):
    """CONVERSION rows for every LGA the converted unit evidences."""
    rows = []
    for lga in unit_lgas(unit):
        row, _created = link(article, lga, 'CONVERSION', actor=actor,
                             upgrade=True)
        rows.append(row)
    return rows


def sync_campaign_field(article):
    """Mirror an article's own stored ``lga`` field (kind ARTICLE)."""
    if getattr(article, 'lga_id', None):
        row, _created = link(article, article.lga, 'ARTICLE')
        return row
    return None


def published_stories(lga):
    """The LGA's published stories, newest first — the public query."""
    from campaigns.models import Campaign
    return (Campaign.objects
            .filter(status='PUBLISHED', lga_links__lga=lga)
            .select_related('lga')
            .order_by('-published_at', '-created_at', '-pk')
            .distinct())


def story_counts_by_lga():
    """{lga_pk: published story count} from the link rows only."""
    return {
        row['lga_id']: row['n']
        for row in ArticleLocation.objects
        .filter(article__status='PUBLISHED')
        .values('lga_id').annotate(n=Count('article', distinct=True))
    }
