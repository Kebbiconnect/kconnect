"""Direct publishing for Muse's brain items (owner decision 2026-10-30).

Until v2.3 every brain draft landed in human REVIEW and only a person could
hand it off. Nasiru, the Director of Media, changed that rule: when
KPN_EDITORIAL_AUTO_PUBLISH is on, a validated brain draft is published
immediately (NEWS -> Campaign PUBLISHED, OPPORTUNITY -> Opportunity OPEN),
because scheduled runs happen while he is away and review delays made
time-sensitive posts late. He corrects published items afterwards with the
newsroom edit/delete tools, which v2.4 also opens to editors for published
articles.

Safeguards that remain:
- Only items whose draft passed editorial.brain.validate_draft can publish.
- Synthetic test items can never publish.
- Opportunities re-check provider, real backend category, a canonical
  HTTPS application link taken from the evidence, and a future ISO
  deadline, exactly like the human handoff did.
- Authorship is a system pick: the verified Director of Media user (the
  owner), falling back to a verified editor, then a superuser. Public
  pages never show that person: they show only the reporter credit
  ("KPN Editorial Team").
- An image problem never blocks the story: the article publishes without
  the image and the failure is reported back in the result/audit.
"""
import base64
import binascii
import io
import re
from datetime import date
from difflib import SequenceMatcher

import requests

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from .brain import BrainError, resolve_lga, validate_draft
from .fetch import FetchError, canonical
from .models import Audit, Job
from .services import unique_slug

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}


def auto_publish_enabled():
    return bool(getattr(settings, 'KPN_EDITORIAL_AUTO_PUBLISH', False))


def _norm_title(value):
    return ' '.join(re.findall(r'\w+', (value or '').casefold()))


def _norm_link(value):
    return (value or '').strip().rstrip('/').casefold()


def duplicate_conflict(kind, title, application_link='', exclude_item_pk=None):
    """Duplicate guard (owner request 2026-10-30: never publish the same
    story or opportunity twice). Returns (level, match_title):
    - 'exact': the same item is already live or already tracked — an
      identical normalised title, a title that is almost identical
      (>= 0.92 similar), or, for opportunities, the same application link.
    - 'possible': a very similar title exists (0.85-0.92) — too close to
      publish blind, but a human should decide.
    - '': no conflict found.
    Checks published articles / hub opportunities AND other editorial
    items of the same kind, so the same story arriving from two different
    sources (different URLs) is still caught."""
    from campaigns.models import Campaign
    from core.models import Opportunity
    from .models import Item

    clean = _norm_title(title)
    if len(clean) < 12:
        return '', ''
    best = ('', '', 0.0)

    def consider(match_title):
        nonlocal best
        other = _norm_title(match_title)
        if not other:
            return
        if other == clean:
            best = ('exact', match_title, 1.0)
            return
        ratio = SequenceMatcher(None, clean, other).ratio()
        if ratio > best[2]:
            best = ('exact' if ratio >= 0.92 else 'possible' if ratio >= 0.85 else '', match_title, ratio)

    if kind in ('NEWS', 'SIGNAL'):
        for t in Campaign.objects.order_by('-created_at').values_list('title', flat=True)[:300]:
            consider(t)
            if best[0] == 'exact':
                return best[0], best[1]
    elif kind == 'VOICE':
        # A quote post is identified by its source post URL (the item
        # key already blocks the same URL twice); there is no public
        # title list to scan — the tracked-items check below applies.
        pass
    else:
        link = _norm_link(application_link)
        rows = Opportunity.objects.order_by('-created_at').values('title', 'application_link')[:300]
        for row in rows:
            if link and _norm_link(row['application_link']) == link:
                return 'exact', row['title']
            consider(row['title'])
            if best[0] == 'exact':
                return best[0], best[1]
    # Only items that already carry a draft (REVIEW) or are live
    # (HANDED_OFF) count: a merely WAITING item must not block this one —
    # it will itself be caught by the article/hub check when its turn comes.
    items = Item.objects.filter(kind=kind, state__in=('REVIEW', 'HANDED_OFF'))
    if exclude_item_pk:
        items = items.exclude(pk=exclude_item_pk)
    for t in items.order_by('-created_at').values_list('title', flat=True)[:300]:
        consider(t)
        if best[0] == 'exact':
            return best[0], best[1]
    return (best[0], best[1]) if best[0] else ('', '')


def publishing_author():
    """The staff user brain-published articles are filed under."""
    from staff.models import User
    base = User.objects.filter(is_active=True, status='VERIFIED')
    for title in ('Director of Media & Communications',
                  'Assistant Director of Media & Communications',
                  'President', 'General Secretary'):
        user = base.filter(role_definition__title=title).order_by('pk').first()
        if user:
            return user
    return User.objects.filter(is_superuser=True, is_active=True).order_by('pk').first()


