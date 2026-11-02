"""Web-newsroom regression tests (Phase 0, KPN Media v2.5.0).

Written BEFORE the Phase 1 changes to pin the existing behaviour of the
campaigns web views: create / edit / submit / publish / return / delete /
article detail / newsroom list. Publish, edit and detail expectations must
survive Phase 1 unchanged; the delete expectations for protected articles
are updated in Phase 1 (archive-instead-of-delete, owner spec 2026-11-01).
"""
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import make_user, media_director

BODY_JSON = {'blocks': [{'type': 'paragraph', 'data': {'text': 'Body text.'}}]}


def make_article(author, title='Test Article', status='DRAFT', **kw):
    kw.setdefault('slug', Campaign.objects.count() and
                  f'{title.lower().replace(" ", "-")}-{Campaign.objects.count()}' or
                  title.lower().replace(' ', '-'))
    kw.setdefault('content', 'Body text.')
    kw.setdefault('content_json', BODY_JSON)
    return Campaign.objects.create(author=author, title=title, status=status, **kw)


class NewsroomWebRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('reg_editor')
        cls.writer = make_user('reg_writer', title='Ward Communications Officer',
                               tier='WARD', role='WARD')
        cls.other_writer = make_user('reg_other', title='LGA Communications Officer',
                                     tier='LGA', role='LGA')

    # ── create ────────────────────────────────────────────────────────────
    def test_write_article_creates_draft(self):
        self.client.force_login(self.writer)
        response = self.client.post(reverse('campaigns:write_article'), {
            'title': 'A Brand New Story',
            'subheadline': '',
            'category': 'COMMUNITY',
            'verification_status': 'DEVELOPING',
            'reporter_credit': 'KPN_REPORTER',
            'location': '',
            'meta_description': '',
            'content_json': json.dumps(BODY_JSON),
        })
        self.assertEqual(response.status_code, 302)
        article = Campaign.objects.get(title='A Brand New Story')
        self.assertEqual(article.status, 'DRAFT')
        self.assertEqual(article.author, self.writer)
        self.assertTrue(article.slug)

    def test_write_article_requires_leader(self):
        member = make_user('reg_member', title=None, role='GENERAL')
        self.client.force_login(member)
        response = self.client.get(reverse('campaigns:write_article'))
        self.assertEqual(response.status_code, 302)  # bounced to dashboard

    # ── edit ──────────────────────────────────────────────────────────────
    def test_author_edits_own_draft(self):
        article = make_article(self.writer, title='Editable Draft')
        self.client.force_login(self.writer)
        response = self.client.post(reverse('campaigns:edit_article', args=[article.pk]), {
            'title': 'Editable Draft Revised',
            'subheadline': '',
            'category': 'COMMUNITY',
            'verification_status': 'DEVELOPING',
            'reporter_credit': 'KPN_REPORTER',
            'location': '',
            'meta_description': '',
            'content_json': json.dumps(BODY_JSON),
        })
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.title, 'Editable Draft Revised')
        self.assertEqual(article.status, 'DRAFT')

    def test_editor_edit_of_published_article_stays_published(self):
        article = make_article(self.writer, title='Live Story', status='PUBLISHED',
                               published_at=timezone.now())
        self.client.force_login(self.editor)
        response = self.client.post(reverse('campaigns:edit_article', args=[article.pk]), {
            'title': 'Live Story Corrected',
            'subheadline': '',
            'category': 'COMMUNITY',
            'verification_status': 'CONFIRMED',
            'reporter_credit': 'KPN_EDITORIAL',
            'location': '',
            'meta_description': '',
            'content_json': json.dumps(BODY_JSON),
        })
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.title, 'Live Story Corrected')
        self.assertEqual(article.status, 'PUBLISHED')

    def test_author_cannot_edit_published_article(self):
        article = make_article(self.writer, title='Locked Live', status='PUBLISHED',
                               published_at=timezone.now())
        self.client.force_login(self.writer)
        response = self.client.post(reverse('campaigns:edit_article', args=[article.pk]), {
            'title': 'Should Not Stick',
            'category': 'COMMUNITY',
            'verification_status': 'DEVELOPING',
            'reporter_credit': 'KPN_REPORTER',
            'content_json': json.dumps(BODY_JSON),
        })
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.title, 'Locked Live')

    def test_author_cannot_edit_someone_elses_draft(self):
        article = make_article(self.other_writer, title='Not Yours')
        self.client.force_login(self.writer)
        response = self.client.get(reverse('campaigns:edit_article', args=[article.pk]))
        self.assertEqual(response.status_code, 404)

    # ── submit for review ─────────────────────────────────────────────────
    def test_submit_draft_moves_to_pending(self):
        article = make_article(self.writer, title='Ready Draft')
        self.client.force_login(self.writer)
        response = self.client.post(reverse('campaigns:submit_for_review', args=[article.pk]))
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')

    def test_submit_empty_body_rejected(self):
        article = Campaign.objects.create(
            author=self.writer, title='Empty One', slug='empty-one',
            content='', content_json=None, status='DRAFT')
        self.client.force_login(self.writer)
        self.client.post(reverse('campaigns:submit_for_review', args=[article.pk]))
        article.refresh_from_db()
        self.assertEqual(article.status, 'DRAFT')

    def test_submit_published_is_friendly_noop(self):
        article = make_article(self.writer, title='Already Live', status='PUBLISHED',
                               published_at=timezone.now())
        self.client.force_login(self.editor)
        response = self.client.post(reverse('campaigns:submit_for_review', args=[article.pk]))
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')

    # ── review queue / publish / return ───────────────────────────────────
    def test_review_queue_editor_only(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(reverse('campaigns:review_queue')).status_code, 200)
        self.client.force_login(self.writer)
        response = self.client.get(reverse('campaigns:review_queue'))
        self.assertEqual(response.status_code, 302)

    def test_publish_article_from_queue(self):
        article = make_article(self.writer, title='Pending Story', status='PENDING')
        self.client.force_login(self.editor)
        response = self.client.post(reverse('campaigns:publish_article', args=[article.pk]))
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'PUBLISHED')
        self.assertEqual(article.approved_by, self.editor)
        self.assertIsNotNone(article.published_at)

    def test_publish_requires_editor_role(self):
        article = make_article(self.writer, title='Pending Two', status='PENDING')
        self.client.force_login(self.writer)
        self.client.post(reverse('campaigns:publish_article', args=[article.pk]))
        article.refresh_from_db()
        self.assertEqual(article.status, 'PENDING')

    def test_publish_rejects_non_pending(self):
        article = make_article(self.writer, title='Draft Not Pending')
        self.client.force_login(self.editor)
        self.client.post(reverse('campaigns:publish_article', args=[article.pk]))
        article.refresh_from_db()
        self.assertEqual(article.status, 'DRAFT')

    def test_return_article_with_note(self):
        article = make_article(self.writer, title='Needs Work', status='PENDING')
        self.client.force_login(self.editor)
        response = self.client.post(reverse('campaigns:return_article', args=[article.pk]),
                                    {'rejection_note': 'Please add sources.'})
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'REJECTED')
        self.assertEqual(article.rejection_note, 'Please add sources.')

    # ── delete (pre-Phase-1 behaviour; protected-article cases change) ────
    def test_author_deletes_own_draft(self):
        article = make_article(self.writer, title='Disposable Draft')
        self.client.force_login(self.writer)
        response = self.client.post(reverse('campaigns:delete_article', args=[article.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Campaign.objects.filter(pk=article.pk).exists())

    def test_author_cannot_delete_published(self):
        article = make_article(self.writer, title='Author Live', status='PUBLISHED',
                               published_at=timezone.now())
        self.client.force_login(self.writer)
        self.client.post(reverse('campaigns:delete_article', args=[article.pk]))
        self.assertTrue(Campaign.objects.filter(pk=article.pk).exists())

    def test_author_cannot_delete_others_article(self):
        article = make_article(self.other_writer, title='Someone Elses Draft')
        self.client.force_login(self.writer)
        response = self.client.post(reverse('campaigns:delete_article', args=[article.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Campaign.objects.filter(pk=article.pk).exists())

    # ── public display ────────────────────────────────────────────────────
    def test_article_detail_published_is_public(self):
        article = make_article(self.writer, title='Public Story', status='PUBLISHED',
                               published_at=timezone.now())
        response = self.client.get(reverse('campaigns:article_detail', args=[article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Public Story')

    def test_article_detail_draft_404_for_anonymous(self):
        article = make_article(self.writer, title='Hidden Draft')
        response = self.client.get(reverse('campaigns:article_detail', args=[article.slug]))
        self.assertEqual(response.status_code, 404)

    def test_article_detail_draft_visible_to_author(self):
        article = make_article(self.writer, title='My Hidden Draft')
        self.client.force_login(self.writer)
        response = self.client.get(reverse('campaigns:article_detail', args=[article.slug]))
        self.assertEqual(response.status_code, 200)

    def test_newsroom_lists_published_only(self):
        make_article(self.writer, title='Listed Live One', status='PUBLISHED',
                     published_at=timezone.now())
        make_article(self.writer, title='Unlisted Draft One')
        response = self.client.get(reverse('campaigns:newsroom'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Listed Live One')
        self.assertNotContains(response, 'Unlisted Draft One')
