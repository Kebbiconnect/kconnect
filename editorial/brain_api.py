"""Token-gated Brain API: how Muse, the owner's external automation agent,
connects to this site directly.

Endpoints, all under /editorial/brain/:

- GET  outbox/       -> WAITING items as JSON (same payload as brain_outbox)
- POST inbox/        -> [{item_id, version, draft}] -> per-item accept/reject
- POST submit-item/  -> a story/opportunity Muse found, with its draft
- POST publish-item/ -> publish one REVIEW item now, with optional draft
                        corrections ({item_id, draft_overrides})
- POST test-item/    -> create one private synthetic WAITING item (loop test)
- telegram-*         -> bot control (see the telegram views below)

Security contract:
- Requires the KPN_EDITORIAL_BRAIN_TOKEN setting (a long random secret the
  owner sets on the server and shares with Muse through secure storage
  only). When no token is configured the endpoints do not exist (404).
- Wrong or missing token -> 401. Comparison is constant-time.
- Drafts pass through exactly the same validation as the management
  commands (editorial.brain.submit_draft).

Publishing (changed in v2.4 at the owner's explicit request, 2026-10-30):
when KPN_EDITORIAL_AUTO_PUBLISH is on, validated NEWS/OPPORTUNITY brain
drafts publish immediately on submission, and publish-item can publish or
repair a REVIEW item. When the flag is off, drafts only ever reach REVIEW
and publish-item refuses. Synthetic items can never publish either way.
"""
import hmac
import json
import uuid

from django.conf import settings
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .brain import BrainError, submit_candidate, submit_draft, waiting_items
from .models import Audit, Item, Job

MAX_BODY_BYTES = 1_000_000
# submit-item / publish-item may carry a base64 featured image for a story.
MAX_SUBMIT_BYTES = 9_000_000
MAX_ENTRIES = 50


def _gate(request):
    """Return an error response, or None when the caller may proceed."""
    token = getattr(settings, 'KPN_EDITORIAL_BRAIN_TOKEN', '') or ''
    if not token:
        return HttpResponseNotFound()
    header = request.META.get('HTTP_AUTHORIZATION', '')
    supplied = header[7:].strip() if header.startswith('Bearer ') else ''
    if not supplied or not hmac.compare_digest(supplied, token):
        return JsonResponse({'error': 'unauthorised'}, status=401)
    if not settings.KPN_EDITORIAL_ENABLED:
        return JsonResponse({'error': 'editorial_disabled'}, status=503)
    return None


@csrf_exempt
@require_GET
def outbox(request):
    blocked = _gate(request)
    if blocked:
        return blocked
    try:
        limit = min(max(int(request.GET.get('limit', 20)), 1), MAX_ENTRIES)
    except (TypeError, ValueError):
        limit = 20
    items = waiting_items(limit)
    Audit.objects.create(action='BRAIN_OUTBOX_READ', detail={'count': len(items)})
    return JsonResponse({'items': items})


@csrf_exempt
@require_POST
def inbox(request):
    blocked = _gate(request)
    if blocked:
        return blocked
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({'error': 'payload_too_large'}, status=413)
    try:
        entries = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid_json'}, status=400)
    if not isinstance(entries, list):
        return JsonResponse({'error': 'expected_a_json_list'}, status=400)
    results = []
    for entry in entries[:MAX_ENTRIES]:
        if not isinstance(entry, dict):
            results.append({'item_id': None, 'status': 'rejected', 'code': 'malformed'})
            continue
        try:
            item = submit_draft(int(entry['item_id']), entry['draft'], int(entry['version']))
            row = {'item_id': item.pk, 'status': 'accepted',
                   'state': item.state, 'version': item.version}
            publish_result = getattr(item, '_publish_result', None)
            if publish_result:
                row.update(publish_result)
            results.append(row)
        except (KeyError, TypeError, ValueError):
            results.append({'item_id': entry.get('item_id'), 'status': 'rejected', 'code': 'malformed'})
        except BrainError as exc:
            results.append({'item_id': entry.get('item_id'), 'status': 'rejected', 'code': exc.code})
    accepted = sum(1 for row in results if row['status'] == 'accepted')
    Audit.objects.create(action='BRAIN_INBOX_WRITE',
                         detail={'accepted': accepted, 'rejected': len(results) - accepted})
    return JsonResponse({'results': results})


@csrf_exempt
@require_POST
def submit_item(request):
    """Register a story/opportunity Muse found by its own searching
    (news sites, Facebook/social, official pages) with its draft attached.
    Lands in human REVIEW, or publishes immediately when the owner has
    enabled KPN_EDITORIAL_AUTO_PUBLISH; duplicates by source URL are
    rejected."""
    blocked = _gate(request)
    if blocked:
        return blocked
    if len(request.body) > MAX_SUBMIT_BYTES:
        return JsonResponse({'error': 'payload_too_large'}, status=413)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid_json'}, status=400)
    try:
        item = submit_candidate(payload)
    except BrainError as exc:
        return JsonResponse({'status': 'rejected', 'code': exc.code}, status=400)
    body = {'item_id': item.pk, 'status': 'accepted',
            'state': item.state, 'version': item.version}
    publish_result = getattr(item, '_publish_result', None)
    if publish_result:
        body.update(publish_result)
    return JsonResponse(body, status=201)


