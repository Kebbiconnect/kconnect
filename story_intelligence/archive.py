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

Page-by-Page Upgrade Priority 4 (brief §G, decision D-13): the
archive gains a TOPIC axis — the section a record belongs to (News,
Human Impact Files, Future Signal, Promise Tracker), carried by
`StoryProfile.kind` and the Promise records themselves; no tagging
model was built. Text search also reaches the public claims recorded
on a story or update (the same claims the article's Story File panel
shows readers). Result rows carry their record status (Published /
Updated / Corrected, derived from StoryUpdate and Correction
existence), their section badging, their Promise Tracker links and
related published stories — all linked records, never copies.
"""
import re
from datetime import date, datetime, time, timedelta
from html import unescape

from django.core.paginator import Paginator
from django.db.models import (
    Case, Count, IntegerField, Q, TextField, Value, When,
)
from django.db.models.functions import Cast
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.utils.html import strip_tags

from campaigns.models import Campaign
from leadership.models import LGA, Ward, Zone

from .models import Correction, Institution, Promise, StoryUpdate

STORY_ID_RE = re.compile(r'^KPN-SI-\d{4}-\d{5}$')
# Search variant (2.0.7): an ID typed or pasted with surrounding text —
# "Story ID: KPN-SI-2026-00088", a trailing full stop, lowercase — must
# still resolve. The anchored pattern above only fired when the whole
# query was exactly the ID, so any decoration silently fell through to
# a text search for the full decorated string and returned nothing.
STORY_ID_SEARCH_RE = re.compile(r'KPN-SI-\d{4}-\d{5}', re.IGNORECASE)


def extract_story_id(text):
    """The well-formed Story ID contained in `text`, uppercased, or
    None. Exact-match semantics are preserved: the returned value is
    the canonical KPN-SI-YYYY-NNNNN form stored on the article."""
    if not text:
        return None
    match = STORY_ID_SEARCH_RE.search(str(text))
    return match.group(0).upper() if match else None


PAGE_SIZE = 20
TYPE_CHOICES = [
    ('story', 'Stories'),
    ('update', 'Story updates'),
    ('promise', 'Promises'),
]
# D-13: topic = the section a record belongs to. 'news' also covers
# stories with no StoryProfile at all (the profile is optional; an
# unprofiled published story is a news story).
TOPIC_CHOICES = [
    ('news', 'News'),
    ('impact', 'Human Impact Files'),
    ('signal', 'Future Signal'),
    ('promise', 'Promise Tracker'),
]
SECTION_LABELS = {
    'NEWS': 'News story',
    'IMPACT': 'Human Impact File',
    'SIGNAL': 'Future Signal',
}


# ─── Parameter handling ───────────────────────────────────────────────────────
# Every filter value is cleaned defensively: invalid values are treated
# as "not set" and can never turn the archive into a 500.

def _clean_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_DATE_FORMATS = ('%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d',
                 '%d %B %Y', '%d %b %Y')


def _clean_date(value):
    """Parse a filter date defensively. Accepts the ISO date the web
    form sends, an ISO datetime (a mobile date-range picker commonly
    emits one — previously rejected outright, which silently dropped
    the filter), and the common day-first renderings. Anything else is
    treated as "not set" and can never turn the archive into a 500."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
        if dj_timezone.is_aware(parsed):
            parsed = dj_timezone.localtime(parsed)
        return parsed.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        parsed = None
    if parsed is not None:
        if dj_timezone.is_aware(parsed):
            parsed = dj_timezone.localtime(parsed)
        return parsed.date()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_archive_params(request):
    get = request.GET
    category = get.get('category', '').strip()
    if category not in dict(Campaign.CATEGORY_CHOICES):
        category = ''
    result_type = get.get('type', 'all').strip()
    if result_type not in ('story', 'update', 'promise'):
        result_type = 'all'
    topic = get.get('topic', '').strip()
    if topic not in dict(TOPIC_CHOICES):
        topic = ''
    q = get.get('q', '').strip()
    if not q:
        # A dedicated story_id parameter (sent by API clients that keep
        # the ID in its own field) is a Story ID lookup, not a browse.
        q = get.get('story_id', '').strip()
    # Additive aliases: clients that name the range from/to or
    # from_date/to_date mean the same From–To filter.
    date_from = _clean_date(
        get.get('date_from') or get.get('from_date') or get.get('from'))
    date_to = _clean_date(
        get.get('date_to') or get.get('to_date') or get.get('to'))
    if date_from and date_to and date_from > date_to:
        # A reversed From–To pair (a picker returning its endpoints in
        # the other order) previously filtered gte the later date AND
        # lte the earlier one — a combination that can never match and
        # silently returned zero results. The intended range is the
        # same two dates, so order them.
        date_from, date_to = date_to, date_from
    return {
        'q': q,
        'type': result_type,
        'topic': topic,
        'category': category,
        'zone': _clean_int(get.get('zone')),
        'lga': _clean_int(get.get('lga')),
        'ward': _clean_int(get.get('ward')),
        'institution': _clean_int(get.get('institution')),
        'date_from': date_from,
        'date_to': date_to,
    }


