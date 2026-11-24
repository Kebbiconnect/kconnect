"""Public Human Impact Files (KPN Media Phase 4, v2.8.0; presentation
rebuilt in the Page-by-Page Upgrade, Priority 3).

Human Impact Files are journalism about the people behind an issue:
ordinary Campaigns whose StoryProfile kind is IMPACT. This page lists
the PUBLISHED ones using only the editors' PUBLIC profile fields
(who is affected, their situation, what to watch). Consent records —
which gate publication of stories featuring identifiable people, see
services.consent_block_reason — are internal and are never queried
or rendered here.

Priority 3 (brief §C, decision D-10): the hub is a documentary
collection, not another news feed. Stories browse by the brief's
eight impact themes: a story's theme is its editor-set
`impact_category` when one is recorded, otherwise the presentation
mapping from its news category (StoryProfile.effective_impact_category).
The latest story leads as the featured file; stories followed over
time carry their published-update count.

Mounted at /impact/stories/: the /impact/ address itself has belonged
to core's organisational impact page since before KPN Media, and
existing URLs are never shadowed or replaced.
"""
from django.shortcuts import render
from django.urls import reverse

from campaigns.models import Campaign
from .models import StoryProfile


def _published_impact_stories():
    return list(
        Campaign.objects
        .filter(status='PUBLISHED', story_profile__kind='IMPACT')
        .select_related('story_profile', 'lga')
        .order_by('-published_at'))


def impact_list(request):
    stories = _published_impact_stories()
    valid = dict(StoryProfile.IMPACT_CATEGORY_CHOICES)
    active_category = request.GET.get('category', '')
    if active_category not in valid:
        active_category = ''

    counts = {key: 0 for key in valid}
    for story in stories:
        theme = story.story_profile.effective_impact_category
        if theme in counts:
            counts[theme] += 1
    categories = [
        {'key': key, 'label': label, 'count': counts[key]}
        for key, label in StoryProfile.IMPACT_CATEGORY_CHOICES
    ]

    if active_category:
        shown = [s for s in stories
                 if s.story_profile.effective_impact_category == active_category]
    else:
        shown = stories
    featured = shown[0] if shown else None
    grid = shown[1:] if shown else []

    # Published-update counts: stories KPN has followed over time say so.
    update_counts = {}
    if stories:
        from .models import StoryUpdate
        for row in (StoryUpdate.objects
                    .filter(article__in=stories, status='PUBLISHED')
                    .values('article_id')):
            update_counts[row['article_id']] = \
                update_counts.get(row['article_id'], 0) + 1
    for story in stories:
        story.update_count = update_counts.get(story.pk, 0)

    return render(request, 'story_intelligence/impact_list.html', {
        'stories': shown,
        'featured': featured,
        'grid_stories': grid,
        'categories': categories,
        'active_category': active_category,
        'active_category_label': valid.get(active_category, ''),
        'total_count': len(stories),
        'followed_count': len(update_counts),
        'crumbs': [
            ('Newsroom', reverse('campaigns:newsroom')),
            ('Human Impact Files', None),
        ],
    })
