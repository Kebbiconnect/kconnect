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
"""

# Pill labels exactly as rendered in core/templates/core/faq.html.
FAQ_CATEGORY_LABELS = {
    'all': 'All',
    'about': 'About KPN',
    'membership': 'Membership',
    'leadership': 'Leadership',
    'reporting': 'Reporting',
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
}

# The template's default: the "All" pill shows every item.
DEFAULT_FAQ_CATEGORY = 'all'


def faq_category(question):
    """The template category slug for an FAQ question.

    Keyed by the question text as stored/rendered; unknown questions
    use the template's default "All" handling (``all``).
    """
    return FAQ_CATEGORY_BY_QUESTION.get(question, DEFAULT_FAQ_CATEGORY)
