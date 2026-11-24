"""Phase 7 — public LGA news pages, field reporting, polish.

Covers: all 21 LGA pages resolve; an LGA page lists only its own
linked published stories; the article↔LGA link paths (conversion,
article-field mirror, staff tagging); tracker counts on the page;
field submissions entering the pipeline uniformly (MANUAL source,
manual location, chosen category primary, desk visibility, Phase 6
restriction for sensitive categories); reporter isolation; the
Newsroom menu entry.
"""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from campaigns.models import Campaign
from campaigns.services import publish_campaign
from editorial.tests.helpers import (
    general_member, make_user, media_director,
)
from leadership.models import LGA
from story_intelligence.models import Institution, Promise

from intelligence import desk as desk_service
from intelligence import field_reports as field_service
from intelligence import security as security_service
from intelligence.models import (
    ArticleLocation, FieldReport, IntelligenceCategory, Project,
    PublicationCategory, PublicationLocation, RawPublication,
)
from intelligence.seeding import ZONES
from intelligence.tests.helpers import seed_directory
from intelligence.tests.test_processing import make_item, make_source

# The 21 canonical LGAs. (The test database also carries an
# 'Editorial Test LGA' row created by the editorial test helpers —
# a fixture artefact that never exists in production.)
CANONICAL_LGAS = [name for names in ZONES.values() for name in names]


def make_article(author, title, status='PUBLISHED', **kw):
    kw.setdefault('slug', slugify(title))
    kw.setdefault('content', 'Body text.')
    kw.setdefault('category', 'COMMUNITY')
    if status == 'PUBLISHED':
        kw.setdefault('published_at', timezone.now())
    return Campaign.objects.create(
        author=author, title=title, status=status, **kw)


def trusted_reporter(username='field_rep'):
    return make_user(username, title=None, role='GENERAL',
                     is_trusted_reporter=True)


