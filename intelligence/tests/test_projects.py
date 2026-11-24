"""Phase 5: public project tracker — lifecycle, the reported vs
verified guard, integrity of documented-fact fields, public pages,
the tracking map rollups and the Newsroom menu.

Everything runs on local fixtures — no network.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from editorial.tests.helpers import (
    assistant_media, general_member, make_user, media_director, president,
)
from intelligence import projects as project_service
from intelligence import tracking
from intelligence.models import (
    EventCluster, IntelligenceCategory, Project, ProjectEvidence,
    ProjectMilestone, PublicationLocation, RawPublication,
)
from leadership.models import LGA
from story_intelligence.models import Institution

from .helpers import seed_directory
from .test_processing import make_item, make_source


def audit_director(username='audit_dir'):
    return make_user(username, title='Director of Audit & Accountability')


class ProjectFixture(TestCase):
    def setUp(self):
        seed_directory()
        self.director = media_director('p5_director')
        self.auditor = audit_director()
        self.assistant = assistant_media('p5_assistant')
        self.member = general_member('p5_member')
        self.jega = LGA.objects.get(name='Jega')
        self.argungu = LGA.objects.get(name='Argungu')
        self.institution = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY')

    def make_project(self, actor=None, **fields):
        fields.setdefault('title', 'Reconstruction of Jega Township Roads')
        fields.setdefault('lga', self.jega)
        fields.setdefault('institution', self.institution)
        return project_service.create_project(actor or self.director, **fields)


class ProjectRegistrationTests(ProjectFixture):
    def test_code_allocated_in_story_id_format(self):
        project = self.make_project()
        year = timezone.localdate().year
        self.assertEqual(project.project_code, f'KPN-PRJ-{year}-00001')
        second = self.make_project(title='Another project')
        self.assertEqual(second.project_code, f'KPN-PRJ-{year}-00002')

    def test_registration_writes_opening_milestone_and_audit(self):
        project = self.make_project()
        milestone = project.milestones.get()
        self.assertEqual(milestone.status_after, 'ANNOUNCED')
        from intelligence.models import IntelligenceAudit
        self.assertTrue(IntelligenceAudit.objects.filter(
            action='PROJECT_CREATED', target_id=project.pk).exists())

    def test_create_requires_manage_projects(self):
        with self.assertRaises(PermissionDenied):
            project_service.create_project(self.assistant, title='Nope')
        with self.assertRaises(PermissionDenied):
            project_service.create_project(self.member, title='Nope')

    def test_undocumented_facts_stay_blank(self):
        project = self.make_project()
        self.assertEqual(project.contractor_name, '')
        self.assertIsNone(project.contract_amount)
        self.assertIsNone(project.award_date)
        self.assertIsNone(project.commencement_date)
        self.assertIsNone(project.expected_completion_date)


class ProjectStatusGuardTests(ProjectFixture):
    def test_reported_abandoned_needs_only_manage(self):
        project = self.make_project()
        project_service.set_project_status(
            project, 'REPORTED_ABANDONED', self.auditor,
            note='Residents report the site deserted.')
        project.refresh_from_db()
        self.assertEqual(project.status, 'REPORTED_ABANDONED')
        milestone = project.milestones.order_by('-pk').first()
        self.assertEqual(milestone.status_after, 'REPORTED_ABANDONED')

    def test_verified_abandoned_refused_without_evidence(self):
        project = self.make_project()
        project_service.set_project_status(
            project, 'REPORTED_ABANDONED', self.director)
        with self.assertRaises(project_service.ProjectError):
            project_service.set_project_status(
                project, 'VERIFIED_ABANDONED', self.auditor)
        project.refresh_from_db()
        self.assertEqual(project.status, 'REPORTED_ABANDONED')

    def test_verified_abandoned_refused_for_the_evidence_reporter(self):
        project = self.make_project()
        project_service.add_evidence(
            project, self.director, kind='FIELD_INSPECTION',
            title='Site visit, 12 November',
            verification_state='DOCUMENTED')
        # The director filed the inspection; he cannot verify his own.
        with self.assertRaises(project_service.ProjectError):
            project_service.set_project_status(
                project, 'VERIFIED_ABANDONED', self.director)
        project.refresh_from_db()
        self.assertEqual(project.status, 'ANNOUNCED')

    def test_verified_abandoned_with_basis_and_second_person(self):
        project = self.make_project()
        evidence = project_service.add_evidence(
            project, self.director, kind='FIELD_INSPECTION',
            title='Site visit, 12 November',
            verification_state='DOCUMENTED')
        project_service.set_project_status(
            project, 'VERIFIED_ABANDONED', self.auditor,
            note='Confirmed deserted on inspection.')
        project.refresh_from_db()
        self.assertEqual(project.status, 'VERIFIED_ABANDONED')
        milestone = project.milestones.order_by('-pk').first()
        self.assertEqual(milestone.status_after, 'VERIFIED_ABANDONED')
        self.assertIn('Verification basis', milestone.body)
        evidence.refresh_from_db()
        self.assertEqual(evidence.milestone, milestone)

    def test_completed_verified_uses_the_same_guard(self):
        project = self.make_project()
        project_service.add_evidence(
            project, self.auditor, kind='OFFICIAL_RECORD',
            title='Completion certificate', verification_state='VERIFIED')
        with self.assertRaises(project_service.ProjectError):
            # auditor reported the record; cannot verify it himself
            project_service.set_project_status(
                project, 'COMPLETED_VERIFIED', self.auditor)
        project_service.set_project_status(
            project, 'COMPLETED_VERIFIED', self.director)
        project.refresh_from_db()
        self.assertEqual(project.status, 'COMPLETED_VERIFIED')

    def test_non_qualifying_evidence_kind_does_not_support_verification(self):
        project = self.make_project()
        project_service.add_evidence(
            project, self.director, kind='COMMUNITY_COMPLAINT',
            title='Residents complain of abandonment',
            verification_state='ALLEGATION')
        with self.assertRaises(project_service.ProjectError):
            project_service.set_project_status(
                project, 'VERIFIED_ABANDONED', self.auditor)

    def test_verified_finding_can_only_be_challenged_as_disputed(self):
        project = self.make_project()
        project_service.add_evidence(
            project, self.director, kind='FIELD_INSPECTION',
            title='Site visit', verification_state='DOCUMENTED')
        project_service.set_project_status(
            project, 'VERIFIED_ABANDONED', self.auditor)
        with self.assertRaises(project_service.ProjectError):
            project_service.set_project_status(
                project, 'IN_PROGRESS', self.director)
        project_service.set_project_status(
            project, 'DISPUTED', self.director,
            note='Ministry disputes the finding.')
        project.refresh_from_db()
        self.assertEqual(project.status, 'DISPUTED')

    def test_same_status_is_a_noop(self):
        project = self.make_project()
        before = project.milestones.count()
        project_service.set_project_status(project, 'ANNOUNCED', self.director)
        self.assertEqual(project.milestones.count(), before)


class PublicProjectPagesTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.documented = self.make_project(
            contractor_name='Documented Builders Ltd',
            contract_amount=Decimal('250000000.00'),
            award_date=date(2026, 3, 2),
            expected_completion_date=date(2027, 6, 30),
            sector='INFRASTRUCTURE', category='ROAD')
        self.bare = self.make_project(
            title='Argungu Water Reticulation Scheme', lga=self.argungu,
            category='WATER')
        project_service.set_project_status(
            self.bare, 'REPORTED_ABANDONED', self.director,
            note='Community reports no work since March.')

    def test_list_is_public_and_shows_records(self):
        response = self.client.get(reverse('projects:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reconstruction of Jega Township Roads')
        self.assertContains(response, 'Argungu Water Reticulation Scheme')
        self.assertContains(response, self.documented.project_code)

    def test_stats_computed_from_records(self):
        response = self.client.get(reverse('projects:list'))
        stats = response.context['stats']
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['reported_abandoned'], 1)
        self.assertEqual(stats['verified_abandoned'], 0)
        self.assertEqual(stats['in_progress'], 0)

    def test_filters_narrow_and_invalid_values_are_ignored(self):
        response = self.client.get(
            reverse('projects:list'), {'status': 'REPORTED_ABANDONED'})
        self.assertEqual([p.pk for p in response.context['projects']],
                         [self.bare.pk])
        response = self.client.get(
            reverse('projects:list'), {'lga': self.jega.pk})
        self.assertEqual([p.pk for p in response.context['projects']],
                         [self.documented.pk])
        response = self.client.get(
            reverse('projects:list'), {'sector': 'INFRASTRUCTURE'})
        self.assertEqual([p.pk for p in response.context['projects']],
                         [self.documented.pk])
        response = self.client.get(
            reverse('projects:list'), {'institution': self.institution.pk})
        self.assertEqual(len(response.context['projects']), 2)
        response = self.client.get(
            reverse('projects:list'), {'q': 'Water Reticulation'})
        self.assertEqual([p.pk for p in response.context['projects']],
                         [self.bare.pk])
        response = self.client.get(
            reverse('projects:list'), {'status': 'NOT_A_STATUS'})
        self.assertEqual(len(response.context['projects']), 2)

    def test_blank_facts_render_no_figures(self):
        response = self.client.get(
            reverse('projects:detail', args=[self.bare.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Contract Amount')
        self.assertNotContains(response, 'Contractor (as documented)')
        self.assertNotContains(response, 'Award Date')
        self.assertNotContains(response, '₦')

    def test_documented_facts_render(self):
        response = self.client.get(
            reverse('projects:detail', args=[self.documented.pk]))
        self.assertContains(response, 'Documented Builders Ltd')
        self.assertContains(response, '250,000,000.00')
        self.assertContains(response, 'March 2, 2026')

    def test_private_evidence_never_public(self):
        project_service.add_evidence(
            self.bare, self.director, kind='COMMUNITY_COMPLAINT',
            title='Secret complaint file', is_public=False,
            verification_state='ALLEGATION')
        project_service.add_evidence(
            self.bare, self.director, kind='PROGRESS_REPORT',
            title='Public progress note', is_public=True,
            verification_state='DOCUMENTED')
        response = self.client.get(
            reverse('projects:detail', args=[self.bare.pk]))
        self.assertContains(response, 'Public progress note')
        self.assertNotContains(response, 'Secret complaint file')

    def test_empty_state_is_honest(self):
        # Milestones/evidence PROTECT their project (append-only
        # history by design), so they are cleared first.
        ProjectMilestone.objects.all().delete()
        ProjectEvidence.objects.all().delete()
        Project.objects.all().delete()
        response = self.client.get(reverse('projects:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No projects tracked yet')
        self.assertEqual(response.context['stats']['total'], 0)

    def test_newsroom_menu_links_the_tracker(self):
        response = self.client.get(reverse('projects:list'))
        self.assertContains(response, 'Project Tracker')
        self.assertContains(response, reverse('projects:list'))


class StaffProjectViewsTests(ProjectFixture):
    def test_register_requires_manage_projects(self):
        self.client.force_login(self.assistant)
        response = self.client.get(reverse('intelligence:projects'))
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.member)
        response = self.client.get(reverse('intelligence:project_new'))
        self.assertEqual(response.status_code, 403)

    def test_register_flow_creates_project(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('intelligence:project_new'), {
            'title': 'New General Hospital, Argungu',
            'description': 'A 120-bed hospital.',
            'sector': 'HEALTH', 'category': 'HOSPITAL',
            'institution': self.institution.pk, 'lga': self.argungu.pk,
            'ward': '', 'district': '', 'community': '',
            'contractor_name': '', 'contract_amount': '',
            'award_date': '', 'commencement_date': '',
            'expected_completion_date': '', 'assigned_officer': '',
            'source_url': '',
        })
        project = Project.objects.get(title='New General Hospital, Argungu')
        self.assertRedirects(
            response, reverse('intelligence:project_detail',
                              args=[project.pk]))
        self.assertTrue(project.project_code.startswith('KPN-PRJ-'))

    def test_status_post_refuses_guarded_without_basis(self):
        project = self.make_project()
        self.client.force_login(self.auditor)
        self.client.post(reverse('intelligence:project_status',
                                 args=[project.pk]),
                         {'status': 'VERIFIED_ABANDONED', 'note': ''})
        project.refresh_from_db()
        self.assertEqual(project.status, 'ANNOUNCED')

    def test_evidence_and_milestone_posts(self):
        project = self.make_project()
        self.client.force_login(self.director)
        self.client.post(reverse('intelligence:project_evidence',
                                 args=[project.pk]), {
            'kind': 'FIELD_INSPECTION', 'title': 'Site visit',
            'url': '', 'captured_at': '', 'verification_state': 'DOCUMENTED',
            'is_public': 'on'})
        self.assertEqual(project.evidence.count(), 1)
        self.client.post(reverse('intelligence:project_milestone',
                                 args=[project.pk]), {
            'date': '2026-11-20', 'title': 'Work resumed', 'body': ''})
        self.assertEqual(project.milestones.count(), 2)  # + registration


class ProjectFromDeskUnitTests(ProjectFixture):
    def _verified_cluster(self):
        source = make_source()
        item = make_item(
            source, 'Government Flags Off Argungu Road Repairs',
            text='The government flagged off repairs of the Argungu '
                 'township road on Monday.')
        category = IntelligenceCategory.objects.get(slug='infrastructure-roads')
        cluster = EventCluster.objects.create(
            title=item.title, category=category, primary_lga=self.argungu,
            desk_state='VERIFIED')
        item.cluster = cluster
        item.save(update_fields=['cluster'])
        return cluster

    def test_propose_prefills_from_unit_records_only(self):
        cluster = self._verified_cluster()
        initial = project_service.propose_from_unit(self.director, cluster)
        self.assertEqual(initial['title'], cluster.title)
        self.assertEqual(initial['lga'], self.argungu.pk)

    def test_propose_refused_for_unverified_unit(self):
        cluster = self._verified_cluster()
        cluster.desk_state = 'DISCOVERED'
        cluster.save(update_fields=['desk_state'])
        with self.assertRaises(project_service.ProjectError):
            project_service.propose_from_unit(self.director, cluster)

    def test_created_project_links_back_to_unit(self):
        cluster = self._verified_cluster()
        self.client.force_login(self.director)
        response = self.client.post(
            reverse('intelligence:project_from_unit',
                    kwargs={'kind': 'cluster', 'pk': cluster.pk}), {
                'title': cluster.title, 'description': '',
                'sector': 'INFRASTRUCTURE', 'category': 'ROAD',
                'institution': self.institution.pk,
                'lga': self.argungu.pk, 'ward': '', 'district': '',
                'community': '', 'contractor_name': '',
                'contract_amount': '', 'award_date': '',
                'commencement_date': '', 'expected_completion_date': '',
                'assigned_officer': '', 'source_url': ''})
        project = Project.objects.get(source_cluster=cluster)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(project.source_cluster, cluster)


class TrackingMapProjectTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.make_project(title='Jega Road')
        delayed = self.make_project(title='Jega Market Stalls')
        project_service.set_project_status(delayed, 'DELAYED', self.director)
        reported = self.make_project(
            title='Argungu Water Scheme', lga=self.argungu)
        project_service.set_project_status(
            reported, 'REPORTED_ABANDONED', self.director)

    def test_project_counts_by_lga(self):
        counts = tracking.project_counts_by_lga()
        self.assertEqual(counts[self.jega.pk]['pj_tracked'], 2)
        self.assertEqual(counts[self.jega.pk]['pj_delayed_stalled'], 1)
        self.assertEqual(counts[self.argungu.pk]['pj_reported_abandoned'], 1)
        self.assertEqual(counts[self.argungu.pk]['pj_verified_abandoned'], 0)

    def test_rows_and_totals_carry_project_counts(self):
        rows = tracking.lga_tracking_rows()
        totals = tracking.project_totals_for(rows)
        self.assertEqual(totals['pj_tracked'], 3)
        self.assertEqual(totals['pj_reported_abandoned'], 1)
        jega_row = next(r for r in rows if r['lga'].pk == self.jega.pk)
        self.assertEqual(jega_row['pj_tracked'], 2)

    def test_map_page_shows_project_counts(self):
        self.client.force_login(self.director)
        response = self.client.get(
            reverse('intelligence:map'), {'lga': self.jega.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Projects in Jega')
        self.assertContains(response, 'Jega Road')
        self.assertContains(response, 'projects tracked')
