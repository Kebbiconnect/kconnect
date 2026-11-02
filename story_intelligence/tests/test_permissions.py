"""Story desk permission enforcement — server-side, not template-deep."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import make_user, media_director, president
from leadership.capabilities import capabilities_for
from story_intelligence.models import StoryUpdate

STORY_CAPS = {'MANAGE_STORY_RECORDS', 'PUBLISH_STORY_UPDATES', 'PERFORM_REDACTION'}


class CapabilityGrantTests(TestCase):
    def test_editor_roles_receive_story_capabilities(self):
        for factory, name in [(media_director, 'cap_director'),
                              (president, 'cap_president')]:
            user = factory(name)
            self.assertTrue(STORY_CAPS.issubset(set(capabilities_for(user))),
                            f'{name} missing story capabilities')

    def test_ordinary_leader_has_no_story_capabilities(self):
        writer = make_user('cap_writer', title='Ward Communications Officer',
                           tier='WARD', role='WARD')
        self.assertTrue(STORY_CAPS.isdisjoint(set(capabilities_for(writer))))

    def test_general_member_has_no_story_capabilities(self):
        member = make_user('cap_member', title=None, role='GENERAL')
        self.assertTrue(STORY_CAPS.isdisjoint(set(capabilities_for(member))))


class DeskAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('desk_editor')
        cls.writer = make_user('desk_writer', title='Ward Communications Officer',
                               tier='WARD', role='WARD')
        cls.article = Campaign.objects.create(
            author=cls.editor, title='Desk Story', slug='desk-story',
            status='PUBLISHED', content='Body.', published_at=timezone.now(),
            story_id='KPN-SI-2026-00051')

    def desk_url(self):
        return reverse('story_intelligence:desk', args=[self.article.pk])

    def test_editor_can_open_desk(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.desk_url()).status_code, 200)

    def test_non_editor_leader_is_blocked(self):
        self.client.force_login(self.writer)
        self.assertEqual(self.client.get(self.desk_url()).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.desk_url())
        self.assertEqual(response.status_code, 302)

    def test_non_editor_cannot_add_update(self):
        self.client.force_login(self.writer)
        response = self.client.post(
            reverse('story_intelligence:add_update', args=[self.article.pk]),
            {'kind': 'DEVELOPMENT', 'title': 'Sneaky', 'body': 'Nope'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StoryUpdate.objects.filter(article=self.article).exists())

    def test_non_editor_cannot_open_redaction(self):
        self.client.force_login(self.writer)
        response = self.client.get(
            reverse('story_intelligence:redact', args=[self.article.pk]))
        self.assertEqual(response.status_code, 403)

    def test_editor_can_add_and_publish_update(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse('story_intelligence:add_update', args=[self.article.pk]),
            {'kind': 'DEVELOPMENT', 'title': 'New Development', 'body': 'Facts.'})
        update = StoryUpdate.objects.get(article=self.article)
        self.assertEqual(update.status, 'DRAFT')
        self.client.post(reverse(
            'story_intelligence:publish_update', args=[self.article.pk, update.pk]))
        update.refresh_from_db()
        self.assertEqual(update.status, 'PUBLISHED')
        self.assertIsNotNone(update.published_at)