@csrf_exempt
@require_POST
def publish_item(request):
    """Publish one REVIEW brain item now (owner-enabled auto-publish only).

    Body: {item_id, draft_overrides?} — overrides are merged into the
    stored draft and re-validated before publishing, which is how a stuck
    item is repaired (e.g. a wrong category or a free-text deadline from
    an older draft) without database access. When auto-publish is off
    this endpoint refuses: human REVIEW remains the only path."""
    blocked = _gate(request)
    if blocked:
        return blocked
    if not getattr(settings, 'KPN_EDITORIAL_AUTO_PUBLISH', False):
        return JsonResponse({'error': 'auto_publish_disabled'}, status=403)
    if len(request.body) > MAX_SUBMIT_BYTES:
        return JsonResponse({'error': 'payload_too_large'}, status=413)
    try:
        payload = json.loads(request.body.decode('utf-8'))
        item = Item.objects.get(pk=int(payload['item_id']))
    except (ValueError, UnicodeDecodeError, KeyError, TypeError, Item.DoesNotExist):
        return JsonResponse({'error': 'item_not_found'}, status=404)
    from .publish import publish_brain_item
    try:
        result = publish_brain_item(item, overrides=payload.get('draft_overrides') or None)
    except BrainError as exc:
        return JsonResponse({'status': 'rejected', 'code': exc.code}, status=400)
    if result.get('duplicate'):
        # Already live: the item was dismissed as a duplicate, nothing to fix.
        return JsonResponse({'item_id': item.pk, 'state': item.state, **result}, status=200)
    Audit.objects.create(item=item, action='BRAIN_PUBLISH_ITEM',
                         detail={'slug': result.get('slug', '')})
    return JsonResponse({'item_id': item.pk, 'state': item.state, **result}, status=201)


@csrf_exempt
@require_GET
def published(request):
    """What is already live / already tracked, so Muse can check BEFORE
    submitting and never repeat a story or opportunity: recent published
    articles, open opportunities, and brain items that carry drafts."""
    blocked = _gate(request)
    if blocked:
        return blocked
    from campaigns.models import Campaign
    from core.models import Opportunity
    articles = [{'title': a.title, 'slug': a.slug,
                 'url_path': f'/campaigns/article/{a.slug}/'}
                for a in Campaign.objects.filter(status='PUBLISHED')
                .order_by('-published_at', '-created_at')[:100]]
    opportunities = [{'title': o.title, 'slug': o.slug,
                      'application_link': o.application_link,
                      'deadline': o.deadline.isoformat() if o.deadline else ''}
                     for o in Opportunity.objects.exclude(status='CLOSED')
                     .order_by('-created_at')[:100]]
    items = [{'item_id': i.pk, 'kind': i.kind, 'title': i.title,
              'source_url': i.source_url, 'state': i.state}
             for i in Item.objects.filter(kind__in=('NEWS', 'OPPORTUNITY'),
                                          state__in=('REVIEW', 'HANDED_OFF'))
             .order_by('-created_at')[:100]]
    return JsonResponse({'articles': articles, 'opportunities': opportunities,
                         'brain_items': items})


@csrf_exempt
@require_POST
def telegram_kb(request):
    """Propose Telegram bot knowledge-base entries written by Muse.
    Entries are created INACTIVE: the owner reviews and activates them in
    the Django admin, and only then can the bot read them."""
    blocked = _gate(request)
    if blocked:
        return blocked
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({'error': 'payload_too_large'}, status=413)
    try:
        payload = json.loads(request.body.decode('utf-8'))
        entries = payload['entries']
    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        return JsonResponse({'error': 'invalid_payload'}, status=400)
    if not isinstance(entries, list) or not entries or len(entries) > 20:
        return JsonResponse({'error': 'expected_1_to_20_entries'}, status=400)
    from telegram_integration.models import BotKnowledgeBase
    created = []
    for entry in entries:
        if not isinstance(entry, dict):
            return JsonResponse({'error': 'malformed_entry'}, status=400)
        topic = str(entry.get('topic', '')).strip()
        content = str(entry.get('content', '')).strip()
        if not topic or len(topic) > 200 or not content or len(content) > 20000:
            return JsonResponse({'error': 'malformed_entry'}, status=400)
        row = BotKnowledgeBase.objects.create(topic=topic, content=content, is_active=False)
        created.append(row.pk)
    Audit.objects.create(action='BRAIN_KB_PROPOSED', detail={'entries': created})
    return JsonResponse({'created_inactive': created}, status=201)