class LgaPageTests(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('p7_director')
        self.jega = LGA.objects.get(name='Jega')
        self.argungu = LGA.objects.get(name='Argungu')

    def test_all_21_lga_pages_resolve(self):
        self.assertEqual(len(CANONICAL_LGAS), 21)
        for name in CANONICAL_LGAS:
            lga = LGA.objects.get(name=name)
            response = self.client.get(
                reverse('lga_news:detail', args=[slugify(lga.name)]))
            self.assertEqual(response.status_code, 200, lga.name)
            self.assertContains(response, f'{lga.name} LGA')

    def test_unknown_lga_slug_is_404(self):
        response = self.client.get(
            reverse('lga_news:detail', args=['not-a-place']))
        self.assertEqual(response.status_code, 404)

    def test_index_lists_all_lgas_with_real_counts(self):
        article = make_article(self.director, 'Jega Market Reopens')
        ArticleLocation.objects.create(
            article=article, lga=self.jega, kind='MANUAL')
        response = self.client.get(reverse('lga_news:index'))
        self.assertEqual(response.status_code, 200)
        row_names = {r['lga'].name for r in response.context['rows']}
        for name in CANONICAL_LGAS:
            self.assertIn(name, row_names)
        row = next(r for r in response.context['rows']
                   if r['lga'].pk == self.jega.pk)
        self.assertEqual(row['stories'], 1)
        other = next(r for r in response.context['rows']
                     if r['lga'].pk == self.argungu.pk)
        self.assertEqual(other['stories'], 0)

    def test_lga_page_lists_only_its_own_linked_published_stories(self):
        mine = make_article(self.director, 'Jega Story One')
        ArticleLocation.objects.create(
            article=mine, lga=self.jega, kind='MANUAL')
        draft = make_article(self.director, 'Jega Draft Story',
                             status='DRAFT')
        ArticleLocation.objects.create(
            article=draft, lga=self.jega, kind='MANUAL')
        unlinked = make_article(self.director, 'Unlinked Story')
        other_lga = make_article(self.director, 'Argungu Story')
        ArticleLocation.objects.create(
            article=other_lga, lga=self.argungu, kind='MANUAL')

        response = self.client.get(
            reverse('lga_news:detail', args=['jega']))
        self.assertContains(response, 'Jega Story One')
        self.assertNotContains(response, 'Jega Draft Story')
        self.assertNotContains(response, 'Unlinked Story')
        self.assertNotContains(response, 'Argungu Story')
        self.assertEqual(response.context['story_total'], 1)

    def test_article_field_mirror_creates_link(self):
        # Saving an article whose own lga field is set mirrors an
        # ARTICLE-kind link via the Campaign save signal.
        article = make_article(self.director, 'Mirrored Story',
                               lga=self.jega)
        link = ArticleLocation.objects.get(article=article)
        self.assertEqual(link.lga, self.jega)
        self.assertEqual(link.kind, 'ARTICLE')

    def test_empty_lga_page_is_an_honest_empty_state(self):
        response = self.client.get(
            reverse('lga_news:detail', args=['argungu']))
        self.assertContains(
            response, 'No stories published for Argungu yet')
        self.assertContains(response, 'No promises tracked')
        self.assertContains(response, 'No projects tracked')

    def test_tracker_counts_and_recent_rows_match_records(self):
        institution = Institution.objects.create(
            name='Kebbi State Government', kind='GOVERNMENT')
        Promise.objects.create(
            institution=institution, title='Jega Water Promise',
            description='A promise.', announced_on=timezone.localdate(),
            lga=self.jega, status='IN_PROGRESS')
        Promise.objects.create(
            institution=institution, title='Argungu Promise',
            description='Another.', announced_on=timezone.localdate(),
            lga=self.argungu, status='ANNOUNCED')
        Project.objects.create(
            title='Jega Township Roads', description='Roads.',
            sector='INFRASTRUCTURE', category='ROAD', lga=self.jega,
            status='DELAYED', created_by=self.director)
        response = self.client.get(
            reverse('lga_news:detail', args=['jega']))
        self.assertEqual(response.context['promise_counts']['tracked'], 1)
        self.assertEqual(
            response.context['promise_counts']['in_progress'], 1)
        self.assertEqual(
            response.context['project_counts']['pj_tracked'], 1)
        self.assertEqual(
            response.context['project_counts']['pj_delayed_stalled'], 1)
        self.assertContains(response, 'Jega Water Promise')
        self.assertContains(response, 'Jega Township Roads')
        self.assertNotContains(response, 'Argungu Promise')
        self.assertContains(
            response, f"?lga={self.jega.pk}")

    def test_newsroom_menu_contains_lga_news(self):
        response = self.client.get('/')
        self.assertContains(response, 'LGA News')
        self.assertContains(response, '/newsroom/lga/')


class ConversionLinkTests(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('p7_conv_director')
        self.source = make_source()
        self.jega = LGA.objects.get(name='Jega')

    def test_conversion_records_lga_links_from_unit_evidence(self):
        item = make_item(
            self.source, 'Fire Guts Shops in Jega Market',
            text='A night fire destroyed shops at the Jega main '
                 'market overnight.')
        from intelligence.relevance import process_publication
        process_publication(item)
        item.refresh_from_db()
        unit = item.cluster or item
        for action in ('TRIAGE', 'BEGIN_VERIFICATION', 'VERIFY',
                       'APPROVE'):
            desk_service.apply_transition(unit, self.director, action)
        article = desk_service.convert_to_draft(unit, self.director)
        links = ArticleLocation.objects.filter(article=article)
        self.assertTrue(links.filter(lga=self.jega,
                                     kind='CONVERSION').exists())
        # And once the article truly publishes, the LGA page lists it.
        publish_campaign(article, self.director)
        response = self.client.get(
            reverse('lga_news:detail', args=['jega']))
        self.assertContains(response, 'Fire Guts Shops in Jega Market')


class ArticleLocationTaggingTests(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('p7_tag_director')
        self.member = general_member('p7_tag_member')
        self.jega = LGA.objects.get(name='Jega')
        self.article = make_article(self.director, 'Taggable Story')

    def test_manager_can_tag_and_untag(self):
        self.client.force_login(self.director)
        response = self.client.post(
            reverse('intelligence:article_location_add',
                    args=[self.article.pk]),
            {'lga': self.jega.pk})
        self.assertEqual(response.status_code, 302)
        link = ArticleLocation.objects.get(article=self.article)
        self.assertEqual(link.kind, 'MANUAL')
        response = self.client.post(
            reverse('intelligence:article_location_remove',
                    args=[link.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ArticleLocation.objects.filter(article=self.article).exists())

    def test_non_manager_is_refused(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('intelligence:article_locations'))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse('intelligence:article_location_add',
                    args=[self.article.pk]),
            {'lga': self.jega.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ArticleLocation.objects.filter(article=self.article).exists())


class FieldReportTests(TestCase):
    def setUp(self):
        seed_directory()
        self.reporter = trusted_reporter('p7_rep_one')
        self.other = trusted_reporter('p7_rep_two')
        self.member = general_member('p7_plain_member')
        self.director = media_director('p7_field_director')
        self.jega = LGA.objects.get(name='Jega')
        self.education = IntelligenceCategory.objects.get(slug='education')
        self.security = IntelligenceCategory.objects.get(
            slug='security-public-safety')

    def submit(self, user, **overrides):
        data = {
            'headline': 'Borehole Broken at Jega Primary School',
            'report_text': 'The only borehole at the primary school '
                           'has been broken for two weeks.',
            'lga': self.jega.pk,
            'category': self.education.pk,
            'occurred_at': '2026-11-23T09:30',
        }
        data.update(overrides)
        self.client.force_login(user)
        return self.client.post(
            reverse('intelligence:field_report_new'), data)

    def test_form_requires_the_capability(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('intelligence:field_report_new'))
        self.assertEqual(response.status_code, 403)

    def test_plain_post_creates_pipeline_intake(self):
        response = self.submit(self.reporter)
        self.assertEqual(response.status_code, 302)
        report = FieldReport.objects.get(reporter=self.reporter)
        pub = report.publication
        self.assertIsNotNone(pub)
        self.assertEqual(pub.source.connector_kind, 'MANUAL')
        self.assertEqual(pub.source.name, field_service.FIELD_SOURCE_NAME)
        self.assertEqual(pub.title, report.headline)
        # The reporter's LGA is a MANUAL location row.
        location = PublicationLocation.objects.get(
            publication=pub, match_kind='MANUAL')
        self.assertEqual(location.lga, self.jega)
        # The reporter's chosen category is the primary link.
        primary = PublicationCategory.objects.get(
            publication=pub, is_primary=True)
        self.assertEqual(primary.category, self.education)
        # The item reached the desk in DISCOVERED state.
        pub.refresh_from_db()
        unit = pub.cluster or pub
        self.assertEqual(unit.desk_state, 'DISCOVERED')
        self.assertIn(pub, list(
            security_service.visible_items(self.director)))

    def test_reporter_sees_only_own_submissions(self):
        self.submit(self.reporter)
        self.submit(self.other, headline='Argungu Ferry Delay Report',
                    lga=LGA.objects.get(name='Argungu').pk)
        self.client.force_login(self.reporter)
        response = self.client.get(
            reverse('intelligence:field_reports_mine'))
        self.assertContains(response, 'Borehole Broken at Jega')
        self.assertNotContains(response, 'Argungu Ferry Delay Report')
        self.assertContains(response, 'Submitted')
        self.client.force_login(self.other)
        response = self.client.get(
            reverse('intelligence:field_reports_mine'))
        self.assertContains(response, 'Argungu Ferry Delay Report')
        self.assertNotContains(response, 'Borehole Broken at Jega')

    def test_sensitive_field_report_is_restricted(self):
        self.submit(
            self.reporter, category=self.security.pk,
            headline='Armed Men Seen Near Jega Border Village',
            report_text='Residents reported armed men passing near '
                        'the village last night.')
        report = FieldReport.objects.get(reporter=self.reporter)
        pub = report.publication
        primary = PublicationCategory.objects.get(
            publication=pub, is_primary=True)
        self.assertEqual(primary.category, self.security)
        self.assertTrue(security_service.unit_is_restricted(pub))
        # Hidden from a non-holder with other intelligence access…
        from editorial.tests.helpers import assistant_media
        assistant = assistant_media('p7_field_asst')
        self.assertNotIn(pub, list(
            security_service.visible_items(assistant)))
        # …and visible to a security-desk holder.
        self.assertIn(pub, list(
            security_service.visible_items(self.director)))

    def test_field_report_status_follows_the_desk(self):
        self.submit(self.reporter)
        report = FieldReport.objects.get(reporter=self.reporter)
        pub = report.publication
        unit = pub.cluster or pub
        desk_service.apply_transition(unit, self.director, 'TRIAGE')
        desk_service.apply_transition(
            unit, self.director, 'REJECT', note='Not enough detail.')
        self.assertEqual(
            field_service.report_status_label(report), 'Not taken forward')