def _image_bytes(draft):
    """Return (bytes, warning) for the draft's image, or (None, warning)."""
    encoded = (draft.get('image_base64') or '').strip()
    if encoded:
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return None, 'image_base64_undecodable'
        return _checked_image(raw)
    url = (draft.get('image_url') or '').strip()
    if url:
        try:
            response = requests.get(url, timeout=20, headers={
                'User-Agent': 'KPN-Editorial/2.4 (+https://kpn.com.ng)'})
            response.raise_for_status()
        except Exception:
            return None, 'image_download_failed'
        return _checked_image(response.content)
    return None, ''


def _checked_image(raw):
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None, 'image_too_large'
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(raw))
        image.verify()
        fmt = (image.format or '').upper()
    except Exception:
        return None, 'image_invalid'
    if fmt not in IMAGE_EXTENSIONS:
        return None, 'image_format_not_supported'
    return (raw, fmt), ''


def _attach_image(article, draft):
    """Attach the draft image as the article's featured image.

    Returns a warning code ('' when attached or no image was supplied)."""
    found, warning = _image_bytes(draft)
    if found is None:
        return warning
    raw, fmt = found
    from django.core.files.base import ContentFile
    name = f'{article.slug}.{IMAGE_EXTENSIONS[fmt]}'
    article.featured_image.save(name, ContentFile(raw), save=True)
    return ''


