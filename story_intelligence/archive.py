"""KPN Media Phase 3 — Searchable Story Archive (query layer + view).

The Archive is a reader-facing discovery surface over records that
already exist and are already public: PUBLISHED articles, PUBLISHED
story updates on published articles, and the public promises. It
stores nothing and exposes nothing new: drafts, pending, returned and
archived articles, draft updates, private evidence, consent records,
audit internals and community-reporter data are never queried, so
they can never appear in results, excerpts or counts.

It deliberately does NOT touch the existing newsroom list or its
search (`campaigns.views.newsroom`) — the Archive is an additional
surface at /archive/, not a replacement.

Portability rule: only ORM icontains/Q composition is used — no
database-specific full-text features — so behaviour is identical on
SQLite (tests) and Postgres (production). Body search covers both the
plain-text `content` fallback (always populated by the editorial /
brain paths) and, via a Cast of `content_json` to text, the Editor.js
block text of web-written articles whose fallback may be empty.

Ordering (documented choice): cheap relevance with no new
infrastructure — with a text query, title matches rank before
other-field matches (a Case/When annotation), then newest first.
Without a query: pure recency.
"""
import re
from datetime import date
from html import unescape

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, TextField, Value, When
from django.db.models.functions import Cast
from django.shortcuts import redirect, render
from django.utils.html import strip_tags

from campaigns.models import Campaign
from leadership.models import LGA, Ward, Zone

from .models import Institution, Promise, StoryUpdate

STORY_ID_RE = re.compile(r'^KPN-SI-\d{4}-\d{5}$')
PAGE_SIZE = 20
TYPE_CHOICES = [
    ('story', 'Stories'),
    ('update', 'Story updates'),
    ('promise', 'Promises'),
]


# ─── Parameter handling ───────────────────────────────────────────────────────
# Every filter value is cleaned defensively: invalid values are treated
# as "not set" and can never turn the archive into a 500.

def _clean_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_archive_params(request):
    get = request.GET
    category = get.get('category', '').strip()
    if category not in dict(Campaign.CATEGORY_CHOICES):
        category = ''
    result_type = get.get('type', 'all').strip()
    if result_type not in ('story', 'update', 'promise'):
        result_type = 'all'
    return {
        'q': get.get('q', '').strip(),
        'type': result_type,
        'category': category,
        'zone': _clean_int(get.get('zone')),
        'lga': _clean_int(get.get('lga')),
        'ward': _clean_int(get.get('ward')),
        'institution': _clean_int(get.get('institution')),
        'date_from': _clean_date(get.get('date_from', '').strip()),
        'date_to': _clean_date(get.get('date_to', '').strip()),
    }


def has_active_filters(params):
    return any([params['category'], params['zone'], params['lga'],
                params['ward'], params['institution'],
                params['date_from'], params['date_to']])


# ─── Querysets ────────────────────────────────────────────────────────────────

def _geo_condition(params, prefix=''):
    """Geography condition for models carrying lga/ward FKs (Campaign,
    or StoryUpdate via `prefix='article__'`). A story filed under an
    LGA also matches its zone; a story filed under a ward also matches
    the ward's LGA and zone."""
    condition = Q()
    if params['zone']:
        condition &= (Q(**{f'{prefix}lga__zone_id': params['zone']}) |
                      Q(**{f'{prefix}ward__lga__zone_id': params['zone']}))
    if params['lga']:
        condition &= (Q(**{f'{prefix}lga_id': params['lga']}) |
                      Q(**{f'{prefix}ward__lga_id': params['lga']}))
    if params['ward']:
        condition &= Q(**{f'{prefix}ward_id': params['ward']})
    return condition


def _rank(q):
    return Case(When(title__icontains=q, then=Value(0)),
                default=Value(1), output_field=IntegerField())


def story_queryset(params):
    qs = Campaign.objects.filter(status='PUBLISHED').select_related('lga', 'ward')
    if params['institution']:
        # Institutions belong to promises; the filter empties stories.
        return qs.none()
    q = params['q']
    if q:
        qs = qs.annotate(
            json_text=Cast('content_json', output_field=TextField()),
            rank=_rank(q),
        ).filter(
            Q(title__icontains=q) | Q(subheadline__icontains=q) |
            Q(location__icontains=q) | Q(content__icontains=q) |
            Q(json_text__icontains=q) | Q(story_id__icontains=q))
        qs = qs.order_by('rank', '-published_at', '-pk')
    else:
        qs = qs.order_by('-published_at', '-pk')
    if params['category']:
        qs = qs.filter(category=params['category'])
    qs = qs.filter(_geo_condition(params))
    if params['date_from']:
        qs = qs.filter(published_at__date__gte=params['date_from'])
    if params['date_to']:
        qs = qs.filter(published_at__date__lte=params['date_to'])
    return qs


def update_queryset(params):
    qs = StoryUpdate.objects.filter(
        status='PUBLISHED', article__status='PUBLISHED',
    ).select_related('article', 'article__lga', 'article__ward')
    if params['institution']:
        return qs.none()
    q = params['q']
    if q:
        qs = qs.annotate(rank=_rank(q)).filter(
            Q(title__icontains=q) | Q(body__icontains=q))
        qs = qs.order_by('rank', '-published_at', '-pk')
    else:
        qs = qs.order_by('-published_at', '-pk')
    if params['category']:
        qs = qs.filter(article__category=params['category'])
    qs = qs.filter(_geo_condition(params, prefix='article__'))
    if params['date_from']:
        qs = qs.filter(published_at__date__gte=params['date_from'])
    if params['date_to']:
        qs = qs.filter(published_at__date__lte=params['date_to'])
    return qs


