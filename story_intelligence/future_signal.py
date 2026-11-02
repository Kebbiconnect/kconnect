"""Public Future Signal list (KPN Media Phase 4, v2.8.0).

Future Signal is an evidence-led editorial format: KPN editors write
analysis pieces (ordinary Campaigns whose StoryProfile kind is SIGNAL)
that say what KPN is seeing, what evidence it rests on, and what would
change the assessment. It is NOT a prediction feed and nothing here is
generated automatically — every piece is written and framed by an
editor, and the page labels it as analysis, not established fact.

Only PUBLISHED signal stories are listed. Consent records, audit
entries and other internal records are never queried here.
"""
from django.shortcuts import render

from campaigns.models import Campaign


def signal_list(request):
    stories = (Campaign.objects
               .filter(status='PUBLISHED', story_profile__kind='SIGNAL')
               .select_related('story_profile')
               .order_by('-published_at'))
    return render(request, 'story_intelligence/signal_list.html',
                  {'stories': stories})
