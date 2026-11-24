"""Public Future Signal list (KPN Media Phase 4, v2.8.0; presentation
rebuilt in the Page-by-Page Upgrade, Priority 3).

Future Signal is an evidence-led editorial format: KPN editors write
analysis pieces (ordinary Campaigns whose StoryProfile kind is SIGNAL)
that say what KPN is seeing, what evidence it rests on, and what would
change the assessment. It is NOT a prediction feed and nothing here is
generated automatically — every piece is written and framed by an
editor, and the page labels it as analysis, not established fact.

Priority 3 (brief §F): reports browse by the brief's eight themes
(`StoryProfile.signal_category`, set by editors) and can be filtered
by the strength of the evidence behind them (`signal_confidence` —
evidence-strength wording, never a probability). A signal without a
recorded theme lists under "All signals" only.

Only PUBLISHED signal stories are listed. Consent records, audit
entries and other internal records are never queried here.
"""
from django.shortcuts import render
from django.urls import reverse

from campaigns.models import Campaign
from .models import StoryProfile


def signal_list(request):
    stories = (Campaign.objects
               .filter(status='PUBLISHED', story_profile__kind='SIGNAL')
               .select_related('story_profile', 'lga')
               .order_by('-published_at'))

    valid_themes = dict(StoryProfile.SIGNAL_CATEGORY_CHOICES)
    valid_confidence = dict(StoryProfile.SIGNAL_CONFIDENCE_CHOICES)
    active_theme = request.GET.get('theme', '')
    if active_theme not in valid_themes:
        active_theme = ''
    active_confidence = request.GET.get('confidence', '')
    if active_confidence not in valid_confidence:
        active_confidence = ''

    theme_counts = {key: 0 for key in valid_themes}
    for story in stories:
        theme = story.story_profile.signal_category
        if theme in theme_counts:
            theme_counts[theme] += 1
    themes = [
        {'key': key, 'label': label, 'count': theme_counts[key]}
        for key, label in StoryProfile.SIGNAL_CATEGORY_CHOICES
    ]
    confidences = [
        {'key': key, 'label': label}
        for key, label in StoryProfile.SIGNAL_CONFIDENCE_CHOICES
    ]

    shown = stories
    if active_theme:
        shown = shown.filter(story_profile__signal_category=active_theme)
    if active_confidence:
        shown = shown.filter(story_profile__signal_confidence=active_confidence)
    shown = list(shown)

    return render(request, 'story_intelligence/signal_list.html', {
        'stories': shown,
        'themes': themes,
        'confidences': confidences,
        'active_theme': active_theme,
        'active_theme_label': valid_themes.get(active_theme, ''),
        'active_confidence': active_confidence,
        'total_count': stories.count(),
        'has_filters': bool(active_theme or active_confidence),
        'crumbs': [
            ('Newsroom', reverse('campaigns:newsroom')),
            ('Future Signal', None),
        ],
    })
