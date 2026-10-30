"""Helpers for the v2.4.4 source-button change.

Before v2.4.4, brain-published articles carried their source as a
trailing plain-text paragraph block ("Source: https://..."), which
renders as dead text. The article now stores source_name/source_url
and the template renders a real link button. `extract_text_source`
pulls that trailing line back out of an existing article's blocks and
plain content so the data migration can convert old articles.
"""
import re
from urllib.parse import urlparse

_SOURCE_BLOCK_RE = re.compile(r'^Source:\s*(https?://\S+)\s*$')
_SOURCE_TAIL_RE = re.compile(r'\n*\s*Source:\s*https?://\S+\s*$')


def source_name_for(item):
    """Best source display name for an editorial Item (or '')."""
    if item is None:
        return ''
    if getattr(item, 'source_id', None) and getattr(item.source, 'name', ''):
        return item.source.name
    original = getattr(item, 'original', None) or {}
    return str(original.get('source_name', '') or '')[:200]


def name_from_url(url):
    host = urlparse(url or '').netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    return host


def extract_text_source(article):
    """Convert an article's trailing text source line into fields.

    Mutates article.content_json/content in memory and returns
    (url, changed). The caller saves. Only the LAST paragraph block is
    considered, and only when it is exactly a "Source: <url>" line.
    """
    url = ''
    changed = False
    data = article.content_json if isinstance(article.content_json, dict) else {}
    blocks = data.get('blocks') if isinstance(data, dict) else None
    if isinstance(blocks, list) and blocks:
        last = blocks[-1]
        if isinstance(last, dict) and last.get('type') == 'paragraph':
            text = str((last.get('data') or {}).get('text', '')).strip()
            match = _SOURCE_BLOCK_RE.match(text)
            if match:
                url = match.group(1)
                blocks.pop()
                changed = True
    if not url and article.content:
        tail = _SOURCE_TAIL_RE.search(article.content)
        if tail:
            found = re.search(r'https?://\S+', tail.group(0))
            if found:
                url = found.group(0)
    if url and article.content:
        cleaned = _SOURCE_TAIL_RE.sub('', article.content).rstrip()
        if cleaned != article.content:
            article.content = cleaned
            changed = True
    return url, changed
