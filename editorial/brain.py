"""The drafting brain for the editorial assistant is Muse, the owner's
external personal agent. There is deliberately NO third-party AI provider,
API key or model call anywhere in this app.

Flow:
  1. The in-site worker discovers sources and runs deterministic maintenance.
     Drafting jobs (kind GENERATE) are left QUEUED for the brain.
  2. `manage.py brain_outbox` exports WAITING items as JSON.
  3. Muse reads the evidence, writes original drafts, and returns them.
  4. `manage.py brain_inbox` imports those drafts through submit_draft(),
     which applies exactly the same field validation, freshness checks and
     audit trail that any drafter is subject to. Nothing is published here:
     imported drafts land in REVIEW for a human decision, like before.
"""
import json
import re
from django.conf import settings
from django.db import transaction
from .models import Audit, Item, Job
from .services import notify_ready, source_current

GENERATE_KINDS = ('NEWS', 'OPPORTUNITY', 'REPORT_EDIT', 'COMMUNITY_EDIT', 'CAPTION')
REPORT_KINDS = ('REPORT_EDIT', 'COMMUNITY_EDIT')

ALLOWED = {
    'NEWS': {'title', 'body', 'category', 'notes'},
    'OPPORTUNITY': {'title', 'body', 'provider', 'category', 'requirements', 'benefits', 'application_link', 'deadline', 'notes'},
    'REPORT_EDIT': {'title', 'content', 'notes'},
    'COMMUNITY_EDIT': {'title', 'what_happened', 'who_was_involved', 'why_is_it_important', 'notes'},
    'CAPTION': {'title', 'body', 'notes'},
}


class BrainError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def redact(text):
    """Remove common contact patterns from report evidence before export."""
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[EMAIL REDACTED]', text)
    return re.sub(r'(?<!\w)(?:\+?234|0)[\d ()-]{9,15}(?!\w)', '[PHONE REDACTED]', text)


def _redacted(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redacted(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redacted(v) for v in value]
    return value


def brain_may_draft(item):
    """Report wording drafts stay off until the owner enables them."""
    if item.kind in REPORT_KINDS:
        return bool(settings.KPN_EDITORIAL_REPORT_DRAFTING_ENABLED)
    return item.kind in GENERATE_KINDS


def waiting_items(limit=20):
    """Serialisable list of WAITING items the brain may draft now."""
    rows = (
        Item.objects.filter(state='WAITING', kind__in=GENERATE_KINDS)
        .select_related('source')
        .order_by('created_at', 'pk')[: max(1, min(int(limit), 100))]
    )
    result = []
    for item in rows:
        if not brain_may_draft(item):
            continue
        original = item.original
        if item.kind in REPORT_KINDS:
            original = _redacted(original)
        result.append({
            'item_id': item.pk,
            'key': item.key,
            'kind': item.kind,
            'title': item.title,
            'version': item.version,
            'source_url': item.source_url,
            'source_name': item.source.name if item.source_id else '',
            'allowed_fields': sorted(ALLOWED[item.kind]),
            'original': original,
        })
    return result


def validate_draft(item, result):
    """The exact drafting rules any brain output must satisfy."""
    if not isinstance(result, dict):
        raise BrainError('invalid_draft_object')
    allowed = ALLOWED[item.kind]
    if set(result) - allowed or any(not isinstance(v, str) or len(v) > 20000 for v in result.values()):
        raise BrainError('invalid_draft_fields')
    required = {'REPORT_EDIT': 'content', 'COMMUNITY_EDIT': 'what_happened'}.get(item.kind, 'body')
    if not result.get(required, '').strip() or not result.get('title', '').strip() or len(result['title']) > 300:
        raise BrainError('missing_draft_content')
    if item.kind == 'OPPORTUNITY' and result.get('application_link'):
        supplied = {link.get('url') for link in item.original.get('application_links', []) if isinstance(link, dict)}
        supplied.add(item.original.get('source_url', ''))
        if result['application_link'] not in supplied:
            raise BrainError('unsupported_application_link')
    if item.kind == 'CAPTION' and len(result.get('body', '')) > 1000:
        raise BrainError('caption_too_long')
    return result


@transaction.atomic
def submit_draft(item_id, result, version):
    """Accept one brain-written draft. Mirrors the worker's old safeguards:
    the item must still be WAITING, at the exported version, and — for
    reports — the underlying report must not have changed since export."""
    item = Item.objects.select_for_update().filter(pk=item_id).first()
    if item is None:
        raise BrainError('item_not_found')
    if item.state != 'WAITING':
        raise BrainError('item_not_waiting')
    if item.version != version:
        raise BrainError('item_changed_reload')
    if not brain_may_draft(item):
        raise BrainError('report_drafting_not_enabled')
    if not source_current(item):
        raise BrainError('stale_report')
    if item.kind == 'CAPTION' and (not item.article_id or item.article.status != 'PUBLISHED'):
        raise BrainError('article_not_published')
    validate_draft(item, result)
    item.draft = result
    item.title = result['title']
    item.state = 'REVIEW'
    item.version += 1
    item.save()
    Job.objects.filter(item=item, kind='GENERATE', state__in=['QUEUED', 'BLOCKED']).update(state='DONE', error_code='')
    Audit.objects.create(item=item, action='CLAUDE_DRAFT_READY', detail={'brain': 'claude-external-agent'})
    notify_ready(item)
    return item


def submit_candidate(payload):
    """Register a story/opportunity that Muse found outside the site's own
    sources (news sites, Facebook/social posts, official pages), together
    with Muse's draft. The item is created from the supplied evidence and
    the draft passes through the exact same validation as submit_draft, so
    it lands in human REVIEW — never published, never handed off.

    payload = {kind: 'NEWS'|'OPPORTUNITY', title, source_url, source_name,
               text, draft: {...}}
    Duplicate source URLs are rejected.
    """
    import hashlib

    from .fetch import canonical

    if not isinstance(payload, dict):
        raise BrainError('malformed_candidate')
    kind = payload.get('kind')
    if kind not in ('NEWS', 'OPPORTUNITY'):
        raise BrainError('kind_not_allowed')
    title = payload.get('title')
    text = payload.get('text')
    if not isinstance(title, str) or not title.strip() or len(title) > 300:
        raise BrainError('invalid_title')
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise BrainError('invalid_evidence')
    try:
        url = canonical(str(payload.get('source_url', '')))
    except Exception:
        raise BrainError('invalid_source_url')
    if not url:
        raise BrainError('invalid_source_url')
    key = 'brain:' + hashlib.sha256(url.encode()).hexdigest()[:40]
    if Item.objects.filter(key=key).exists():
        raise BrainError('duplicate_candidate')
    original = {
        'title': title.strip(),
        'text': text,
        'source_url': url,
        'source_name': str(payload.get('source_name', ''))[:200],
        'links': [url],
        'found_by': 'claude-external-search',
    }
    with transaction.atomic():
        item = Item.objects.create(key=key, kind=kind, title=title.strip(), original=original)
        return submit_draft(item.pk, payload.get('draft'), item.version)
