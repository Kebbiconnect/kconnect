"""Page-by-Page Upgrade · Priority 6 tests (brief §I, Code of Conduct).

The Priority 6 build is a restructuring/presentation task: the existing
constitutional content of /code-of-conduct/ is reorganised into the
brief's twelve parts (purpose & scope, member responsibilities,
leadership responsibilities, ethical communication, financial
integrity, prohibited conduct, safeguarding, reporting, investigation
and fair hearing, disciplinary measures, appeals, FAQ) under a sticky
table of contents, with a real Kebbi photographic hero. The hard
constraint is preservation: every substantive provision of the old page
— above all the reporting, investigation, sanctions and appeals
provisions — must survive word-for-word in substance. These tests pin
the provision texts (copied from the pre-upgrade template), the route,
the section/FAQ anchor integrity, the hero (credit line removed
site-wide per the owner's 2026-11-24 instruction), and D-15: no
official Code of Conduct document exists in the repository, so the
page must carry NO download element (no placeholder button).
"""
import html
import re

from django.test import TestCase
from django.urls import reverse


def page_text(response):
    """Rendered page text: tags stripped, entities unescaped,
    whitespace collapsed."""
    text = re.sub(r'<[^>]+>', ' ', response.content.decode('utf-8'))
    return re.sub(r'\s+', ' ', html.unescape(text))


# Every substantive provision of the pre-upgrade page, verbatim.
PROVISIONS = [
    # Introduction / purpose
    'The Kebbi Progressive Youth Network (KPN) is built on the principles of unity, respect, and progressive development.',
    'To safeguard the integrity of the network and ensure a constructive environment for all members,',
    'Article XII of the KPN Constitution strictly defines our Code of Conduct and Disciplinary measures.',
    'Article XII of the Kebbi Progressive Youth Network Constitution',
    # Section 1 — general obligations
    'Every registered member and appointed leader of the Kebbi Progressive Youth Network shall:',
    'Uphold the aims and objectives of the KPN at all times.',
    'Conduct themselves in a manner that brings honor and respect to the organization.',
    'Respect the constitutional hierarchy and authority of the State Executive Council and recognized Zonal, LGA, and Ward leadership.',
    'Promote unity and peace among members and the wider Kebbi State community.',
    'Attend statutory meetings and participate actively in KPN civic and community programs.',
    # Section 2 — offenses and prohibited conduct
    'The following acts constitute offenses against the Network and shall attract strict disciplinary action:',
    'Financial Misappropriation: Embezzlement, fraud, or mismanagement of KPN funds or resources.',
    'Hate Speech: The use of ethnic, religious, or gender-based slurs, or incitement of violence against any group.',
    'Sabotage: Engaging in anti-network activities or collaborating with entities to undermine KPN objectives.',
    'Insubordination: Flagrant disrespect or refusal to carry out lawful directives from the State Executive Council or immediate superiors.',
    'Defamation: Publishing or broadcasting false and malicious information against the Network, its leadership, or its members.',
    'Dereliction of Duty: Consistent failure by an appointed leader to perform their constitutional duties (e.g., failure to submit mandatory reports).',
    'Falsification: Forgery of KPN documents, ID tags, or misrepresentation of the Network to external bodies.',
    'Disruption: Deliberate disruption of KPN meetings, events, or official digital platforms.',
    # Section 3 — disciplinary procedures (reporting / investigation)
    'Discipline within KPN is administered fairly, transparently, and without prejudice.',
    'Director of Legal Affairs & Ethics oversees the Disciplinary Committee, which handles all infractions.',
    'Reporting: Any member can report a violation via the hierarchical reporting structure (Ward → LGA → Zone → State).',
    'Investigation: The Disciplinary Committee shall investigate the allegations and grant the accused member a fair hearing.',
    'Recommendation: The Committee submits its findings and recommended sanctions to the State Executive Council.',
    'Ratification: The State Executive Council (or the President, in emergency cases) ratifies and enforces the sanction.',
    # Section 4 — sanctions
    'Depending on the gravity of the offense, the following sanctions may be applied:',
    'Reprimand: A formal written warning (First offense / Minor infractions).',
    'Suspension: Temporary removal from the Network or leadership position for a specified period not exceeding 6 months.',
    'Fines / Restitution: Mandatory repayment of misappropriated funds or replacement of damaged property.',
    'Removal from Office: Permanent stripping of leadership titles and responsibilities (Requires 2/3 majority vote of the State Executive Council).',
    'Expulsion: Complete revocation of KPN membership (Reserved for zero-tolerance offenses and severe sabotage).',
    # Section 5 — appeals
    'Any member subjected to disciplinary action has the right to appeal the decision within 14 days of receiving official notice.',
    'Appeals must be submitted in writing to the General Secretary, who shall convene an independent Appeals Panel appointed by the President.',
    'The decision of the Appeals Panel shall be final.',
    # Closing agreement
    'One Voice, One Change.',
    'By holding KPN membership or an ID tag, you expressly agree to abide by this Code of Conduct.',
    'Let us work together with integrity to build the Kebbi State of our dreams.',
]

