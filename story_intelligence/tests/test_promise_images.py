"""Promise Tracker images (owner instruction, 2026-11-24): a promise
can carry its own image, uploaded by staff on the promise desk form
before the promise appears on the tracker. The public tracker shows
the promise's own image first, then falls back to the featured image
of a linked published story, then to the sector-icon tile — exactly
the behaviour that existed before the field was added."""
import os
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from story_intelligence.models import Institution, Promise

# A valid 1x1 transparent GIF — enough for ImageField validation.
GIF_1PX = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff'
    b'!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00'
    b'\x02\x02D\x01\x00;'
)

FILE_STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


def make_promise(editor, institution, **kw):
    defaults = {
        'institution': institution,
        'title': 'A tracked promise',
        'description': 'What was promised.',
        'announced_on': timezone.localdate() - timedelta(days=5),
        'created_by': editor,
    }
    defaults.update(kw)
    return Promise.objects.create(**defaults)


class PromiseImageFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('pimg_editor')
        cls.institution = Institution.objects.create(
            name='Kebbi State Ministry of Works', kind='MINISTRY')


class PromiseImageFormTests(PromiseImageFixture):
    """The desk form accepts, stores and replaces the tracker image."""

    def setUp(self):
        self.tmp_media = tempfile.mkdtemp(prefix='kpn-test-media-')
        self.addCleanup(shutil.rmtree, self.tmp_media, ignore_errors=True)
        stack = override_settings(
            MEDIA_ROOT=self.tmp_media, MEDIA_URL='/media/',
            STORAGES=FILE_STORAGES)
        stack.enable()
        self.addCleanup(stack.disable)

    def _create_data(self, **extra):
        data = {
            'institution': self.institution.pk,
            'title': 'Rebuild the Argungu township road',
            'description': 'Full rehabilitation of the township road.',
            'announced_by': 'The Governor',
            'announced_on': '2026-11-01',
            'source_name': 'Kebbi Radio',
            'source_url': 'https://example.org/announcement',
            'deadline': '',
            'next_check_date': '',
        }
        data.update(extra)
        return data

    def test_create_form_stores_uploaded_image(self):
        self.client.force_login(self.editor)
        upload = SimpleUploadedFile(
            'road.gif', GIF_1PX, content_type='image/gif')
        response = self.client.post(
            reverse('story_intelligence:promise_create'),
            self._create_data(image=upload))
        promise = Promise.objects.get(
            title='Rebuild the Argungu township road')
        self.assertRedirects(
            response,
            reverse('story_intelligence:promise_detail_desk',
                    args=[promise.pk]))
        self.assertTrue(promise.image.name.startswith('promises/'))
        self.assertTrue(
            os.path.exists(os.path.join(self.tmp_media, promise.image.name)))

    def test_create_without_image_still_works(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('story_intelligence:promise_create'),
            self._create_data())
        promise = Promise.objects.get(
            title='Rebuild the Argungu township road')
        self.assertRedirects(
            response,
            reverse('story_intelligence:promise_detail_desk',
                    args=[promise.pk]))
        self.assertFalse(promise.image)

    def test_edit_form_replaces_image(self):
        promise = make_promise(self.editor, self.institution)
        promise.image.save(
            'old.gif', SimpleUploadedFile('old.gif', GIF_1PX), save=True)
        old_name = promise.image.name
        self.client.force_login(self.editor)
        upload = SimpleUploadedFile(
            'new.gif', GIF_1PX, content_type='image/gif')
        response = self.client.post(
            reverse('story_intelligence:promise_save', args=[promise.pk]),
            self._create_data(title=promise.title, image=upload))
        self.assertRedirects(
            response,
            reverse('story_intelligence:promise_detail_desk',
                    args=[promise.pk]))
        promise.refresh_from_db()
        self.assertNotEqual(promise.image.name, old_name)
        self.assertTrue(promise.image.name.startswith('promises/'))
        self.assertTrue(
            os.path.exists(os.path.join(self.tmp_media, promise.image.name)))

    def test_edit_form_shows_current_image_preview(self):
        promise = make_promise(self.editor, self.institution)
        promise.image = 'promises/preview.gif'
        promise.save()
        self.client.force_login(self.editor)
        response = self.client.get(
            reverse('story_intelligence:promise_detail_desk',
                    args=[promise.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Current tracker image', html)
        self.assertIn('/media/promises/preview.gif', html)
        self.assertIn('enctype="multipart/form-data"', html)


class PromiseImageDisplayTests(PromiseImageFixture):
    """Public precedence: own image → linked story image → icon tile."""

    def _story_with_image(self, slug='road-story'):
        article = Campaign.objects.create(
            author=self.editor, title='Road Story', slug=slug,
            status='PUBLISHED', content='Body.',
            published_at=timezone.now())
        article.featured_image = 'campaigns/story-photo.jpg'
        article.save()
        return article

    def test_display_image_prefers_own_image(self):
        promise = make_promise(self.editor, self.institution)
        promise.image = 'promises/own-photo.jpg'
        promise.save()
        promise.stories.add(self._story_with_image())
        self.assertEqual(promise.display_image.name, 'promises/own-photo.jpg')

    def test_display_image_falls_back_to_story_image(self):
        promise = make_promise(self.editor, self.institution)
        promise.stories.add(self._story_with_image())
        self.assertEqual(
            promise.display_image.name, 'campaigns/story-photo.jpg')

    def test_display_image_none_without_any_image(self):
        promise = make_promise(self.editor, self.institution)
        self.assertIsNone(promise.display_image)

    def test_card_renders_own_image(self):
        promise = make_promise(
            self.editor, self.institution, title='Own image promise',
            sector='INFRASTRUCTURE')
        promise.image = 'promises/own-photo.jpg'
        promise.save()
        promise.stories.add(self._story_with_image())
        response = self.client.get(reverse('promises:list'))
        html = response.content.decode()
        self.assertIn('/media/promises/own-photo.jpg', html)
        self.assertNotIn('/media/campaigns/story-photo.jpg', html)

    def test_card_falls_back_to_story_image(self):
        promise = make_promise(
            self.editor, self.institution, title='Story image promise',
            sector='INFRASTRUCTURE')
        promise.stories.add(self._story_with_image())
        response = self.client.get(reverse('promises:list'))
        html = response.content.decode()
        self.assertIn('/media/campaigns/story-photo.jpg', html)

    def test_card_falls_back_to_icon_tile(self):
        make_promise(
            self.editor, self.institution, title='No image promise',
            sector='HEALTH')
        response = self.client.get(reverse('promises:list'))
        html = response.content.decode()
        self.assertIn('pt-thumb-fallback', html)
        self.assertIn('fa-heart-pulse', html)

    def test_detail_shows_image_when_set(self):
        promise = make_promise(
            self.editor, self.institution, title='Detailed promise')
        promise.image = 'promises/detail-photo.jpg'
        promise.save()
        response = self.client.get(
            reverse('promises:detail', args=[promise.pk]))
        html = response.content.decode()
        self.assertIn('<figure class="pt-detail-image">', html)
        self.assertIn('/media/promises/detail-photo.jpg', html)
        self.assertIn('alt="Detailed promise"', html)

    def test_detail_shows_story_image_as_fallback(self):
        promise = make_promise(
            self.editor, self.institution, title='Story fallback detail')
        promise.stories.add(self._story_with_image())
        response = self.client.get(
            reverse('promises:detail', args=[promise.pk]))
        html = response.content.decode()
        self.assertIn('<figure class="pt-detail-image">', html)
        self.assertIn('/media/campaigns/story-photo.jpg', html)

    def test_detail_unchanged_without_any_image(self):
        promise = make_promise(
            self.editor, self.institution, title='Plain detail promise')
        response = self.client.get(
            reverse('promises:detail', args=[promise.pk]))
        html = response.content.decode()
        self.assertNotIn('<figure class="pt-detail-image">', html)
        self.assertIn('Plain detail promise', html)
