"""FAQ expansion (owner-directed, 2026-11-27): cards/questions 10-30.

Covers the 21 FAQs added on top of the original nine template cards:
three new categories (opportunities, trackers, support) plus additions
to about/membership/leadership/reporting. The rows exist in the test
database because the data migration ``core/0015_faq_expansion`` runs
when the test DB is built.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from core.faq_categories import FAQ_CATEGORY_LABELS, faq_category
from core.models import FAQ

API = '/api/v1/'

# (question, expected category slug) for the 21 expansion questions,
# in template order (openFaq 10-30).
NEW_ITEMS = [
    ('When was KPN founded, and is it registered?', 'about'),
    ('Which areas does KPN cover?', 'about'),
    ("What does 'One Voice, One Change' mean?", 'about'),
    ('How do I join KPN?', 'membership'),
    ('What happens after I submit my membership application?', 'membership'),
    ('How do I sign in to the KPN mobile app?', 'membership'),
    ('Who leads KPN in my ward or LGA?', 'leadership'),
    ('What are the senatorial zones in KPN?', 'leadership'),
    ('How do I report a problem or a story from my community?', 'reporting'),
    ('What kind of issues can I report?', 'reporting'),
    ('What is the Opportunities Hub?', 'opportunities'),
    ("What does 'Verification Pending' mean on an opportunity?", 'opportunities'),
    ('How do I apply for an opportunity listed on KPN?', 'opportunities'),
    ('How do I report a suspicious opportunity listing?', 'opportunities'),
    ('What is the Promise Tracker?', 'trackers'),
    ("What does 'Verified Completed' mean on the Promise Tracker?", 'trackers'),
    ('What is the Project Tracker?', 'trackers'),
    ('How can I support KPN?', 'support'),
    ('How do I contact KPN?', 'support'),
    ('What can I do with the KPN mobile app?', 'support'),
    ('How do I follow KPN on Telegram?', 'support'),
]

# The original nine template mappings — must stay unchanged.
ORIGINAL_ITEMS = [
    ('What is the Kebbi Progressive Youth Network (KPN)?', 'about'),
    ('Is KPN a political organization?', 'about'),
    ('How does KPN fund its activities?', 'about'),
    ('Who can join KPN?', 'membership'),
    ('What are the responsibilities of a member?', 'membership'),
    ('Can I lose my membership?', 'membership'),
    ('How is KPN structured?', 'leadership'),
    ('How does KPN gather community reports?', 'reporting'),
    ('How is information classified before publication?', 'reporting'),
]


class FaqExpansionCategoryTests(TestCase):
    def test_each_new_question_maps_to_its_category(self):
        for question, category in NEW_ITEMS:
            self.assertEqual(faq_category(question), category, question)

    def test_new_category_labels_exist(self):
        self.assertEqual(FAQ_CATEGORY_LABELS['opportunities'], 'Opportunities')
        self.assertEqual(FAQ_CATEGORY_LABELS['trackers'], 'Trackers')
        self.assertEqual(FAQ_CATEGORY_LABELS['support'], 'Support & Contact')

    def test_original_nine_mappings_unchanged(self):
        for question, category in ORIGINAL_ITEMS:
            self.assertEqual(faq_category(question), category, question)
        # Original labels untouched too.
        self.assertEqual(FAQ_CATEGORY_LABELS['all'], 'All')
        self.assertEqual(FAQ_CATEGORY_LABELS['about'], 'About KPN')
        self.assertEqual(FAQ_CATEGORY_LABELS['membership'], 'Membership')
        self.assertEqual(FAQ_CATEGORY_LABELS['leadership'], 'Leadership')
        self.assertEqual(FAQ_CATEGORY_LABELS['reporting'], 'Reporting')


class FaqExpansionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def fetch_all_faqs(self):
        """Collect every row from the paginated public FAQ endpoint."""
        rows = []
        url = API + 'content/faq/'
        while url:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, response.content)
            data = response.data
            if isinstance(data, dict) and 'results' in data:
                rows.extend(data['results'])
                nxt = data.get('next')
                url = nxt.split('/api/v1/', 1)[-1] if nxt else None
                if url:
                    url = API + url
            else:
                rows.extend(data)
                url = None
        return rows

    def test_migration_seeded_the_new_questions(self):
        seeded = set(FAQ.objects.values_list('question', flat=True))
        for question, _category in NEW_ITEMS:
            self.assertIn(question, seeded)

    def test_api_returns_new_questions_with_correct_categories(self):
        by_question = {row['question']: row['category']
                        for row in self.fetch_all_faqs()}
        for question, category in NEW_ITEMS:
            self.assertIn(question, by_question)
            self.assertEqual(by_question[question], category, question)