PART_IDS = [
    'purpose', 'member-responsibilities', 'leadership-responsibilities',
    'ethical-communication', 'financial-integrity', 'prohibited-conduct',
    'safeguarding', 'reporting', 'investigation', 'disciplinary-measures',
    'appeals', 'faq',
]

FAQ_IDS = [
    'faq-applies-to', 'faq-prohibited', 'faq-zero-tolerance',
    'faq-reporting', 'faq-after-report', 'faq-fair-hearing',
    'faq-sanctions', 'faq-appeals',
]


class CodeOfConductPriority6Tests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse('core:code_of_conduct'))
        self.html = self.response.content.decode('utf-8')
        self.text = page_text(self.response)

    def test_route_resolves_and_renders(self):
        self.assertEqual(reverse('core:code_of_conduct'), '/code-of-conduct/')
        self.assertEqual(self.response.status_code, 200)
        self.assertTemplateUsed(self.response, 'core/code_of_conduct.html')

    def test_all_substantive_provisions_preserved(self):
        for provision in PROVISIONS:
            with self.subTest(provision=provision[:60]):
                self.assertIn(provision, self.text)

    def test_procedure_sanctions_appeals_sections_intact(self):
        # The hard-locked areas keep their original part placement:
        # reporting + investigation steps in order, sanctions list, appeals.
        reporting_at = self.text.index('Reporting: Any member can report')
        # Search on from Part 8: the next occurrences are Part 9's steps
        # (Part 3 carries one ratification excerpt, the FAQ repeats the
        # steps — neither disturbs the procedure's own order).
        investigation_at = self.text.index('Investigation: The Disciplinary Committee', reporting_at)
        recommendation_at = self.text.index('Recommendation: The Committee submits', reporting_at)
        ratification_at = self.text.index('Ratification: The State Executive Council', reporting_at)
        self.assertLess(reporting_at, investigation_at)
        self.assertLess(investigation_at, recommendation_at)
        self.assertLess(recommendation_at, ratification_at)

    def test_twelve_parts_present_with_toc_links(self):
        for part_id in PART_IDS:
            with self.subTest(part=part_id):
                self.assertIn(f'id="{part_id}"', self.html)
                self.assertIn(f'href="#{part_id}"', self.html)

    def test_faq_anchors_resolve(self):
        for faq_id in FAQ_IDS:
            with self.subTest(faq=faq_id):
                self.assertIn(f'id="{faq_id}"', self.html)
        # Every in-page anchor used on the page points at a real id.
        ids = set(re.findall(r'id="([^"]+)"', self.html))
        anchors = set(re.findall(r'href="#([^"]+)"', self.html))
        missing = {a for a in anchors if a and a not in ids}
        self.assertEqual(missing, set())

    def test_faq_answers_come_from_the_code_itself(self):
        # FAQ answers are the Code's own provisions, not new policy.
        self.assertIn('How do I report a violation?', self.text)
        self.assertIn('Any member can report a violation via the hierarchical reporting structure (Ward → LGA → Zone → State).', self.text)
        self.assertIn('How can I appeal a disciplinary decision?', self.text)
        self.assertIn('Which offenses are zero tolerance?', self.text)

    def test_hero_is_real_kebbi_photo_no_credit(self):
        # Manifest storage hashes the filename: img/conduct-hero.<hash>.jpg
        self.assertIn('img/conduct-hero.', self.html)
        # Owner instruction 2026-11-24: hero credit lines removed site-wide.
        self.assertNotIn('National Youth Day gathering, Birnin Kebbi', self.text)
        self.assertNotIn('Photo: Kebbi State Ministry of Youth Development & Sports', self.text)
        self.assertNotIn('kpn-hero-credit', self.html)

    def test_no_download_element_without_official_document(self):
        # D-15: no official Code of Conduct document exists in the repo,
        # so the page itself ships with no download button/link at all.
        # Scoped to the page's <main> content: since §24 (2026-11-27)
        # the global site footer carries the owner's "Download Android
        # App" link on every page, which is site chrome, not a Code of
        # Conduct document download.
        main = self.html.split('<main', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('download', main.lower())
        self.assertNotIn('.pdf', main.lower())

    def test_no_placeholder_or_guide_text(self):
        self.assertNotIn('verify current document', self.html.lower())
        self.assertNotIn('should explain', self.html.lower())
        self.assertNotIn('lorem', self.html.lower())
