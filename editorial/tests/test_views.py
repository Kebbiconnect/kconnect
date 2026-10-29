from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from editorial.models import Control, Item, Job, Source
from editorial.tests.helpers import general_member, make_user, media_director


class ViewAccessTests(TestCase):
    def setUp(self):
        self.director = media_director()
        self.member = general_member()
        self.item = Item.objects.create(key='v1', kind='NEWS', title='Queue story', state='REVIEW',
                                        draft={'title': 'Queue story', 'body': 'Draft body'})

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('editorial:index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_general_member_sees_no_scoped_items(self):
        # The workspace opens for verified members, but items_for() scopes
        # them to nothing: no queue content leaks.
        self.client.force_login(self.member)
        response = self.client.get(reverse('editorial:index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Queue story')

    def test_director_sees_index_and_brain_queue(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('editorial:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Queue story')

    def test_detail_save_draft_flow(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('editorial:detail', args=[self.item.pk]), {
            'version': self.item.version, 'title': 'Edited title', 'body': 'Edited body',
            'category': 'GENERAL', 'notes': ''})
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.draft['body'], 'Edited body')

    def test_detail_of_invisible_item_404s_for_member(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('editorial:detail', args=[self.item.pk]))
        self.assertEqual(response.status_code, 404)


class ControlAndSourceTests(TestCase):
    def setUp(self):
        self.director = media_director()
        self.president = make_user('v_pres', title='President')

    def test_manager_can_pause_and_resume(self):
        self.client.force_login(self.director)
        self.client.post(reverse('editorial:control'), {'enabled': 'yes'})
        self.assertTrue(Control.objects.get(pk=1).enabled)
        self.client.post(reverse('editorial:control'), {'enabled': 'no'})
        self.assertFalse(Control.objects.get(pk=1).enabled)

    def test_non_manager_cannot_control(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse('editorial:control'), {'enabled': 'yes'})
        self.assertEqual(response.status_code, 403)

    def test_manager_can_add_source(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('editorial:source_new'), {
            'name': 'Official feed', 'kind': 'NEWS', 'url': 'https://example.com/feed.xml',
            'feed': 'on', 'allowed_hosts': '', 'keywords': 'Kebbi', 'max_items': '3', 'enabled': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Source.objects.filter(name='Official feed', enabled=True).exists())

    def test_source_form_rejects_http(self):
        self.client.force_login(self.director)
        self.client.post(reverse('editorial:source_new'), {
            'name': 'Bad feed', 'kind': 'NEWS', 'url': 'http://example.com/feed.xml',
            'allowed_hosts': '', 'keywords': 'Kebbi', 'max_items': '3'})
        self.assertFalse(Source.objects.filter(name='Bad feed').exists())

    def test_non_manager_cannot_add_source(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse('editorial:source_new'))
        self.assertEqual(response.status_code, 403)


class RetryTests(TestCase):
    def test_failed_job_can_be_requeued_by_scoped_user(self):
        director = media_director()
        item = Item.objects.create(key='v-retry', kind='NEWS', title='Retry story', state='WAITING')
        job = Job.objects.create(key='generate:v-retry', kind='GENERATE', item=item,
                                 state='FAILED', attempts=3, error_code='boom')
        self.client.force_login(director)
        response = self.client.post(reverse('editorial:retry', args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.state, 'QUEUED')
        self.assertEqual(job.attempts, 0)


@override_settings(KPN_EDITORIAL_DAILY_DRAFTS=99)
class SystemCheckTests(TestCase):
    def test_out_of_range_daily_drafts_fails_check(self):
        from django.core.checks import Error
        from editorial.checks import editorial_configuration
        errors = editorial_configuration(None)
        self.assertTrue(any(isinstance(e, Error) for e in errors))

    @override_settings(KPN_EDITORIAL_DAILY_DRAFTS=5)
    def test_valid_configuration_passes(self):
        from editorial.checks import editorial_configuration
        self.assertEqual(editorial_configuration(None), [])