def promise_queryset(params):
    qs = Promise.objects.select_related('institution', 'zone', 'lga', 'ward')
    if params['category']:
        # Promises carry no newsroom category; the filter empties them.
        return qs.none()
    q = params['q']
    if q:
        qs = qs.annotate(rank=_rank(q)).filter(
            Q(title__icontains=q) | Q(description__icontains=q) |
            Q(institution__name__icontains=q))
        qs = qs.order_by('rank', '-announced_on', '-pk')
    else:
        qs = qs.order_by('-announced_on', '-pk')
    if params['zone']:
        qs = qs.filter(zone_id=params['zone'])
    if params['lga']:
        qs = qs.filter(lga_id=params['lga'])
    if params['ward']:
        qs = qs.filter(ward_id=params['ward'])
    if params['institution']:
        qs = qs.filter(institution_id=params['institution'])
    if params['date_from']:
        qs = qs.filter(announced_on__gte=params['date_from'])
    if params['date_to']:
        qs = qs.filter(announced_on__lte=params['date_to'])
    return qs


# ─── Excerpts ─────────────────────────────────────────────────────────────────
# Excerpts are plain strings built here and rendered by the template
# with normal auto-escaping (never |safe): HTML in body text or in the
# query itself is displayed as text, never injected.

def _block_texts(content_json):
    texts = []
    if isinstance(content_json, dict):
        for block in content_json.get('blocks', []):
            if not isinstance(block, dict):
                continue
            data = block.get('data', {})
            if not isinstance(data, dict):
                continue
            for key in ('text', 'content'):
                value = data.get(key)
                if isinstance(value, str):
                    texts.append(value)
            items = data.get('items')
            if isinstance(items, list):
                texts.extend(item for item in items if isinstance(item, str))
    return texts


def article_body_text(article):
    """Plain-text body of an article, for excerpts only. The stored
    `content` fallback is HTML-escaped at write time on the editorial
    paths, so it is unescaped here; the template re-escapes on render."""
    if article.content and article.content.strip():
        return unescape(article.content)
    return ' '.join(_block_texts(article.content_json))


def make_excerpt(text, query='', context_words=14, tail_words=26, head_words=42):
    text = ' '.join(strip_tags(text or '').split())
    if not text:
        return ''
    words = text.split(' ')
    if query:
        idx = text.lower().find(query.lower())
        if idx >= 0:
            pos = 0
            hit = 0
            for i, word in enumerate(words):
                if pos + len(word) >= idx:
                    hit = i
                    break
                pos += len(word) + 1
            start = max(0, hit - context_words)
            end = min(len(words), hit + tail_words)
            excerpt = ' '.join(words[start:end])
            if start:
                excerpt = '… ' + excerpt
            if end < len(words):
                excerpt += ' …'
            return excerpt
    excerpt = ' '.join(words[:head_words])
    if len(words) > head_words:
        excerpt += ' …'
    return excerpt


# ─── View ─────────────────────────────────────────────────────────────────────

def archive_home(request):
    params = parse_archive_params(request)
    q = params['q']

    # Exact Story ID lookup: a well-formed ID resolves directly to the
    # story's article page. An unknown ID falls through to the normal
    # search, which simply finds nothing for it.
    if q and STORY_ID_RE.match(q.upper()):
        article = Campaign.objects.filter(
            status='PUBLISHED', story_id=q.upper()).only('slug').first()
        if article is not None:
            return redirect('campaigns:article_detail', slug=article.slug)

    browsing = (not q and params['type'] == 'all'
                and not has_active_filters(params))
    show_updates = params['type'] in ('all', 'update') and not browsing
    show_promises = params['type'] in ('all', 'promise') and not browsing
    show_stories = params['type'] in ('all', 'story')

    # Pagination links preserve every parameter except the page
    # numbers themselves (each section paginates independently).
    query_params = request.GET.copy()
    for key in ('sp', 'up', 'pp'):
        query_params.pop(key, None)
    base_qs = query_params.urlencode()

    context = {
        'params': params,
        'browsing': browsing,
        'base_qs': base_qs,
        'categories': Campaign.CATEGORY_CHOICES,
        'type_choices': TYPE_CHOICES,
        'zones': Zone.objects.all(),
        'lgas': LGA.objects.all(),
        'wards': (Ward.objects.filter(lga_id=params['lga'])
                  if params['lga'] else Ward.objects.all()
                  ).select_related('lga'),
        'institutions': Institution.objects.all(),
        'show_stories': show_stories,
        'show_updates': show_updates,
        'show_promises': show_promises,
    }

    total = 0
    if show_stories:
        paginator = Paginator(story_queryset(params), PAGE_SIZE)
        page = paginator.get_page(request.GET.get('sp'))
        for article in page.object_list:
            text = article_body_text(article)
            if q and q.lower() in (article.subheadline or '').lower():
                text = article.subheadline
            article.excerpt = make_excerpt(text, q)
        context['stories_page'] = page
        context['stories_total'] = paginator.count
        total += paginator.count
    if show_updates:
        paginator = Paginator(update_queryset(params), PAGE_SIZE)
        page = paginator.get_page(request.GET.get('up'))
        for update in page.object_list:
            update.excerpt = make_excerpt(update.body, q)
        context['updates_page'] = page
        context['updates_total'] = paginator.count
        total += paginator.count
    if show_promises:
        paginator = Paginator(promise_queryset(params), PAGE_SIZE)
        page = paginator.get_page(request.GET.get('pp'))
        for promise in page.object_list:
            promise.excerpt = make_excerpt(promise.description, q)
        context['promises_page'] = page
        context['promises_total'] = paginator.count
        total += paginator.count
    context['total_results'] = total

    return render(request, 'story_intelligence/archive.html', context)