def has_active_filters(params):
    return any([params['topic'], params['category'], params['zone'],
                params['lga'], params['ward'], params['institution'],
                params['date_from'], params['date_to']])


def _topic_condition(params, prefix=''):
    """Topic condition (D-13) for models carrying a story profile:
    Campaign directly, or StoryUpdate via `prefix='article__'`.
    'promise' is handled by the callers (it empties story/update
    results and keeps only promises), so it maps to no condition here."""
    topic = params['topic']
    if topic == 'impact':
        return Q(**{f'{prefix}story_profile__kind': 'IMPACT'})
    if topic == 'signal':
        return Q(**{f'{prefix}story_profile__kind': 'SIGNAL'})
    if topic == 'news':
        return (Q(**{f'{prefix}story_profile__isnull': True}) |
                Q(**{f'{prefix}story_profile__kind': 'NEWS'}))
    return Q()


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


def _published_range(params):
    """(gte, lt) aware datetimes bounding the From–To dates in the
    site's timezone (Africa/Lagos): from the start of the From day to
    the start of the day AFTER the To day, so a story published at any
    time ON the To date matches. Explicit bounds are used instead of
    the `__date` transform, whose result depends on the database
    session timezone (Postgres vs SQLite) and could shift a story
    published just after midnight Lagos time onto the previous day."""
    tz = dj_timezone.get_default_timezone()
    start = end = None
    if params['date_from']:
        start = dj_timezone.make_aware(
            datetime.combine(params['date_from'], time.min), tz)
    if params['date_to']:
        end = dj_timezone.make_aware(
            datetime.combine(params['date_to'] + timedelta(days=1),
                             time.min), tz)
    return start, end


def _apply_published_range(qs, params, field='published_at'):
    start, end = _published_range(params)
    if start is not None:
        qs = qs.filter(**{f'{field}__gte': start})
    if end is not None:
        qs = qs.filter(**{f'{field}__lt': end})
    return qs


def story_queryset(params):
    qs = Campaign.objects.filter(status='PUBLISHED').select_related(
        'lga', 'ward', 'story_profile')
    if params['institution']:
        # Institutions belong to promises; the filter empties stories.
        return qs.none()
    if params['topic'] == 'promise':
        # The Promise Tracker topic holds promises only.
        return qs.none()
    q = params['q']
    if q:
        qs = qs.annotate(
            json_text=Cast('content_json', output_field=TextField()),
            rank=_rank(q),
        ).filter(
            Q(title__icontains=q) | Q(subheadline__icontains=q) |
            Q(location__icontains=q) | Q(content__icontains=q) |
            Q(json_text__icontains=q) | Q(story_id__icontains=q) |
            Q(claims__text__icontains=q)).distinct()
        qs = qs.order_by('rank', '-published_at', '-pk')
    else:
        qs = qs.order_by('-published_at', '-pk')
    if params['category']:
        qs = qs.filter(category=params['category'])
    qs = qs.filter(_topic_condition(params))
    qs = qs.filter(_geo_condition(params))
    qs = _apply_published_range(qs, params)
    return qs


def update_queryset(params):
    qs = StoryUpdate.objects.filter(
        status='PUBLISHED', article__status='PUBLISHED',
    ).select_related('article', 'article__lga', 'article__ward',
                     'article__story_profile')
    if params['institution']:
        return qs.none()
    if params['topic'] == 'promise':
        return qs.none()
    q = params['q']
    if q:
        qs = qs.annotate(rank=_rank(q)).filter(
            Q(title__icontains=q) | Q(body__icontains=q) |
            Q(claims__text__icontains=q)).distinct()
        qs = qs.order_by('rank', '-published_at', '-pk')
    else:
        qs = qs.order_by('-published_at', '-pk')
    if params['category']:
        qs = qs.filter(article__category=params['category'])
    qs = qs.filter(_topic_condition(params, prefix='article__'))
    qs = qs.filter(_geo_condition(params, prefix='article__'))
    qs = _apply_published_range(qs, params)
    return qs


def promise_queryset(params):
    qs = Promise.objects.select_related(
        'institution', 'zone', 'lga', 'ward').prefetch_related('stories')
    if params['category']:
        # Promises carry no newsroom category; the filter empties them.
        return qs.none()
    if params['topic'] in ('news', 'impact', 'signal'):
        # Story topics hold stories (and their updates) only.
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


# ─── Row enrichment (Priority 4) ──────────────────────────────────────────────
# Everything attached to a result row is derived from records that
# already exist and are already public: the story's section (its
# StoryProfile kind), its published updates, its published corrections,
# the promises that link to it, and other published stories. Nothing
# is copied and nothing is invented.

