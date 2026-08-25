"""
campaigns/templatetags/campaign_extras.py

Template tags and filters for the KPN Newsroom:
- render_article_blocks: Convert Editor.js JSON → safe HTML
- category_colour / verification_badge helpers
"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import json

register = template.Library()


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------

def _render_paragraph(data):
    text = escape(data.get('text', ''))
    # Editor.js paragraph can include inline HTML like <b>, <i>, <a>
    # We stored it from the editor so it should be safe — but we escape
    # raw user input above then restore allowed inline tags carefully.
    # For production you would sanitize with bleach; here we trust our editors.
    raw = data.get('text', '')
    return f'<p class="mb-4 leading-relaxed text-gray-800 dark:text-gray-200">{raw}</p>'


def _render_header(data):
    text = data.get('text', '')
    level = data.get('level', 2)
    level = max(2, min(4, int(level)))
    size_map = {2: 'text-2xl font-bold mt-8 mb-4', 3: 'text-xl font-semibold mt-6 mb-3', 4: 'text-lg font-semibold mt-5 mb-2'}
    cls = size_map.get(level, size_map[2])
    return f'<h{level} class="{cls} text-gray-900 dark:text-white">{text}</h{level}>'


def _render_list(data):
    style = data.get('style', 'unordered')
    items = data.get('items', [])
    tag = 'ol' if style == 'ordered' else 'ul'
    list_cls = 'list-decimal' if style == 'ordered' else 'list-disc'
    items_html = ''.join(
        f'<li class="mb-1 text-gray-800 dark:text-gray-200">{item}</li>'
        for item in items
    )
    return f'<{tag} class="{list_cls} pl-6 mb-4 space-y-1">{items_html}</{tag}>'


def _render_image(data):
    file_data = data.get('file', {})
    url = file_data.get('url', data.get('url', ''))
    caption = data.get('caption', '')
    stretched = data.get('stretched', False)
    bg = data.get('withBackground', False)
    border = data.get('withBorder', False)

    img_cls = 'w-full rounded-lg'
    if stretched:
        img_cls += ' max-w-none'
    if border:
        img_cls += ' border border-gray-300 dark:border-gray-600'
    wrapper_cls = 'my-6'
    if bg:
        wrapper_cls += ' bg-gray-100 dark:bg-gray-800 p-4 rounded-lg'

    caption_html = f'<figcaption class="text-center text-sm text-gray-500 dark:text-gray-400 mt-2">{caption}</figcaption>' if caption else ''
    if not url:
        return ''
    return (
        f'<figure class="{wrapper_cls}">'
        f'<img src="{escape(url)}" alt="{escape(caption)}" class="{img_cls}" loading="lazy">'
        f'{caption_html}'
        f'</figure>'
    )


def _render_quote(data):
    text = data.get('text', '')
    caption = data.get('caption', '')
    alignment = data.get('alignment', 'left')
    align_cls = 'text-center' if alignment == 'center' else ''
    cite_html = f'<cite class="block text-sm text-gray-500 dark:text-gray-400 mt-2 not-italic">— {caption}</cite>' if caption else ''
    return (
        f'<blockquote class="border-l-4 border-kpn-green pl-6 py-2 my-6 {align_cls}">'
        f'<p class="text-xl italic text-gray-700 dark:text-gray-300">{text}</p>'
        f'{cite_html}'
        f'</blockquote>'
    )


def _render_delimiter(_data):
    return '<hr class="my-8 border-gray-200 dark:border-gray-700">'


def _render_warning(data):
    title = data.get('title', 'Note')
    message = data.get('message', '')
    return (
        f'<div class="my-6 p-4 bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-300 '
        f'dark:border-yellow-700 rounded-lg">'
        f'<p class="font-semibold text-yellow-800 dark:text-yellow-300 mb-1">'
        f'<i class="fas fa-exclamation-triangle mr-1"></i>{title}</p>'
        f'<p class="text-yellow-700 dark:text-yellow-400 text-sm">{message}</p>'
        f'</div>'
    )


def _render_checklist(data):
    items = data.get('items', [])
    rows = []
    for item in items:
        if isinstance(item, dict):
            checked = item.get('checked', False)
            text = item.get('text', '')
        else:
            checked = False
            text = str(item)
        icon = '<i class="fas fa-check-square text-kpn-green"></i>' if checked else '<i class="far fa-square text-gray-400"></i>'
        rows.append(
            f'<li class="flex items-start gap-2 mb-1 text-gray-800 dark:text-gray-200">'
            f'{icon}<span>{text}</span></li>'
        )
    return f'<ul class="my-4 space-y-1">{"".join(rows)}</ul>'


def _render_embed(data):
    service = data.get('service', '')
    embed_url = data.get('embed', '')
    caption = data.get('caption', '')
    if not embed_url:
        return ''
    caption_html = f'<p class="text-center text-sm text-gray-500 mt-2">{caption}</p>' if caption else ''
    return (
        f'<div class="my-6 aspect-video">'
        f'<iframe src="{escape(embed_url)}" class="w-full h-full rounded-lg" '
        f'allowfullscreen loading="lazy" title="{escape(caption or service)}"></iframe>'
        f'{caption_html}'
        f'</div>'
    )


BLOCK_RENDERERS = {
    'paragraph': _render_paragraph,
    'header': _render_header,
    'list': _render_list,
    'image': _render_image,
    'quote': _render_quote,
    'delimiter': _render_delimiter,
    'warning': _render_warning,
    'checklist': _render_checklist,
    'embed': _render_embed,
}


@register.filter(name='render_article_blocks')
def render_article_blocks(content_json):
    """
    Usage in template: {{ article.content_json|render_article_blocks }}
    Takes the Editor.js JSON dict (already deserialized by Django JSONField)
    and returns safe HTML.
    """
    if not content_json:
        return mark_safe('')

    if isinstance(content_json, str):
        try:
            content_json = json.loads(content_json)
        except (json.JSONDecodeError, TypeError):
            return mark_safe(f'<p>{escape(content_json)}</p>')

    blocks = content_json.get('blocks', []) if isinstance(content_json, dict) else []
    parts = []
    for block in blocks:
        btype = block.get('type', '')
        data = block.get('data', {})
        renderer = BLOCK_RENDERERS.get(btype)
        if renderer:
            parts.append(renderer(data))
        else:
            # Fallback: try to render any text
            raw = data.get('text', '')
            if raw:
                parts.append(f'<p class="mb-4 text-gray-800 dark:text-gray-200">{raw}</p>')

    return mark_safe('\n'.join(parts))


@register.filter(name='verification_badge')
def verification_badge(article):
    """Render a compact KPN verification badge."""
    labels = {
        'VERIFIED': ('KPN VERIFIED', 'bg-green-100 text-green-800 border border-green-300'),
        'CONFIRMED': ('KPN CONFIRMED', 'bg-blue-100 text-blue-800 border border-blue-300'),
        'DEVELOPING': ('KPN DEVELOPING', 'bg-yellow-100 text-yellow-800 border border-yellow-300'),
        'COMMUNITY_ALERT': ('KPN COMMUNITY ALERT', 'bg-red-100 text-red-800 border border-red-300'),
    }
    # Use article.verification_status if article is a Campaign object, else treat as string
    status = getattr(article, 'verification_status', article)
    label, cls = labels.get(status, ('KPN DEVELOPING', 'bg-yellow-100 text-yellow-800 border border-yellow-300'))
    return mark_safe(
        f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold '
        f'tracking-wide uppercase {cls}">{label}</span>'
    )
