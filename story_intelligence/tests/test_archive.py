"""Phase 3 — Searchable Story Archive: text search across stories,
updates and promises; Story ID lookup; composing filters; pagination;
browse mode; escaping; and public safety (nothing non-public may
appear in results, excerpts or counts). The existing newsroom list and
search are untouched — one regression test pins that here too.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from core.models import CommunityReport
from editorial.tests.helpers import media_director
from leadership.models import LGA, Ward, Zone
from story_intelligence.models import (
    ConsentRecord, EvidenceRecord, Institution, Promise, StorySourceLink,
    StoryUpdate,
)

ARCHIVE_URL = reverse('archive:home')


def aware_days_ago(days):
    return timezone.now() - timedelta(days=days)


class ArchiveFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('arch_editor')
        cls.zone = Zone.objects.create(name='Kebbi Central')
        cls.other_zone = Zone.objects.create(name='Kebbi North')
        cls.lga = LGA.objects.create(name='Argungu', zone=cls.zone)
        cls.other_lga = LGA.objects.create(name='Yauri', zone=cls.other_zone)
        cls.ward = Ward.objects.create(name='Gulma', lga=cls.lga)

        cls.festival = Campaign.objects.create(
            author=cls.editor, title='Argungu Fishing Festival Returns',
            slug='argungu-fishing-festival-returns', status='PUBLISHED',
            subheadline='Thousands expected at the riverbank',
            content='The riverbank market reopened early. Farmers traded '
                    'under the harvestmoon sky near the water.',
            category='CULTURE', lga=cls.lga, location='Argungu',
            story_id='KPN-SI-2026-00101', published_at=aware_days_ago(10))
        cls.classrooms = Campaign.objects.create(
            author=cls.editor, title='New Classrooms for Birnin Kebbi',
            slug='new-classrooms-birnin-kebbi', status='PUBLISHED',
            content='', content_json={'blocks': [
                {'type': 'paragraph',
                 'data': {'text': 'A zebrawood bench was donated to each room.'}}]},
            category='EDUCATION', ward=cls.ward,
            story_id='KPN-SI-2026-00102', published_at=aware_days_ago(2))
        cls.road_story = Campaign.objects.create(
            author=cls.editor, title='Township Road Repairs Begin',
            slug='township-road-repairs-begin', status='PUBLISHED',
            content='Crews moved to site on Monday morning.',
            category='INFRASTRUCTURE', lga=cls.other_lga,
            story_id='KPN-SI-2026-00103', published_at=aware_days_ago(4))

        # Non-public articles — must never appear anywhere in the archive.
        cls.draft = Campaign.objects.create(
            author=cls.editor, title='DraftSecretTitle', slug='draft-secret',
            status='DRAFT', content='draftsecretword in the body',
            story_id='KPN-SI-2026-00666')
        cls.pending = Campaign.objects.create(
            author=cls.editor, title='PendingSecretTitle', slug='pending-secret',
            status='PENDING', content='pendingsecretword in the body')
        cls.rejected = Campaign.objects.create(
            author=cls.editor, title='RejectedSecretTitle', slug='rejected-secret',
            status='REJECTED', content='rejectedsecretword in the body')
        cls.archived = Campaign.objects.create(
            author=cls.editor, title='ArchivedSecretTitle', slug='archived-secret',
            status='ARCHIVED', content='archivedsecretword in the body',
            story_id='KPN-SI-2026-00109', published_at=aware_days_ago(30))

        cls.update = StoryUpdate.objects.create(
            article=cls.festival, title='Council Confirms Festival Date',
            body='The drumbeat ceremony will open the week of events.',
            status='PUBLISHED', published_at=aware_days_ago(1),
            author=cls.editor)
        cls.draft_update = StoryUpdate.objects.create(
            article=cls.festival, title='DraftUpdateSecretTitle',
            body='draftupdatesecret body', status='DRAFT', author=cls.editor)
        cls.orphan_update = StoryUpdate.objects.create(
            article=cls.draft, title='OrphanUpdateSecretTitle',
            body='orphanupdatesecret body', status='PUBLISHED',
            published_at=aware_days_ago(1), author=cls.editor)

        cls.institution = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY',
            contact_note='INTERNAL CONTACT NOTE', notes='INTERNAL NOTE')
        cls.other_institution = Institution.objects.create(
            name='Argungu Local Government', kind='LGA_GOVERNMENT')
        cls.promise = Promise.objects.create(
            institution=cls.institution,
            title='Rebuild the Argungu township road',
            description='The government promised to rebuild the road '
                        'with drainage on both sides.',
            announced_by='The Governor', announced_on='2026-09-15',
            lga=cls.lga, created_by=cls.editor)
        cls.other_promise = Promise.objects.create(
            institution=cls.other_institution,
            title='Renovate the Yauri general hospital',
            description='A full renovation of the wards and theatre.',
            announced_on='2026-08-01', lga=cls.other_lga,
            created_by=cls.editor)

        # Private material attached to a PUBLIC story — never searchable.
        EvidenceRecord.objects.create(
            article=cls.festival, title='PrivateEvidenceSecretTitle',
            kind='DOCUMENT', description='privateevidencesecret detail',
            is_public=False, added_by=cls.editor)
        ConsentRecord.objects.create(
            article=cls.festival, subject_descriptor='ConsentSecretPerson',
            consent_basis='WRITTEN', recorded_by=cls.editor,
            notes='consentsecretnotes')
        cls.report = CommunityReport.objects.create(
            reporter_name='SecretReporterName', reporter_phone='0800SECRET',
            lga=cls.lga, location_details='SecretLocationDetail',
            category='INFRASTRUCTURE',
            what_happened='A reportsecret detail was filed.',
            status='APPROVED')
        StorySourceLink.objects.create(
            report=cls.report, article=cls.festival, kind='SOURCE',
            linked_by=cls.editor)

    def slugs(self, response, key='stories_page'):
        return [a.slug for a in response.context[key].object_list]


class ArchiveBrowseTests(ArchiveFixture):
    def test_browse_mode_lists_recent_published_stories_with_ids(self):
        response = self.client.get(ARCHIVE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['browsing'])
        self.assertEqual(set(self.slugs(response)), {
            'argungu-fishing-festival-returns', 'new-classrooms-birnin-kebbi',
            'township-road-repairs-begin'})
        content = response.content.decode()
        self.assertIn('KPN-SI-2026-00101', content)
        self.assertIn('Browsing the archive', content)

    def test_browse_mode_hides_non_public_articles(self):
        response = self.client.get(ARCHIVE_URL)
        content = response.content.decode()
        for secret in ['DraftSecretTitle', 'PendingSecretTitle',
                       'RejectedSecretTitle', 'ArchivedSecretTitle']:
            self.assertNotIn(secret, content)

    def test_archive_is_linked_from_nav(self):
        response = self.client.get(ARCHIVE_URL)
        self.assertContains(response, 'href="/archive/"')

    def test_invalid_params_never_error(self):
        response = self.client.get(ARCHIVE_URL, {
            'zone': 'abc', 'lga': '', 'category': 'NOPE',
            'date_from': 'banana', 'date_to': '2026-13-40',
            'type': 'weird', 'sp': 'xyz'})
        self.assertEqual(response.status_code, 200)


class ArchiveSearchTests(ArchiveFixture):
    def test_search_by_title(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Fishing Festival'})
        self.assertEqual(response.context['stories_total'], 1)
        self.assertEqual(self.slugs(response),
                         ['argungu-fishing-festival-returns'])

    def test_search_by_subheadline(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'riverbank'})
        # Matches the festival subheadline AND its body — still one story.
        self.assertEqual(response.context['stories_total'], 1)
        self.assertEqual(self.slugs(response),
                         ['argungu-fishing-festival-returns'])

    def test_search_by_body_content_field(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'harvestmoon'})
        self.assertEqual(self.slugs(response),
                         ['argungu-fishing-festival-returns'])

    def test_search_by_body_content_json_blocks(self):
        # The classrooms story has an empty `content` fallback; its body
        # lives only in Editor.js blocks.
        response = self.client.get(ARCHIVE_URL, {'q': 'zebrawood'})
        self.assertEqual(response.context['stories_total'], 1)
        self.assertEqual(self.slugs(response), ['new-classrooms-birnin-kebbi'])
        self.assertIn('zebrawood', response.content.decode())

    def test_search_finds_story_updates(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'drumbeat'})
        self.assertEqual(response.context['updates_total'], 1)
        update = response.context['updates_page'].object_list[0]
        self.assertEqual(update.title, 'Council Confirms Festival Date')
        # The update links to its story's existing article page.
        self.assertContains(
            response,
            reverse('campaigns:article_detail',
                    args=['argungu-fishing-festival-returns']))

    def test_search_finds_promises_by_description(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'drainage'})
        self.assertEqual(response.context['promises_total'], 1)
        promise = response.context['promises_page'].object_list[0]
        self.assertEqual(promise.title, 'Rebuild the Argungu township road')

    def test_search_finds_promises_by_institution_name(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Ministry of Works'})
        self.assertEqual(response.context['promises_total'], 1)

    def test_results_are_labelled_by_type(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'road'})
        content = response.content.decode()
        self.assertIn('Story', content)
        self.assertIn('Promise', content)

    def test_title_match_ranks_before_body_match(self):
        older_title_match = Campaign.objects.create(
            author=self.editor, title='Harvestmoon Celebrations Planned',
            slug='harvestmoon-celebrations', status='PUBLISHED',
            content='Plans were announced.', category='CULTURE',
            story_id='KPN-SI-2026-00110', published_at=aware_days_ago(20))
        response = self.client.get(
            ARCHIVE_URL, {'q': 'harvestmoon', 'type': 'story'})
        results = response.context['stories_page'].object_list
        self.assertEqual(results[0].slug, older_title_match.slug)
        self.assertEqual(results[1].slug, 'argungu-fishing-festival-returns')

    def test_type_filter_limits_sections(self):
        response = self.client.get(
            ARCHIVE_URL, {'q': 'road', 'type': 'promise'})
        self.assertFalse(response.context['show_stories'])
        self.assertFalse(response.context['show_updates'])
        self.assertTrue(response.context['show_promises'])
        self.assertNotIn('Township Road Repairs Begin',
                         response.content.decode())


class ArchiveStoryIdTests(ArchiveFixture):
    def test_exact_story_id_redirects_to_article(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'KPN-SI-2026-00101'})
        self.assertRedirects(
            response,
            reverse('campaigns:article_detail',
                    args=['argungu-fishing-festival-returns']),
            fetch_redirect_response=False)

    def test_lowercase_story_id_also_resolves(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'kpn-si-2026-00102'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('campaigns:article_detail',
                    args=['new-classrooms-birnin-kebbi']))

    def test_unknown_story_id_falls_through_to_empty_search(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'KPN-SI-2026-99999'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_results'], 0)

    def test_story_id_of_unpublished_article_never_resolves(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'KPN-SI-2026-00666'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_results'], 0)


class ArchiveFilterTests(ArchiveFixture):
    def test_category_filter(self):
        response = self.client.get(
            ARCHIVE_URL, {'type': 'story', 'category': 'CULTURE'})
        self.assertEqual(self.slugs(response),
                         ['argungu-fishing-festival-returns'])

    def test_category_filter_empties_promises(self):
        response = self.client.get(ARCHIVE_URL, {'category': 'CULTURE'})
        self.assertEqual(response.context['promises_total'], 0)
        self.assertEqual(response.context['stories_total'], 1)

    def test_lga_filter_matches_ward_filed_stories(self):
        response = self.client.get(
            ARCHIVE_URL, {'type': 'story', 'lga': self.lga.pk})
        self.assertEqual(set(self.slugs(response)), {
            'argungu-fishing-festival-returns', 'new-classrooms-birnin-kebbi'})

    def test_zone_filter(self):
        response = self.client.get(
            ARCHIVE_URL, {'type': 'story', 'zone': self.zone.pk})
        self.assertEqual(set(self.slugs(response)), {
            'argungu-fishing-festival-returns', 'new-classrooms-birnin-kebbi'})

    def test_ward_filter(self):
        response = self.client.get(
            ARCHIVE_URL, {'type': 'story', 'ward': self.ward.pk})
        self.assertEqual(self.slugs(response), ['new-classrooms-birnin-kebbi'])

    def test_institution_filter(self):
        response = self.client.get(
            ARCHIVE_URL, {'institution': self.institution.pk})
        self.assertEqual(response.context['promises_total'], 1)
        self.assertEqual(response.context['stories_total'], 0)
        promise = response.context['promises_page'].object_list[0]
        self.assertEqual(promise.institution_id, self.institution.pk)

    def test_date_from_filter(self):
        cutoff = (timezone.now() - timedelta(days=5)).date().isoformat()
        response = self.client.get(
            ARCHIVE_URL, {'type': 'story', 'date_from': cutoff})
        self.assertEqual(set(self.slugs(response)), {
            'new-classrooms-birnin-kebbi', 'township-road-repairs-begin'})

    def test_date_to_filter(self):
        cutoff = (timezone.now() - timedelta(days=5)).date().isoformat()
        response = self.client.get(
            ARCHIVE_URL, {'type': 'story', 'date_to': cutoff})
        self.assertEqual(self.slugs(response),
                         ['argungu-fishing-festival-returns'])

    def test_filters_compose_with_text_query(self):
        response = self.client.get(
            ARCHIVE_URL, {'q': 'road', 'lga': self.lga.pk})
        # The road story is in the other LGA; the promise is in this one.
        self.assertEqual(response.context['stories_total'], 0)
        self.assertEqual(response.context['promises_total'], 1)
        response = self.client.get(
            ARCHIVE_URL, {'q': 'festival', 'category': 'EDUCATION'})
        self.assertEqual(response.context['total_results'], 0)
        response = self.client.get(
            ARCHIVE_URL, {'q': 'festival', 'category': 'CULTURE'})
        self.assertEqual(response.context['stories_total'], 1)


class ArchivePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('arch_pager')
        articles = []
        for i in range(1, 26):
            articles.append(Campaign(
                author=cls.editor, title=f'Floodrelief Story {i:02d}',
                slug=f'floodrelief-story-{i:02d}', status='PUBLISHED',
                content='floodrelief teams reached the villages.',
                category='EMERGENCY', story_id=f'KPN-SI-2026-{i:05d}',
                published_at=timezone.now() - timedelta(hours=i)))
        Campaign.objects.bulk_create(articles)

    def test_first_page_has_twenty_and_total_count(self):
        response = self.client.get(
            ARCHIVE_URL, {'q': 'floodrelief', 'type': 'story'})
        page = response.context['stories_page']
        self.assertEqual(len(page.object_list), 20)
        self.assertEqual(response.context['stories_total'], 25)
        self.assertEqual(page.paginator.num_pages, 2)

    def test_second_page_has_the_rest_and_no_overlap(self):
        first = self.client.get(
            ARCHIVE_URL, {'q': 'floodrelief', 'type': 'story'})
        second = self.client.get(
            ARCHIVE_URL, {'q': 'floodrelief', 'type': 'story', 'sp': '2'})
        first_slugs = {a.slug for a in first.context['stories_page'].object_list}
        second_page = second.context['stories_page']
        self.assertEqual(len(second_page.object_list), 5)
        second_slugs = {a.slug for a in second_page.object_list}
        self.assertTrue(first_slugs.isdisjoint(second_slugs))

    def test_pagination_links_preserve_query_params(self):
        response = self.client.get(
            ARCHIVE_URL, {'q': 'floodrelief', 'type': 'story'})
        content = response.content.decode()
        self.assertIn('sp=2', content)
        self.assertIn('q=floodrelief', content)

    def test_out_of_range_page_clamps_to_last(self):
        response = self.client.get(
            ARCHIVE_URL, {'q': 'floodrelief', 'type': 'story', 'sp': '99'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stories_page'].number, 2)


class ArchivePrivacyTests(ArchiveFixture):
    def assert_no_results(self, query):
        response = self.client.get(ARCHIVE_URL, {'q': query})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_results'], 0)

    def test_draft_article_body_is_not_searchable(self):
        self.assert_no_results('draftsecretword')

    def test_pending_article_body_is_not_searchable(self):
        self.assert_no_results('pendingsecretword')

    def test_rejected_article_body_is_not_searchable(self):
        self.assert_no_results('rejectedsecretword')

    def test_archived_article_body_is_not_searchable(self):
        self.assert_no_results('archivedsecretword')

    def test_draft_update_is_not_searchable(self):
        self.assert_no_results('draftupdatesecret')

    def test_update_on_unpublished_article_is_not_searchable(self):
        self.assert_no_results('orphanupdatesecret')

    def test_private_evidence_is_not_searchable(self):
        self.assert_no_results('privateevidencesecret')

    def test_consent_record_is_not_searchable(self):
        self.assert_no_results('consentsecretnotes')
        response = self.client.get(ARCHIVE_URL)
        self.assertNotIn('ConsentSecretPerson', response.content.decode())

    def test_reporter_private_data_never_appears(self):
        self.assert_no_results('reportsecret')
        self.assert_no_results('SecretReporterName')
        response = self.client.get(ARCHIVE_URL, {'q': 'festival'})
        content = response.content.decode()
        for secret in ['SecretReporterName', '0800SECRET',
                       'SecretLocationDetail', 'INTERNAL CONTACT NOTE',
                       'INTERNAL NOTE']:
            self.assertNotIn(secret, content)


class ArchiveEscapingTests(ArchiveFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.html_story = Campaign.objects.create(
            author=cls.editor,
            title='Market <script>alert(1)</script> Day',
            slug='market-html-day', status='PUBLISHED',
            content='Traders said <b>business</b> was brisk at the fair.',
            category='MARKETS', story_id='KPN-SI-2026-00111',
            published_at=aware_days_ago(1))

    def test_html_in_title_and_body_renders_escaped(self):
        response = self.client.get(ARCHIVE_URL, {'q': 'Market'})
        content = response.content.decode()
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', content)
        self.assertNotIn('<script>alert(1)</script>', content)

    def test_html_in_query_is_escaped(self):
        response = self.client.get(ARCHIVE_URL, {'q': '<script>alert(2)'})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('&lt;script&gt;alert(2)', content)
        self.assertNotIn('<script>alert(2)', content)


class NewsroomRegressionTests(ArchiveFixture):
    def test_existing_newsroom_list_and_search_still_work(self):
        response = self.client.get(reverse('campaigns:newsroom'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse('campaigns:newsroom'), {'q': 'Fishing'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Argungu Fishing Festival Returns',
                      response.content.decode())
        self.assertNotIn('DraftSecretTitle', response.content.decode())
