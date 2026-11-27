"""FAQ categories — the SINGLE source for the API ``category`` field.

Owner rule (Part B, screen 53): never paraphrase. The categories and
the question-to-category mapping below were extracted VERBATIM from
the public FAQ web template, ``core/templates/core/faq.html``:

* The category pills at the top of that template are hard-coded as
  ``<button class="category-btn" data-category="...">Label</button>``:
  ``all`` = "All", ``about`` = "About KPN", ``membership`` =
  "Membership", ``leadership`` = "Leadership", ``reporting`` =
  "Reporting".
* Each FAQ card in the template carries its own hard-coded
  ``data-category`` attribute; the mapping below is keyed by the
  card's question text exactly as rendered in the template (the
  FAQ model's stable identity for an item — its stored ``question``).

The category value exposed by the API is the template's
``data-category`` slug, exactly as written in the template.

Questions the template does not categorise (e.g. FAQs added later
through the staff FAQ manager, which has no category field) fall back
to the template's own default handling: the "All" pill
(``data-category="all"``), under which every item is shown. No
category names are invented here.

Owner-directed expansion, 2026-11-27: on the owner's direct
instruction, the FAQ was expanded beyond the original nine template
cards. Three new categories were added — ``opportunities``
("Opportunities"), ``trackers`` ("Trackers") and ``support``
("Support & Contact") — together with 21 new questions (cards 10–30
in the template). The new material was added in three places at once:
the template (``core/templates/core/faq.html``), this mapping, and
the data migration ``core/migrations/0015_faq_expansion.py``, which
seeds the matching ``core.FAQ`` rows. The original nine questions,
answers, pills and mappings above are unchanged.
"""

# Pill labels exactly as rendered in core/templates/core/faq.html.
FAQ_CATEGORY_LABELS = {
    'all': 'All',
    'about': 'About KPN',
    'membership': 'Membership',
    'leadership': 'Leadership',
    'reporting': 'Reporting',
    'opportunities': 'Opportunities',
    'trackers': 'Trackers',
    'support': 'Support & Contact',
}

# Question text (verbatim from the template cards) -> the card's
# hard-coded data-category value in core/templates/core/faq.html.
FAQ_CATEGORY_BY_QUESTION = {
    # About Questions (data-category="about")
    'What is the Kebbi Progressive Youth Network (KPN)?': 'about',
    'Is KPN a political organization?': 'about',
    'How does KPN fund its activities?': 'about',
    # Membership Questions (data-category="membership")
    'Who can join KPN?': 'membership',
    'What are the responsibilities of a member?': 'membership',
    'Can I lose my membership?': 'membership',
    # Leadership Questions (data-category="leadership")
    'How is KPN structured?': 'leadership',
    # Reporting & Activities Questions (data-category="reporting")
    'How does KPN gather community reports?': 'reporting',
    'How is information classified before publication?': 'reporting',
    # About additions (2026-11-27 expansion, cards 10-12)
    'When was KPN founded, and is it registered?': 'about',
    'Which areas does KPN cover?': 'about',
    "What does 'One Voice, One Change' mean?": 'about',
    # Membership additions (2026-11-27 expansion, cards 13-15)
    'How do I join KPN?': 'membership',
    'What happens after I submit my membership application?': 'membership',
    'How do I sign in to the KPN mobile app?': 'membership',
    # Leadership additions (2026-11-27 expansion, cards 16-17)
    'Who leads KPN in my ward or LGA?': 'leadership',
    'What are the senatorial zones in KPN?': 'leadership',
    # Reporting additions (2026-11-27 expansion, cards 18-19)
    'How do I report a problem or a story from my community?': 'reporting',
    'What kind of issues can I report?': 'reporting',
    # Opportunities Questions (data-category="opportunities")
    'What is the Opportunities Hub?': 'opportunities',
    "What does 'Verification Pending' mean on an opportunity?": 'opportunities',
    'How do I apply for an opportunity listed on KPN?': 'opportunities',
    'How do I report a suspicious opportunity listing?': 'opportunities',
    # Trackers Questions (data-category="trackers")
    'What is the Promise Tracker?': 'trackers',
    "What does 'Verified Completed' mean on the Promise Tracker?": 'trackers',
    'What is the Project Tracker?': 'trackers',
    # Support & Contact Questions (data-category="support")
    'How can I support KPN?': 'support',
    'How do I contact KPN?': 'support',
    'What can I do with the KPN mobile app?': 'support',
    'How do I follow KPN on Telegram?': 'support',
}

# The template's default: the "All" pill shows every item.
DEFAULT_FAQ_CATEGORY = 'all'


def faq_category(question):
    """The template category slug for an FAQ question.

    Keyed by the question text as stored/rendered; unknown questions
    use the template's default "All" handling (``all``).
    """
    return FAQ_CATEGORY_BY_QUESTION.get(question, DEFAULT_FAQ_CATEGORY)