@transaction.atomic
def publish_brain_item(item, overrides=None):
    """Publish one REVIEW brain item now. Returns a result dict:
    {published: True, kind, slug, url_path, image_warning} on success.
    Raises BrainError with a stable code when it cannot publish; the item
    is then left untouched in REVIEW so it can be fixed and retried."""
    if item.kind not in ('NEWS', 'OPPORTUNITY', 'SIGNAL', 'VOICE'):
        raise BrainError('kind_not_publishable')
    if item.state not in ('REVIEW', 'WAITING'):
        raise BrainError('item_not_publishable_state')
    if item.original.get('synthetic'):
        raise BrainError('synthetic_not_publishable')
    draft = dict(item.draft or {})
    if overrides:
        if not isinstance(overrides, dict):
            raise BrainError('invalid_overrides')
        draft.update(overrides)
    if not draft.get('title') or not draft.get('body'):
        raise BrainError('missing_draft_content')
    # Re-validate the (possibly corrected) draft with the same rules the
    # brain had to pass: real backend category, ISO future deadline, etc.
    validate_draft(item, draft)

    # Duplicate guard: never publish the same story/opportunity twice.
    level, match = duplicate_conflict(
        item.kind, draft['title'],
        application_link=draft.get('application_link', ''),
        exclude_item_pk=item.pk)
    if level == 'exact':
        item.state = 'DISMISSED'
        item.version += 1
        item.save()
        Audit.objects.create(item=item, action='CLAUDE_DUPLICATE_DISMISSED',
                             detail={'kind': item.kind, 'duplicate_of': match})
        return {'published': False, 'duplicate': True, 'duplicate_of': match}
    if level == 'possible':
        raise BrainError('possible_duplicate')

    if item.kind == 'NEWS':
        author = publishing_author()
        if author is None:
            raise BrainError('no_publishing_author')
        from campaigns.models import Campaign
        from campaigns.source_backfill import name_from_url, source_name_for
        paragraphs = [p.strip() for p in draft['body'].split('\n') if p.strip()]
        source_url = (item.source_url or item.original.get('source_url', '') or '')[:500]
        source_line = f'Source: {source_url}'.strip()
        # v2.4.4: the source is stored in dedicated fields and rendered
        # as a link BUTTON on the article page — no more dead text line
        # inside the article blocks. The plain-text `content` fallback
        # keeps the text line for non-HTML surfaces.
        blocks = [{'type': 'paragraph', 'data': {'text': str(escape(p))}} for p in paragraphs]
        article = Campaign.objects.create(
            author=author, title=draft['title'],
            slug=unique_slug(Campaign, draft['title']),
            content=str(escape(draft['body'])) + ('\n\n' + str(escape(source_line)) if source_url else ''),
            content_json={'blocks': blocks},
            category=draft.get('category', 'GENERAL'),
            # LGA tagging (owner, 27 Nov 2026): the article's own lga
            # field is mirrored to an ArticleLocation row by the save
            # signal, so the story appears on that LGA's news page.
            lga=resolve_lga(draft.get('lga', '')),
            status='PUBLISHED', published_at=timezone.now(),
            approved_by=author, verification_status='DEVELOPING',
            reporter_credit='KPN_EDITORIAL',
            source_url=source_url,
            source_name=(source_name_for(item) or name_from_url(source_url)) if source_url else '',
            meta_description=_excerpt(draft['body']))
        # KPN Media Phase 1: every published article carries a permanent
        # Story ID. Allocation runs inside this publish transaction; if
        # it fails, the whole publish rolls back and the item stays in
        # REVIEW, recoverable — the caller sees a stable error code.
        # KPN Media Phase 4: the Human Impact consent guard runs in the
        # same transaction, before allocation; a blocked publish rolls
        # back identically and the item stays in REVIEW.
        from story_intelligence.services import (
            ConsentRequiredError, allocate_story_id,
            ensure_consent_for_publish)
        try:
            ensure_consent_for_publish(article)
        except ConsentRequiredError:
            raise BrainError('consent_required')
        try:
            allocate_story_id(article)
            article.save(update_fields=['story_id'])
        except Exception:
            raise BrainError('story_id_allocation_failed')
        item.article = article
        result = {'published': True, 'kind': 'NEWS', 'slug': article.slug,
                  'url_path': f'/campaigns/article/{article.slug}/',
                  'image_warning': _attach_image(article, draft)}
        # Owner (27 Nov 2026): all members get an app notification when
        # a new story is posted.
        from core.notifications import notify_all_members
        transaction.on_commit(lambda aid=article.pk, title=article.title, slug=article.slug: notify_all_members(
            'NEW_ARTICLE', 'New story on KPN', title,
            link=f'/campaigns/article/{slug}/', target_type='article', target_id=aid))
    elif item.kind == 'SIGNAL':
        author = publishing_author()
        if author is None:
            raise BrainError('no_publishing_author')
        from campaigns.models import Campaign
        from campaigns.source_backfill import name_from_url, source_name_for
        paragraphs = [p.strip() for p in draft['body'].split('\n') if p.strip()]
        source_url = (item.source_url or item.original.get('source_url', '') or '')[:500]
        source_line = f'Source: {source_url}'.strip()
        blocks = [{'type': 'paragraph', 'data': {'text': str(escape(p))}} for p in paragraphs]
        article = Campaign.objects.create(
            author=author, title=draft['title'],
            slug=unique_slug(Campaign, draft['title']),
            content=str(escape(draft['body'])) + ('\n\n' + str(escape(source_line)) if source_url else ''),
            content_json={'blocks': blocks},
            category=draft.get('category', 'GENERAL'),
            lga=resolve_lga(draft.get('lga', '')),
            status='PUBLISHED', published_at=timezone.now(),
            approved_by=author, verification_status='DEVELOPING',
            reporter_credit='KPN_EDITORIAL',
            source_url=source_url,
            source_name=(source_name_for(item) or name_from_url(source_url)) if source_url else '',
            meta_description=_excerpt(draft['body']))
        from story_intelligence.services import (
            ConsentRequiredError, allocate_story_id,
            ensure_consent_for_publish)
        try:
            ensure_consent_for_publish(article)
        except ConsentRequiredError:
            raise BrainError('consent_required')
        try:
            allocate_story_id(article)
            article.save(update_fields=['story_id'])
        except Exception:
            raise BrainError('story_id_allocation_failed')
        # Future Signal framing: the story profile carries the analysis
        # fields, kept separate from the article body so the public
        # page never blends observation, evidence and judgment.
        from story_intelligence.models import StoryProfile
        profile, _created = StoryProfile.objects.get_or_create(article=article)
        profile.kind = 'SIGNAL'
        profile.signal_observation = draft.get('signal_observation', '')
        profile.signal_category = draft.get('signal_category', '')
        profile.signal_confidence = draft.get('signal_confidence', '')
        profile.signal_horizon = draft.get('signal_horizon', '')
        profile.signal_change_condition = draft.get('signal_change_condition', '')
        profile.why_it_matters = draft.get('why_it_matters', '')
        profile.who_is_affected = draft.get('who_is_affected', '')
        profile.what_is_unknown = draft.get('what_is_unknown', '')
        profile.what_to_watch = draft.get('what_to_watch', '')
        profile.save()
        item.article = article
        # The web Future Signal surface is the hub at /signals/ (there
        # is no per-signal web detail page; the app reads the API
        # detail), so the reported path is the hub.
        result = {'published': True, 'kind': 'SIGNAL', 'slug': article.slug,
                  'url_path': '/signals/',
                  'image_warning': _attach_image(article, draft)}
        from core.notifications import notify_all_members
        transaction.on_commit(lambda aid=article.pk, title=article.title: notify_all_members(
            'NEW_SIGNAL', 'New Future Signal analysis', title,
            link='/signals/', target_type='article', target_id=aid))
    elif item.kind == 'VOICE':
        # Community Voice quote (owner, 27 Nov 2026): a Kebbi resident's
        # own public words, amplified with the screenshot of their post
        # as the evidence image. The reviewer decision the page requires
        # (published_to_voice) is the brain's validated submission
        # itself, under the owner's standing auto-publish rule.
        from core.models import CommunityReport
        from django.core.files.base import ContentFile

        author_name = draft.get('author', '').strip()[:100]
        platform = draft.get('platform', '').strip().upper()
        source_url = item.source_url or item.original.get('source_url', '')
        lga = resolve_lga(draft.get('lga', ''))
        report = CommunityReport.objects.create(
            reporter_name=author_name or 'Community member',
            reporter_phone='',
            location_details=draft.get('location_details', '')[:200],
            category=draft.get('category', 'COMMUNITY'),
            what_happened=draft['body'],
            who_was_involved=f'{author_name} on {platform.title()}' if author_name else '',
            why_is_it_important=draft.get('why_it_matters', ''),
            lga=lga,
            zone=lga.zone if lga else None,
            status='APPROVED',
            info_status='CONFIRMED',
            internal_notes=(
                f'Community Voice quote amplified by KPN. Original post: {source_url}'
                + (f"\n{draft.get('notes', '')}" if draft.get('notes') else '')),
            published_to_voice=True,
            voice_published_at=timezone.now())
        image_warning = ''
        found, image_warning = _image_bytes(draft)
        if found is not None:
            raw, fmt = found
            report.evidence_image.save(
                f'voice-{report.pk}.{IMAGE_EXTENSIONS[fmt]}', ContentFile(raw), save=True)
        result = {'published': True, 'kind': 'VOICE', 'slug': f'voice-{report.pk}',
                  'url_path': '/civic/community-voice/',
                  'image_warning': image_warning}
    else:
        from core.models import Opportunity
        try:
            link = canonical(draft.get('application_link', ''))
        except (FetchError, ValueError):
            raise BrainError('invalid_application_link')
        if len(link) > 200:
            raise BrainError('application_link_too_long')
        deadline = None
        if draft.get('deadline', '').strip():
            deadline = date.fromisoformat(draft['deadline'].strip())
        source_url = item.source_url or item.original.get('source_url', '')
        opportunity = Opportunity.objects.create(
            title=draft['title'], slug=unique_slug(Opportunity, draft['title']),
            category=draft['category'], provider=draft['provider'][:200],
            description=draft['body'] + ('\n\nSource: ' + source_url if source_url else ''),
            requirements=draft.get('requirements', ''),
            benefits=draft.get('benefits', ''),
            application_link=link, deadline=deadline, status='OPEN')
        item.opportunity = opportunity
        result = {'published': True, 'kind': 'OPPORTUNITY', 'slug': opportunity.slug,
                  'url_path': '/opportunities/',
                  'image_warning': ''}
        # Owner (27 Nov 2026): all members get an app notification when
        # a new opportunity is posted.
        from core.notifications import notify_all_members
        transaction.on_commit(lambda oid=opportunity.pk, title=opportunity.title, slug=opportunity.slug: notify_all_members(
            'NEW_OPPORTUNITY', 'New opportunity on KPN', title,
            link=f'/opportunities/{slug}/', target_type='opportunity', target_id=oid))

    item.draft = draft
    item.title = draft['title']
    item.state = 'HANDED_OFF'
    item.version += 1
    item.save()
    Job.objects.filter(item=item, state__in=['QUEUED', 'BLOCKED']).update(state='DONE', error_code='')
    Audit.objects.create(item=item, action='CLAUDE_AUTO_PUBLISHED',
                         detail={'kind': item.kind, 'slug': result['slug'],
                                 'image_warning': result['image_warning']})
    return result


def _excerpt(body, limit=160):
    text = ' '.join((body or '').split())
    return text[:limit]


def maybe_auto_publish(item):
    """Publish a freshly drafted brain item when the owner has enabled
    auto-publish. Returns the publish result dict, or None when disabled.
    A publish failure never loses the draft: the item stays in REVIEW and
    the failure code is returned under 'publish_error'."""
    if not auto_publish_enabled() or item.kind not in ('NEWS', 'OPPORTUNITY', 'SIGNAL', 'VOICE'):
        return None
    try:
        return publish_brain_item(item)
    except BrainError as exc:
        Audit.objects.create(item=item, action='CLAUDE_AUTO_PUBLISH_FAILED',
                             detail={'code': exc.code})
        return {'published': False, 'publish_error': exc.code}