def _json_body(request):
    if len(request.body) > MAX_BODY_BYTES:
        return None, JsonResponse({'error': 'payload_too_large'}, status=413)
    try:
        return json.loads(request.body.decode('utf-8')), None
    except (ValueError, UnicodeDecodeError):
        return None, JsonResponse({'error': 'invalid_json'}, status=400)


@csrf_exempt
@require_POST
def telegram_post(request):
    """Post an announcement (or custom message) to the KPN Telegram
    channel through the bot, on Muse's instruction. Recorded in the
    bot outbox and the audit log before it is sent."""
    blocked = _gate(request)
    if blocked:
        return blocked
    payload, error = _json_body(request)
    if error:
        return error
    text = str(payload.get('text', '')).strip() if isinstance(payload, dict) else ''
    if not text or len(text) > 4000:
        return JsonResponse({'error': 'text_required_max_4000'}, status=400)
    from telegram_integration.brain_service import enqueue_announcement, send_outbox_row
    row = enqueue_announcement(text, chat_id=str(payload.get('chat_id', ''))[:64])
    sent = send_outbox_row(row)
    Audit.objects.create(action='BRAIN_TELEGRAM_POST',
                         detail={'outbox_id': row.pk, 'state': row.state})
    return JsonResponse({'outbox_id': row.pk, 'sent': sent, 'state': row.state,
                         'telegram_message_id': row.telegram_message_id},
                        status=201 if sent else 502)


@csrf_exempt
@require_GET
def telegram_outbox(request):
    """Recent bot outbox rows, so Muse can verify what was delivered."""
    blocked = _gate(request)
    if blocked:
        return blocked
    from telegram_integration.models import BotOutbox
    rows = [{'id': r.pk, 'kind': r.kind, 'state': r.state, 'chat_id': r.chat_id,
             'telegram_message_id': r.telegram_message_id, 'error': r.error,
             'created_at': r.created_at.isoformat()}
            for r in BotOutbox.objects.all()[:30]]
    return JsonResponse({'outbox': rows})


@csrf_exempt
@require_POST
def telegram_drain(request):
    """Send any queued outbox rows (e.g. article shares queued while the
    web process could not reach Telegram)."""
    blocked = _gate(request)
    if blocked:
        return blocked
    from telegram_integration.brain_service import drain_outbox
    result = drain_outbox()
    Audit.objects.create(action='BRAIN_TELEGRAM_DRAIN', detail=result)
    return JsonResponse(result)


@csrf_exempt
@require_GET
def telegram_questions(request):
    """Member questions the bot could not answer, waiting for Muse."""
    blocked = _gate(request)
    if blocked:
        return blocked
    from telegram_integration.models import BrainQuestion
    rows = [{'id': q.pk, 'telegram_user_id': q.telegram_user_id,
             'question': q.question, 'created_at': q.created_at.isoformat()}
            for q in BrainQuestion.objects.filter(state='QUEUED')[:50]]
    return JsonResponse({'questions': rows})


@csrf_exempt
@require_POST
def telegram_answer(request):
    """Deliver Muse's answer to a queued member question via the bot."""
    blocked = _gate(request)
    if blocked:
        return blocked
    payload, error = _json_body(request)
    if error:
        return error
    from telegram_integration.brain_service import answer_question
    from telegram_integration.models import BrainQuestion
    try:
        question = BrainQuestion.objects.get(pk=int(payload['question_id']), state='QUEUED')
    except (KeyError, TypeError, ValueError, BrainQuestion.DoesNotExist):
        return JsonResponse({'error': 'question_not_found_or_already_handled'}, status=404)
    answer = str(payload.get('answer', '')).strip()
    if not answer or len(answer) > 4000:
        return JsonResponse({'error': 'answer_required_max_4000'}, status=400)
    answer_question(question, answer)
    Audit.objects.create(item=None, action='BRAIN_TELEGRAM_ANSWER',
                         detail={'question_id': question.pk, 'state': question.state})
    return JsonResponse({'question_id': question.pk, 'state': question.state})


@csrf_exempt
@require_POST
def test_item(request):
    """Create one private synthetic WAITING item so the owner can watch the
    full loop (outbox -> draft -> inbox -> review -> dismiss) on production
    without a shell. Synthetic items can never be handed off or published."""
    blocked = _gate(request)
    if blocked:
        return blocked
    key = 'test:' + uuid.uuid4().hex
    item = Item.objects.create(
        key=key, kind='NEWS', title='Synthetic KPN test — not real news',
        original={'title': 'Synthetic KPN test — not real news',
                  'text': 'This is a fictional test report. A fictional youth reading group in Kebbi State met on a Saturday to discuss a reading programme. No attendance figure, named participants, funding, or verified outcome has been supplied. Do not invent them.',
                  'source_url': '', 'synthetic': True})
    Job.objects.create(key='generate:' + key, kind='GENERATE', item=item)
    Audit.objects.create(item=item, action='BRAIN_TEST_ITEM_CREATED')
    return JsonResponse({'item_id': item.pk, 'state': item.state}, status=201)
