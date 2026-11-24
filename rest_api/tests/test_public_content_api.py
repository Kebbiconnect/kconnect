"""API completion (2026-11-24): Promise/Project trackers, Future
Signal, Human Impact Files, Story Archive, LGA News, the article
Story File, opportunity/community serializer currency, Impact &
Metrics groups+coverage, and the health/root endpoints.

Privacy pins throughout: no reporter data, no captured_by, no
non-public evidence, no draft updates, no unpublished corrections,
no consent internals — ever.
"""
import io
import shutil
import tempfile
from datetime import date, timedelta

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from core.models import CommunityInitiative, Opportunity
from editorial.tests.helpers import media_director
from intelligence.models import (
    ArticleLocation, Project, ProjectEvidence, ProjectMilestone,
)
from leadership.models import LGA, Ward, Zone
from story_intelligence.models import (
    Claim, Correction, EvidenceRecord, Institution, Promise,
    PromiseUpdate, StoryProfile, StoryUpdate,
)

API = '/api/v1/'


def png(name='test.png'):
    out = io.BytesIO()
    Image.new('RGB', (16, 16), 'green').save(out, 'PNG')
    return SimpleUploadedFile(name, out.getvalue(), content_type='image/png')


def make_article(author, title, **kwargs):
    kwargs.setdefault('content', 'Article body text.')
    kwargs.setdefault('published_at', timezone.now())
    status = kwargs.pop('status', 'PUBLISHED')
    return Campaign.objects.create(
        author=author, title=title,
        slug=title.lower().replace(' ', '-').replace(',', ''),
        status=status, **kwargs)


class SeededCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('api_completion_editor')
        cls.zone = Zone.objects.create(name='API Zone')
        cls.lga = LGA.objects.create(name='Jega', zone=cls.zone)
        cls.ward = Ward.objects.create(name='Jega Ward', lga=cls.lga)
        cls.institution = Institution.objects.create(
            name='Kebbi State Government', kind='GOVERNMENT')

    def setUp(self):
        self.client = APIClient()
        self.temp = tempfile.mkdtemp(prefix='kpn-api-completion-')
        self.storage = override_settings(MEDIA_ROOT=self.temp)
        self.storage.enable()

    def tearDown(self):
        self.storage.disable()
        shutil.rmtree(self.temp, ignore_errors=True)


class HealthAndSchemaTests(SeededCase):
    def test_health_is_public_and_carries_no_internals(self):
        response = self.client.get(API + 'health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'ok')
        self.assertEqual(response.data['api_version'], '1.1.0')
        self.assertIn('trackers', response.data['resources'])
        body = str(response.data).lower()
        self.assertNotIn('django', body)
        self.assertNotIn('secret', body)

    def test_root_lists_resource_groups(self):
        response = self.client.get(API)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'KPN API')
        self.assertIn('promises', response.data['resources']['trackers'])

    def test_schema_renders(self):
        response = self.client.get(API + 'schema/')
        self.assertEqual(response.status_code, 200)


class PromiseApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.story = make_article(self.editor, 'Road Work Begins In Jega')
        self.draft = make_article(self.editor, 'Unpublished Linked Story',
                                  status='DRAFT')
        self.promise = Promise.objects.create(
            institution=self.institution, title='Rebuild Jega township road',
            description='Rebuild the township road within a year.',
            announced_by='Governor', announced_on=date(2026, 1, 10),
            source_name='State broadcast', deadline=date(2027, 1, 10),
            status='IN_PROGRESS', sector='INFRASTRUCTURE',
            lga=self.lga, zone=self.zone)
        self.promise.stories.add(self.story, self.draft)
        PromiseUpdate.objects.create(
            promise=self.promise, update_date=date(2026, 6, 1),
            title='Grading started', body='Grading has started.',
            status_after='IN_PROGRESS',
            evidence_title='Site report', evidence_url='https://example.org/r')

    def test_list_shape_fields_and_pagination(self):
        response = self.client.get(API + 'promises/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['public_code'],
                         f'KPN-PT-{self.promise.pk:04d}')
        self.assertEqual(row['institution_name'], 'Kebbi State Government')
        self.assertEqual(row['sector'], 'INFRASTRUCTURE')
        self.assertEqual(row['sector_label'], 'Infrastructure')
        self.assertIn('In progress', row['status_label'])
        self.assertFalse(row['is_delayed'])
        # Only the published linked story is exposed.
        self.assertEqual([s['slug'] for s in row['stories']],
                         [self.story.slug])
        for forbidden in ('created_by', 'next_check_date',
                          'verification_claim'):
            self.assertNotIn(forbidden, row)

    def test_detail_includes_updates_timeline(self):
        response = self.client.get(API + f'promises/{self.promise.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['updates']), 1)
        update = response.data['updates'][0]
        self.assertEqual(update['title'], 'Grading started')
        self.assertEqual(update['evidence_url'], 'https://example.org/r')
        self.assertNotIn('author', update)

    def test_filters(self):
        other = Promise.objects.create(
            institution=self.institution, title='School feeding pledge',
            description='Feed pupils.', announced_on=date(2026, 2, 1),
            status='ANNOUNCED', sector='EDUCATION')
        by_sector = self.client.get(API + 'promises/', {'sector': 'EDUCATION'})
        self.assertEqual([r['id'] for r in by_sector.data['results']],
                         [other.pk])
        by_lga = self.client.get(API + 'promises/', {'lga': self.lga.pk})
        self.assertEqual([r['id'] for r in by_lga.data['results']],
                         [self.promise.pk])
        by_status = self.client.get(API + 'promises/', {'status': 'ANNOUNCED'})
        self.assertEqual([r['id'] for r in by_status.data['results']],
                         [other.pk])
        by_q = self.client.get(API + 'promises/', {'q': 'township'})
        self.assertEqual([r['id'] for r in by_q.data['results']],
                         [self.promise.pk])
        invalid = self.client.get(API + 'promises/', {'sector': 'NOPE'})
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.data['count'], 2)

    def test_promise_image_uses_display_image(self):
        self.promise.image = png('promise.png')
        self.promise.save()
        response = self.client.get(API + 'promises/')
        self.assertTrue(response.data['results'][0]['image'])


class ProjectApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            project_code='KPN-PRJ-2026-00001',
            title='Jega water scheme rehabilitation',
            description='Rehabilitate the water scheme.',
            sector='WATER', category='WATER', institution=self.institution,
            lga=self.lga, status='REPORTED_ABANDONED')
        ProjectMilestone.objects.create(
            project=self.project, date=date(2026, 5, 1),
            title='Reported abandoned by residents',
            status_after='REPORTED_ABANDONED')
        ProjectEvidence.objects.create(
            project=self.project, kind='PHOTO', title='Public site photo',
            url='https://example.org/photo', is_public=True,
            verification_state='DOCUMENTED', captured_by=self.editor)
        ProjectEvidence.objects.create(
            project=self.project, kind='OTHER', title='Internal note file',
            url='https://example.org/internal', is_public=False,
            captured_by=self.editor)

    def test_list_fields_and_documented_facts_blank_when_unset(self):
        response = self.client.get(API + 'projects/')
        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        self.assertEqual(row['project_code'], 'KPN-PRJ-2026-00001')
        self.assertEqual(row['status_label'], 'Reported abandoned')
        self.assertEqual(row['sector_label'], 'Water & Sanitation')
        # Never invented: no contractor/amount was documented.
        self.assertEqual(row['contractor_name'], '')
        self.assertIsNone(row['contract_amount'])
        self.assertEqual(row['contract_amount_display'], '')
        self.assertNotIn('captured_by', str(response.data))
        self.assertNotIn('assigned_officer', row)

    def test_detail_public_evidence_only(self):
        response = self.client.get(API + f'projects/{self.project.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['milestones']), 1)
        titles = [e['title'] for e in response.data['evidence']]
        self.assertEqual(titles, ['Public site photo'])
        self.assertNotIn('Internal note file', str(response.data))
        self.assertNotIn('captured_by', str(response.data))

    def test_status_filter(self):
        response = self.client.get(
            API + 'projects/', {'status': 'REPORTED_ABANDONED'})
        self.assertEqual(response.data['count'], 1)
        response = self.client.get(
            API + 'projects/', {'status': 'COMPLETED_VERIFIED'})
        self.assertEqual(response.data['count'], 0)


class SignalApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.base = make_article(self.editor, 'Early Rains Arrive')
        self.signal = make_article(self.editor, 'A Farming Season At Risk',
                                   category='AGRICULTURE')
        profile = StoryProfile.objects.create(
            article=self.signal, kind='SIGNAL',
            signal_observation='Early rains arrived, then stopped.',
            why_it_matters='Planting decisions depend on it.',
            who_is_affected='Rain-fed farmers.',
            what_is_unknown='Whether the rains return.',
            what_to_watch='Weekly rainfall reports.',
            signal_confidence='DEVELOPING', signal_horizon='This season',
            signal_change_condition='Three weeks of steady rain.',
            signal_category='AGRICULTURE_FOOD')
        profile.related_stories.add(self.base)
        Claim.objects.create(article=self.signal, status='CONFIRMED',
                             text='Rainfall was below average.')
        Claim.objects.create(article=self.signal, status='OFFICIAL_STATEMENT',
                             text='The ministry projects a late harvest.',
                             source_name='State ministry')
        Claim.objects.create(article=self.signal, status='DEVELOPING',
                             text='Dry spells may lengthen.')

    def test_list_and_theme_filter(self):
        response = self.client.get(API + 'signals/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['signal_category'], 'AGRICULTURE_FOOD')
        self.assertEqual(row['signal_confidence_label'],
                         'Developing — the evidence is growing')
        filtered = self.client.get(API + 'signals/',
                                   {'theme': 'ECONOMIC_OUTLOOK'})
        self.assertEqual(filtered.data['count'], 0)

    def test_detail_claim_groups_never_blended(self):
        response = self.client.get(API + f'signals/{self.signal.slug}/')
        self.assertEqual(response.status_code, 200)
        groups = response.data['claim_groups']
        self.assertEqual([c['text'] for c in groups['confirmed_facts']],
                         ['Rainfall was below average.'])
        self.assertEqual(
            [c['text'] for c in groups['estimates_and_official_statements']],
            ['The ministry projects a late harvest.'])
        self.assertEqual(
            [c['text'] for c in groups['still_being_established']],
            ['Dry spells may lengthen.'])
        questions = response.data['questions']
        self.assertEqual(questions['analyst_judgment'],
                         'Planting decisions depend on it.')
        self.assertEqual(questions['projections']['horizon'], 'This season')
        body = str(response.data).lower()
        self.assertNotIn('probabilit', body)
        self.assertNotIn('likelihood', body)


class ImpactFileApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.story = make_article(self.editor, 'The Teacher Of Jega',
                                  category='EDUCATION')
        StoryProfile.objects.create(
            article=self.story, kind='IMPACT',
            who_is_affected='Pupils in Jega.',
            why_it_matters='Their school had no teacher.',
            who_contributed='The community association.',
            what_is_unknown='Funding for next term.',
            what_to_watch='Enrolment figures.')
        Claim.objects.create(article=self.story, status='CONFIRMED',
                             text='Enrolment doubled in one term.')
        StoryUpdate.objects.create(
            article=self.story, kind='FOLLOW_UP', title='A second teacher',
            body='A second teacher has been posted.', status='PUBLISHED',
            published_at=timezone.now())
        StoryUpdate.objects.create(
            article=self.story, kind='FOLLOW_UP', title='Secret draft',
            body='Not public.', status='DRAFT')

    def test_list_effective_category_and_filter(self):
        response = self.client.get(API + 'impact-files/')
        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        # D-10: EDUCATION news category maps to EDUCATION_OPPORTUNITY.
        self.assertEqual(row['impact_category'], 'EDUCATION_OPPORTUNITY')
        self.assertEqual(row['update_count'], 1)
        filtered = self.client.get(API + 'impact-files/',
                                   {'category': 'EDUCATION_OPPORTUNITY'})
        self.assertEqual(filtered.data['count'], 1)
        filtered = self.client.get(API + 'impact-files/',
                                   {'category': 'RURAL'})
        self.assertEqual(filtered.data['count'], 0)

    def test_detail_six_parts_and_privacy(self):
        response = self.client.get(API + f'impact-files/{self.story.slug}/')
        self.assertEqual(response.status_code, 200)
        parts = response.data['six_parts']
        self.assertEqual(parts['who_is_affected'], 'Pupils in Jega.')
        self.assertEqual(parts['their_situation'],
                         'Their school had no teacher.')
        self.assertEqual(parts['who_contributed_to_the_change'],
                         'The community association.')
        self.assertEqual(
            parts['what_the_evidence_shows']['claims'][0]['text'],
            'Enrolment doubled in one term.')
        developed = parts['how_the_story_developed']
        self.assertEqual([u['title'] for u in developed],
                         ['A second teacher'])
        body = str(response.data)
        self.assertNotIn('Secret draft', body)
        self.assertNotIn('consent', body.lower())
        self.assertNotIn('features_identifiable_people', body)


class StoryFileApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.article = make_article(
            self.editor, 'Governor Visits Jega', story_id='KPN-SI-2026-00042',
            source_name='Daily Trust', source_url='https://example.org/src')
        StoryProfile.objects.create(
            article=self.article, kind='NEWS',
            why_it_matters='It affects Jega residents.')
        Claim.objects.create(article=self.article, status='CONFIRMED',
                             text='The visit happened on Monday.',
                             source_name='Daily Trust')
        EvidenceRecord.objects.create(
            article=self.article, kind='SOURCE_LINK', title='Public source',
            url='https://example.org/public', is_public=True)
        EvidenceRecord.objects.create(
            article=self.article, kind='DOCUMENT', title='Private file',
            url='https://example.org/private', is_public=False)
        StoryUpdate.objects.create(
            article=self.article, kind='DEVELOPMENT', title='Road reopened',
            body='The road has reopened.', status='PUBLISHED',
            published_at=timezone.now())
        Correction.objects.create(
            article=self.article, kind='CORRECTION',
            text='The date was corrected.', published=True)
        Correction.objects.create(
            article=self.article, kind='CORRECTION',
            text='Unpublished correction.', published=False)
        ArticleLocation.objects.create(
            article=self.article, lga=self.lga, kind='ARTICLE')
        self.plain = make_article(self.editor, 'Plain Story No Panel')

    def test_detail_exposes_public_story_file(self):
        response = self.client.get(API + f'newsroom/{self.article.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['source_name'], 'Daily Trust')
        story_file = response.data['story_file']
        self.assertEqual(story_file['story_id'], 'KPN-SI-2026-00042')
        self.assertEqual([c['text'] for c in story_file['claims']],
                         ['The visit happened on Monday.'])
        self.assertEqual(story_file['claims'][0]['status_label'],
                         'Confirmed by KPN')
        self.assertEqual([e['title'] for e in story_file['evidence']],
                         ['Public source'])
        self.assertEqual([u['title'] for u in story_file['updates']],
                         ['Road reopened'])
        self.assertEqual([c['text'] for c in story_file['corrections']],
                         ['The date was corrected.'])
        self.assertEqual(story_file['article_locations'][0]['lga_name'],
                         'Jega')
        body = str(response.data)
        self.assertNotIn('Private file', body)
        self.assertNotIn('Unpublished correction', body)

    def test_plain_article_has_no_story_file(self):
        response = self.client.get(API + f'newsroom/{self.plain.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['story_file'])


class ArchiveApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.article = make_article(
            self.editor, 'Water Returns To Jega',
            story_id='KPN-SI-2026-00077')
        Claim.objects.create(article=self.article, status='CONFIRMED',
                             text='Boreholes were repaired in March.')
        Correction.objects.create(
            article=self.article, kind='CORRECTION',
            text='A name was corrected.', published=True)

    def test_search_reaches_public_claims(self):
        response = self.client.get(API + 'archive/', {'q': 'Boreholes'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['stories_total'], 1)
        row = response.data['stories'][0]
        self.assertEqual(row['record_status'], 'Corrected')
        self.assertEqual(row['correction_count'], 1)
        self.assertEqual(row['section']['kind'], 'NEWS')

    def test_exact_story_id_lookup_returns_the_record(self):
        response = self.client.get(API + 'archive/',
                                   {'q': 'KPN-SI-2026-00077'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['match_type'], 'story_id')
        self.assertEqual(response.data['story']['slug'], self.article.slug)

    def test_unknown_story_id_falls_through_to_empty_search(self):
        response = self.client.get(API + 'archive/',
                                   {'q': 'KPN-SI-2026-99999'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['match_type'], 'search')
        self.assertEqual(response.data['stories_total'], 0)

    def test_counts_present(self):
        response = self.client.get(API + 'archive/')
        self.assertEqual(response.data['counts']['stories'], 1)


class LgaNewsApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.linked = make_article(self.editor, 'Linked Jega Story')
        ArticleLocation.objects.create(
            article=self.linked, lga=self.lga, kind='MANUAL')
        self.unlinked = make_article(self.editor, 'Unlinked Story')
        Promise.objects.create(
            institution=self.institution, title='Jega pledge',
            description='A pledge.', announced_on=date(2026, 3, 1),
            lga=self.lga)

    def test_index_counts(self):
        response = self.client.get(API + 'lgas/news/')
        self.assertEqual(response.status_code, 200)
        rows = {r['name']: r for r in response.data['results']}
        self.assertEqual(rows['Jega']['stories'], 1)
        self.assertEqual(rows['Jega']['promises'], 1)
        self.assertEqual(response.data['totals']['stories'], 1)

    def test_detail_uses_recorded_links_only(self):
        from intelligence.article_locations import lga_slug
        response = self.client.get(
            API + f'lgas/news/{lga_slug(self.lga)}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['lga']['name'], 'Jega')
        self.assertEqual(response.data['story_total'], 1)
        self.assertEqual(
            [s['slug'] for s in response.data['stories']],
            [self.linked.slug])
        self.assertEqual(response.data['promise_counts']['tracked'], 1)
        self.assertEqual(len(response.data['recent_promises']), 1)

    def test_unknown_lga_404(self):
        response = self.client.get(API + 'lgas/news/no-such-lga/')
        self.assertEqual(response.status_code, 404)


class OpportunityCurrencyTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.open_opp = Opportunity.objects.create(
            title='Open Scholarship', slug='open-scholarship',
            category='SCHOLARSHIP', provider='Provider A',
            description='Desc.', application_link='https://example.org/apply',
            deadline=date(2027, 5, 1), status='OPEN',
            opens_at=date(2026, 12, 1), location_text='Abuja',
            nigerians_eligible=True, verification_source='Provider site')
        self.pending = Opportunity.objects.create(
            title='Checking Grant', slug='checking-grant', category='GRANT',
            provider='Provider B', description='Desc.',
            application_link='https://example.org/hidden',
            deadline=date(2027, 6, 1), status='VERIFICATION_PENDING')
        self.closed = Opportunity.objects.create(
            title='Expired Job', slug='expired-job', category='JOB',
            provider='Provider C', description='Desc.',
            application_link='https://example.org/old',
            deadline=date(2026, 1, 1), status='CLOSED')

    def test_list_includes_verification_pending_without_link(self):
        response = self.client.get(API + 'opportunities/')
        rows = {r['slug']: r for r in response.data['results']}
        self.assertIn('checking-grant', rows)
        self.assertNotIn('expired-job', rows)
        pending = rows['checking-grant']
        self.assertEqual(pending['status'], 'VERIFICATION_PENDING')
        self.assertEqual(pending['external_apply_link'], '')
        self.assertEqual(pending['application_link'], '')
        opened = rows['open-scholarship']
        self.assertEqual(opened['external_apply_link'],
                         'https://example.org/apply')
        self.assertEqual(opened['opens_at'], '2026-12-01')
        self.assertEqual(opened['location_text'], 'Abuja')
        self.assertTrue(opened['nigerians_eligible'])
        self.assertEqual(opened['verification_source'], 'Provider site')

    def test_detail_withholds_pending_link_too(self):
        response = self.client.get(API + 'opportunities/checking-grant/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['external_apply_link'], '')

    def test_archive_lists_closed_only(self):
        response = self.client.get(API + 'opportunities/archive/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['slug'] for r in response.data['results']],
                         ['expired-job'])


class CommunityCurrencyTests(SeededCase):
    def test_new_fields_and_public_label(self):
        CommunityInitiative.objects.create(
            title='Market Cleanup', category='PROJECT', status='PLANNING',
            description='Clean the market.', location_text='Jega market',
            objective='A cleaner market.', start_date=date(2026, 12, 1),
            responsible_team='Jega LGA Chapter', lga=self.lga, ward=self.ward)
        response = self.client.get(API + 'community/')
        row = response.data['results'][0]
        self.assertEqual(row['objective'], 'A cleaner market.')
        self.assertEqual(row['responsible_team'], 'Jega LGA Chapter')
        self.assertEqual(row['public_status_label'], 'Planned')
        self.assertEqual(row['status_label'], 'Planning')
        self.assertEqual(row['lga_name'], 'Jega')
        self.assertEqual(row['ward_name'], 'Jega Ward')


class ImpactExtensionTests(SeededCase):
    def test_groups_and_coverage_added_legacy_kept(self):
        response = self.client.get(API + 'impact/')
        self.assertEqual(response.status_code, 200)
        for key in ('verified_members', 'trusted_reporters',
                    'community_reports', 'opportunities',
                    'impact_communities_reached', 'active_lgas',
                    'active_wards', 'zones_total', 'lgas_total',
                    'wards_total'):
            self.assertIn(key, response.data)
        groups = response.data['groups']
        self.assertEqual([g['name'] for g in groups], [
            'Network Reach', 'Community Development', 'Media & Information',
            'Youth Empowerment', 'Civic Engagement',
            'Organizational Performance'])
        metric = groups[0]['metrics'][0]
        for key in ('key', 'label', 'value', 'recorded', 'definition',
                    'source', 'period', 'last_updated'):
            self.assertIn(key, metric)
        coverage = response.data['coverage']
        self.assertEqual(coverage['totals']['lgas_total'],
                         LGA.objects.count())
        jega = [r for r in coverage['lgas'] if r['lga_name'] == 'Jega']
        self.assertEqual(len(jega), 1)
        self.assertIn('strength', jega[0])


class EmptyRouteSmokeTests(TestCase):
    """Every public route answers anonymously on an empty database
    without a 500."""
    ROUTES = [
        '', 'health/', 'newsroom/', 'opportunities/',
        'opportunities/archive/', 'community/', 'civic/', 'advocacy/',
        'leadership/', 'patrons/', 'impact/', 'promises/', 'projects/',
        'signals/', 'impact-files/', 'archive/', 'lgas/news/',
        'locations/zones/', 'locations/lgas/', 'locations/wards/',
        'roles/', 'content/about/', 'content/contact/', 'content/support/',
        'content/code-of-conduct/', 'content/faq/', 'gallery/', 'schema/',
        'content/home/',
    ]

    def test_routes_do_not_500(self):
        client = APIClient()
        for route in self.ROUTES:
            response = client.get(API + route)
            self.assertLess(response.status_code, 500,
                            f'{route} -> {response.status_code}')
