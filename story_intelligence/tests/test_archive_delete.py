"""Archive-instead-of-delete (Phase 1): services, web views, REST API."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import Campaign
from campaigns.services import (
    ProtectedArticleError, archive_campaign, delete_campaign, restore_campaign,
)
from editorial.tests.helpers import make_user, media_director
from story_intelligence.models import StoryUpdate


def make(author, title, status='DRAFT', **kw):
    kw.setdefault('slug', title.lower().replace(' ', '-'))
    kw.setdefault('content', 'Body.')
    return Campaign.objects.create(author=author, title=title, status=status, **kw)


class ServiceGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('arch_editor')

    def test_plain_draft_can_be_deleted(self):
        a = make(self.editor, 'Plain Draft')
        delete_campaign(a)
        self.assertFalse(Campaign.objects.filter(pk=a.pk).exists())

    def test_published_article_cannot_be_deleted(self):
        a = make(self.editor, 'Live One', status='PUBLISHED',
                 published_at=timezone.now(), story_id='KPN-SI-2026-00011')
        with self.assertRaises(ProtectedArticleError):
            delete_campaign(a)
        self.assertTrue(Campaign.objects.filter(pk=a.pk).exists())

    def test_draft_with_story_id_cannot_be_deleted(self):
        a = make(self.editor, 'Draft With Id', story_id='KPN-SI-2026-00012')
        with self.assertRaises(ProtectedArticleError):
            delete_campaign(a)

    def test_draft_with_story_records_cannot_be_deleted(self):
        a = make(self.editor, 'Draft With Update')
        StoryUpdate.objects.create(article=a, title='U', body='B', author=self.editor)
        with self.assertRaises(ProtectedArticleError):
            delete_campaign(a)

    def test_archive_and_restore_preserve_story_id_and_history(self):
        a = make(self.editor, 'Archive Me', status='PUBLISHED',
                 published_at=timezone.now(), story_id='KPN-SI-2026-00013')
        StoryUpdate.objects.create(
            article=a, title='Kept Update', body='B', status='PUBLISHED',
            published_at=timezone.now(), author=self.editor)
        archive_campaign(a, actor=self.editor)
        a.refresh_from_db()
        self.assertEqual(a.status, 'ARCHIVED')
        self.assertEqual(a.story_id, 'KPN-SI-2026-00013')
        restore_campaign(a, actor=self.editor)
        a.refresh_from_db()
        self.assertEqual(a.status, 'PUBLISHED')
        self.assertEqual(a.story_id, 'KPN-SI-2026-00013')
        self.assertEqual(a.story_updates.count(), 1)


class WebArchiveDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('web_arch_editor')

    def setUp(self):
        self.client.force_login(self.editor)

    def test_editor_delete_of_published_is_refused(self):
        a = make(self.editor, 'Web Live', status='PUBLISHED',
                 published_at=timezone.now(), story_id='KPN-SI-2026-00021')
        response = self.client.post(reverse('campaigns:delete_article', args=[a.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Campaign.objects.filter(pk=a.pk).exists())

    def test_editor_archives_and_restores_via_web(self):
        a = make(self.editor, 'Web Archive', status='PUBLISHED',
                 published_at=timezone.now(), story_id='KPN-SI-2026-00022')
        self.client.post(reverse('campaigns:archive_article', args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.status, 'ARCHIVED')
        # Archived article is no longer public (check as an anonymous reader;
        # leaders can still preview non-published articles).
        self.client.logout()
        response = self.client.get(reverse('campaigns:article_detail', args=[a.slug]))
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.editor)
        self.client.post(reverse('campaigns:restore_article', args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.status, 'PUBLISHED')
        self.assertEqual(a.story_id, 'KPN-SI-2026-00022')


class ApiArchiveDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.writer = make_user('api_arch_writer', title='Ward Communications Officer',
                               tier='WARD', role='WARD')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.writer)

    def test_author_deletes_own_plain_draft(self):
        a = make(self.writer, 'Api Plain Draft')
        response = self.client.delete(f'/api/v1/articles/mine/{a.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Campaign.objects.filter(pk=a.pk).exists())

    def test_author_cannot_delete_draft_with_story_id(self):
        a = make(self.writer, 'Api Draft With Id', story_id='KPN-SI-2026-00031')
        response = self.client.delete(f'/api/v1/articles/mine/{a.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Campaign.objects.filter(pk=a.pk).exists())

    def test_author_archives_and_restores_via_api(self):
        a = make(self.writer, 'Api Archive', status='PUBLISHED',
                 published_at=timezone.now(), story_id='KPN-SI-2026-00032')
        response = self.client.post(f'/api/v1/articles/mine/{a.pk}/archive/')
        self.assertEqual(response.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.status, 'ARCHIVED')
        response = self.client.post(f'/api/v1/articles/mine/{a.pk}/restore/')
        self.assertEqual(response.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.status, 'PUBLISHED')
        self.assertEqual(a.story_id, 'KPN-SI-2026-00032')