def _section_for(article):
    """(kind, label, section url) for a story: its StoryProfile kind,
    defaulting to NEWS for stories with no profile. IMPACT and SIGNAL
    stories also live in their own public sections, so the row links
    across to them; a news story's record is its article page itself."""
    profile = getattr(article, 'story_profile', None)
    kind = profile.kind if profile is not None else 'NEWS'
    url = None
    if kind == 'IMPACT':
        url = reverse('impact_files:list')
    elif kind == 'SIGNAL':
        url = reverse('signals:list')
    return kind, SECTION_LABELS[kind], url


def _counts_by(rows):
    return {row[0]: row[1] for row in rows}


def _enrich_stories(articles):
    ids = [a.pk for a in articles]
    if not ids:
        return
    update_counts = _counts_by(
        StoryUpdate.objects.filter(article_id__in=ids, status='PUBLISHED')
        .values_list('article_id').annotate(n=Count('pk')))
    correction_counts = _counts_by(
        Correction.objects.filter(article_id__in=ids, published=True)
        .values_list('article_id').annotate(n=Count('pk')))
    linked = {}
    for promise in Promise.objects.filter(stories__in=ids).distinct():
        for story in promise.stories.all():
            if story.pk in ids:
                linked.setdefault(story.pk, []).append(promise)
    for article in articles:
        article.section_kind, article.section_label, article.section_url = \
            _section_for(article)
        article.update_count = update_counts.get(article.pk, 0)
        article.correction_count = correction_counts.get(article.pk, 0)
        article.linked_promises = linked.get(article.pk, [])
        article.related_stories = _related_stories(article)


def _related_stories(article, limit=3):
    """Other published stories in the same LGA (a story filed under a
    ward counts for its LGA) or the same news category, newest first."""
    condition = Q(category=article.category)
    if article.lga_id:
        condition |= Q(lga_id=article.lga_id) | Q(ward__lga_id=article.lga_id)
    elif article.ward_id:
        condition |= Q(ward__lga_id=article.ward.lga_id)
    return list(
        Campaign.objects.filter(status='PUBLISHED').filter(condition)
        .exclude(pk=article.pk).order_by('-published_at', '-pk')[:limit])


def _enrich_updates(updates):
    ids = [u.pk for u in updates]
    if not ids:
        return
    correction_counts = _counts_by(
        Correction.objects.filter(update_id__in=ids, published=True)
        .values_list('update_id').annotate(n=Count('pk')))
    for update in updates:
        update.section_kind, update.section_label, update.section_url = \
            _section_for(update.article)
        update.correction_count = correction_counts.get(update.pk, 0)


def _enrich_promises(promises):
    for promise in promises:
        promise.linked_stories = [
            story for story in promise.stories.all()
            if story.status == 'PUBLISHED']


def _record_counts():
    """Real totals for the page's trust strip and connected-sections
    band — the same definitions the sections themselves use."""
    published = Campaign.objects.filter(status='PUBLISHED')
    return {
        'stories': published.count(),
        'updates': StoryUpdate.objects.filter(
            status='PUBLISHED', article__status='PUBLISHED').count(),
        'promises': Promise.objects.count(),
        'impact': published.filter(story_profile__kind='IMPACT').count(),
        'signal': published.filter(story_profile__kind='SIGNAL').count(),
    }


# ─── View ─────────────────────────────────────────────────────────────────────

def archive_home(request):
    params = parse_archive_params(request)
    q = params['q']

    # Exact Story ID lookup: a well-formed ID resolves directly to the
    # story's article page. The ID may be the whole query or embedded
    # in it (typed/pasted with a label or punctuation — see
    # extract_story_id). An unknown ID falls through to the normal
    # search, which simply finds nothing for it.
    story_id = extract_story_id(q)
    if story_id:
        article = Campaign.objects.filter(
            status='PUBLISHED', story_id=story_id).only('slug').first()
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
        'topic_choices': TOPIC_CHOICES,
        'record_counts': _record_counts(),
        'crumbs': [
            ('Newsroom', reverse('campaigns:newsroom')),
            ('Story Archive', None),
        ],
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
        _enrich_stories(list(page.object_list))
        context['stories_page'] = page
        context['stories_total'] = paginator.count
        total += paginator.count
    if show_updates:
        paginator = Paginator(update_queryset(params), PAGE_SIZE)
        page = paginator.get_page(request.GET.get('up'))
        for update in page.object_list:
            update.excerpt = make_excerpt(update.body, q)
        _enrich_updates(list(page.object_list))
        context['updates_page'] = page
        context['updates_total'] = paginator.count
        total += paginator.count
    if show_promises:
        paginator = Paginator(promise_queryset(params), PAGE_SIZE)
        page = paginator.get_page(request.GET.get('pp'))
        for promise in page.object_list:
            promise.excerpt = make_excerpt(promise.description, q)
        _enrich_promises(list(page.object_list))
        context['promises_page'] = page
        context['promises_total'] = paginator.count
        total += paginator.count
    context['total_results'] = total

    return render(request, 'story_intelligence/archive.html', context)
