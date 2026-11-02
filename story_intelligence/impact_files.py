"""Public Human Impact Files list (KPN Media Phase 4, v2.8.0).

Human Impact Files are journalism about the people behind an issue:
ordinary Campaigns whose StoryProfile kind is IMPACT. This page lists
the PUBLISHED ones using only the editors' PUBLIC profile fields
(who is affected, their situation, what to watch). Consent records —
which gate publication of stories featuring identifiable people, see
services.consent_block_reason — are internal and are never queried
or rendered here.

Mounted at /impact/stories/: the /impact/ address itself has belonged
to core's organisational impact page since before KPN Media, and
existing URLs are never shadowed or replaced.
"""
from django.shortcuts import render

from campaigns.models import Campaign


def impact_list(request):
    stories = (Campaign.objects
               .filter(status='PUBLISHED', story_profile__kind='IMPACT')
               .select_related('story_profile')
               .order_by('-published_at'))
    return render(request, 'story_intelligence/impact_list.html',
                  {'stories': stories})
