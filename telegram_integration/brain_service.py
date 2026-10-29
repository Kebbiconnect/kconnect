"""Muse's hands on the KPN Telegram bot.

The bot is an admin of the KPN channel. Through this service Muse can:
- post announcements to the channel,
- share newly published website articles to the channel,
- answer member questions that the bot's instant providers could not.

Every send is recorded in BotOutbox / BrainQuestion first. Sending uses
the existing services.send_telegram_message helper and bot token.
"""
import html
import logging
import re

from django.conf import settings
from django.utils import timezone

from .models import BotOutbox, BrainQuestion
from .services import get_channel_id, send_telegram_message

logger = logging.getLogger(__name__)


def _plain(text, limit=300):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    return re.sub(r'\s+', ' ', text).strip()[:limit]


def article_share_text(article):
    base = (getattr(settings, 'SITE_URL', '') or 'https://kpn.com.ng').rstrip('/')
    url = f'{base}/campaigns/article/{article.slug}/'
    excerpt = article.meta_description or _plain(article.content, 220)
    parts = [f'📰 <b>{html.escape(article.title)}</b>']
    if excerpt:
        parts.append(html.escape(excerpt))
    parts.append(f'👉 Read more: {url}')
    parts.append('#KPN #Kebbi')
    return '\n\n'.join(parts)


def enqueue_article_share(article):
    """Queue a channel share for a published article (once per article)."""
    if BotOutbox.objects.filter(kind='ARTICLE', article=article).exists():
        return None
    return BotOutbox.objects.create(kind='ARTICLE', article=article,
                                    text=article_share_text(article))


def enqueue_announcement(text, chat_id=''):
    return BotOutbox.objects.create(kind='ANNOUNCEMENT', text=text, chat_id=chat_id or '')


def send_outbox_row(row):
    """Send one queued outbox row now. Returns True when Telegram accepted it."""
    target = row.chat_id or get_channel_id()
    response = send_telegram_message(target, row.text)
    if response.get('ok'):
        row.state = 'SENT'
        row.sent_at = timezone.now()
        result = response.get('result') or {}
        row.telegram_message_id = result.get('message_id')
        row.error = ''
    else:
        row.state = 'FAILED'
        row.error = str(response.get('error') or response.get('description') or 'send_failed')[:300]
    row.save(update_fields=['state', 'sent_at', 'telegram_message_id', 'error'])
    return row.state == 'SENT'


def drain_outbox(limit=10):
    sent = failed = 0
    for row in BotOutbox.objects.filter(state='QUEUED').order_by('created_at')[:limit]:
        if send_outbox_row(row):
            sent += 1
        else:
            failed += 1
    return {'sent': sent, 'failed': failed}


def queue_question(telegram_user_id, question):
    return BrainQuestion.objects.create(telegram_user_id=telegram_user_id, question=question)


def answer_question(row, answer_text):
    """Deliver Muse's answer to the member in their bot chat."""
    body = ('✅ <b>Answer from the KPN media team</b>\n\n'
            f'<i>You asked:</i> {html.escape(_plain(row.question, 200))}\n\n'
            f'{html.escape(answer_text)}')
    out = BotOutbox.objects.create(kind='ANSWER', chat_id=str(row.telegram_user_id), text=body)
    if send_outbox_row(out):
        row.answer = answer_text
        row.state = 'SENT'
        row.answered_at = timezone.now()
        row.error = ''
    else:
        row.state = 'FAILED'
        row.error = out.error
    row.save(update_fields=['answer', 'state', 'answered_at', 'error'])
    return row
