"""Source connectors for the collection engine (Phase 2).

Each connector is a small adapter behind one interface —
``collect(source) -> int``, returning the number of NEW raw items it
stored — built entirely on the editorial fetcher chassis:
``permitted_fetch`` (HTTPS only, allowlisted hosts, robots.txt
respected, public-IP pinning, 1 MB cap) and the ``discovery`` parsers.
There is no second fetcher here and no connector weakens a chassis
safety property.

Items land as :class:`intelligence.models.RawPublication` intake rows
only. Nothing in this module classifies, clusters or publishes:
geographic relevance is Phase 3 and the verification workflow is
Phase 4. The editorial keyword filter is deliberately NOT applied —
intake is source-driven and relevance is a separate, later engine
(Doc 03 §2.1–2.3); per-source ``max_items`` caps the volume.
"""
import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from django.utils import timezone

from editorial.discovery import entries, is_old
from editorial.fetch import (
    FetchError, Readable, canonical, hosts_for, permitted_fetch, readable,
)

from .models import RawPublication

MAX_TEXT_CHARS = 24000  # matches editorial.fetch.readable()'s own cap


def parse_date(value):
    """Best-effort parse of a feed/page date string; None when unusable."""
    if not value:
        return None
    try:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError, OverflowError):
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _fingerprint(title, text):
    normalised = ' '.join(f'{title} {text}'.split()).casefold()
    return hashlib.sha256(normalised.encode('utf-8')).hexdigest()


def _already_stored(source, canonical_url):
    return RawPublication.objects.filter(
        source=source, canonical_url=canonical_url).exists()


def _store(source, *, original_url, canonical_url, title, summary, text,
           published_at, fetch_status, metadata=None):
    """Create one raw item; False when its canonical URL is already stored."""
    if _already_stored(source, canonical_url):
        return False
    RawPublication.objects.create(
        source=source, canonical_url=canonical_url, original_url=original_url,
        title=(title or source.name)[:300], summary=(summary or '')[:3000],
        text=(text or '')[:MAX_TEXT_CHARS], published_at=published_at,
        fetch_status=fetch_status,
        content_fingerprint=_fingerprint(title or '', text or summary or ''),
        raw_metadata=metadata or {})
    return True


def collect_feed(source):
    """RSS/Atom connector: poll the feed, store new entries as raw items.

    The feed itself is fetched through the chassis; each fresh entry's
    article page is then fetched for full text. When the article fetch
    fails (robots, HTTP error, oversize), the feed's own title/summary
    is still stored, marked FEED_ONLY — the lead is intake either way.
    Entries whose own date is more than 3 days old are dropped by the
    chassis age rule (``discovery.is_old``).
    """
    allowed = hosts_for(source)
    body, final_url = permitted_fetch(source.url, allowed)
    stored = 0
    for entry in entries(body, final_url, feed=True):
        if stored >= source.max_items:
            break
        if is_old(entry['date']):
            continue
        try:
            url = canonical(entry['url'])
        except FetchError:
            continue
        if _already_stored(source, url):
            continue
        text, status, original = '', 'FEED_ONLY', entry['url']
        try:
            article_body, article_url = permitted_fetch(url, allowed)
            text = readable(article_body)
            status, original = 'CONTENT', article_url
        except FetchError:
            pass
        if _store(source, original_url=original, canonical_url=url,
                  title=entry['title'], summary=entry['summary'], text=text,
                  published_at=parse_date(entry['date']), fetch_status=status,
                  metadata={'feed_date': entry['date']}):
            stored += 1
    return stored


_DATE_PATTERNS = [
    re.compile(r'property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)', re.I),
    re.compile(r'content=["\']([^"\']+)["\'][^>]*property=["\']article:published_time["\']', re.I),
    re.compile(r'["\']datePublished["\']\s*:\s*["\']([^"\']+)', re.I),
    re.compile(r'<time[^>]+datetime=["\']([^"\']+)', re.I),
]


def extract_published(body):
    """An article page's own publication date string, when it declares one."""
    text = body.decode('utf-8', errors='replace')
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ''


def _listing_links(body, base, allowed, listing_url):
    """Article candidates linked from a listing page (allowlisted hosts only)."""
    parser = Readable()
    parser.feed(body.decode('utf-8', errors='replace'))
    seen, links = set(), []
    for link in parser.links:
        href = (link.get('url') or '').strip()
        if not href or href.startswith(('#', 'mailto:', 'javascript:')):
            continue
        try:
            url = canonical(urljoin(base, href))
        except (FetchError, ValueError):
            continue
        if urlsplit(url).hostname not in allowed:
            continue
        if url == listing_url or url in seen:
            continue
        if urlsplit(url).path in ('', '/'):
            continue  # the site root is a navigation target, not an item
        seen.add(url)
        links.append(url)
    return links


def collect_page(source):
    """Monitored-page connector (news pages and official pages).

    A listing page (for example the Kebbi State Government Pressroom)
    yields its article links: each is fetched through the chassis,
    checked against its own declared publication date — a listing
    mixes current with years-old items, so listing order is never
    treated as recency (Doc 05 §C) — and stored. A page with no
    outgoing article links is stored as a single item, matching the
    editorial chassis' page behaviour. One bad link never fails the
    source: it is skipped and the remaining links are still collected.
    """
    allowed = hosts_for(source)
    body, final_url = permitted_fetch(source.url, allowed)
    listing_url = canonical(final_url)
    candidates = _listing_links(body, final_url, allowed, listing_url)
    if not candidates:
        candidates = [listing_url]
    stored = 0
    for url in candidates:
        if stored >= source.max_items:
            break
        if _already_stored(source, url):
            continue
        try:
            if url == listing_url:
                article_body, article_final = body, final_url
            else:
                article_body, article_final = permitted_fetch(url, allowed)
        except FetchError:
            continue
        date_text = extract_published(article_body)
        if is_old(date_text):
            continue
        entry = entries(article_body, article_final, feed=False)[0]
        if _store(source, original_url=article_final, canonical_url=url,
                  title=entry['title'], summary=entry['summary'],
                  text=readable(article_body),
                  published_at=parse_date(date_text), fetch_status='CONTENT',
                  metadata={'page_date': date_text}):
            stored += 1
    return stored


# connector_kind -> collect(source) -> int (new items stored).
# YOUTUBE_CHANNEL has no connector until a Data API key exists
# (Doc 05 §I); MANUAL sources are desk submissions, never polled.
CONNECTORS = {
    'RSS': collect_feed,
    'PAGE': collect_page,
    'OFFICIAL_PAGE': collect_page,
}
