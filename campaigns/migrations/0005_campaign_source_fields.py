"""v2.4.4: source_name/source_url on Campaign + backfill.

Brain-published articles used to carry their source as a trailing
plain-text "Source: https://..." paragraph, which renders as dead
text. Convert those articles: move the URL into source_url, drop the
text block/line, and fill source_name from the linked editorial item
when one exists (else the source hostname).
"""
from django.db import migrations, models


def backfill_sources(apps, schema_editor):
    Campaign = apps.get_model('campaigns', 'Campaign')
    Item = apps.get_model('editorial', 'Item')
    from campaigns.source_backfill import extract_text_source, name_from_url
    items_by_article = {}
    for item in Item.objects.filter(article__isnull=False):
        items_by_article[item.article_id] = item
    for article in Campaign.objects.filter(reporter_credit='KPN_EDITORIAL'):
        if article.source_url:
            continue
        url, changed = extract_text_source(article)
        if not url:
            continue
        article.source_url = url[:500]
        item = items_by_article.get(article.pk)
        name = ''
        if item is not None:
            if getattr(item, 'source_id', None):
                source = getattr(item, 'source', None)
                name = getattr(source, 'name', '') or ''
            if not name and isinstance(item.original, dict):
                name = str(item.original.get('source_name', '') or '')
        article.source_name = (name or name_from_url(url))[:200]
        article.save(update_fields=['source_url', 'source_name',
                                    'content_json', 'content'])


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0004_alter_campaign_options_and_more'),
        ('editorial', '0002_remove_provider_accounting'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='source_name',
            field=models.CharField(
                blank=True, max_length=200,
                help_text='Original publisher (e.g. Punch, Independent NG)'),
        ),
        migrations.AddField(
            model_name='campaign',
            name='source_url',
            field=models.URLField(
                blank=True, max_length=500,
                help_text='Link to the original story'),
        ),
        migrations.RunPython(backfill_sources, migrations.RunPython.noop),
    ]
