"""App download page tests (owner instruction 2026-11-27, §24).

The Download App page (/download-app/) offers the Android APK only
when the signed release file actually sits in the static/app/ slot;
the size and version it shows are the file's own. The endpoint
(/download-app/apk/) streams that file as an attachment and 404s
while the slot is empty. The site footer links to the page.

The staticfiles storage is swapped for a temp-directory filesystem
storage so both states are exercised without touching real static
files.
"""

import os
import shutil
import tempfile
from unittest.mock import patch

from django.core.files.storage import FileSystemStorage
from django.template.defaultfilters import filesizeformat
from django.test import TestCase
from django.urls import reverse

APK_BYTES = b'PK\x03\x04' + b'kpn-test-apk' * 64


class DownloadAppStorageMixin:
    """Point core.views.staticfiles_storage at a temp directory."""

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        storage = FileSystemStorage(location=self.tmpdir)
        patcher = patch('core.views.staticfiles_storage', storage)
        patcher.start()
        self.addCleanup(patcher.stop)

    def add_apk(self, version='2.0.8'):
        app_dir = os.path.join(self.tmpdir, 'app')
        os.makedirs(app_dir, exist_ok=True)
        with open(os.path.join(app_dir, 'kpn-app.apk'), 'wb') as fh:
            fh.write(APK_BYTES)
        if version is not None:
            with open(os.path.join(app_dir, 'VERSION.txt'), 'w') as fh:
                fh.write(version + '\n')


class DownloadPageAbsentTests(DownloadAppStorageMixin, TestCase):
    def test_page_200_with_notice_and_no_button(self):
        response = self.client.get(reverse('core:download_app'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Download the KPN App', html)
        self.assertIn('Android download coming to this page shortly', html)
        # No download button and no endpoint link while the slot is empty.
        self.assertNotIn(reverse('core:download_app_apk'), html)
        self.assertNotIn('Download for Android', html)

    def test_stores_shown_as_coming_soon_not_links(self):
        response = self.client.get(reverse('core:download_app'))
        html = response.content.decode('utf-8')
        self.assertIn('Google Play', html)
        self.assertIn('App Store', html)
        self.assertIn('Coming Soon', html)
        self.assertNotIn('play.google.com', html)
        self.assertNotIn('apps.apple.com', html)

    def test_endpoint_404_while_apk_absent(self):
        response = self.client.get(reverse('core:download_app_apk'))
        self.assertEqual(response.status_code, 404)


class DownloadPagePresentTests(DownloadAppStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.add_apk()

    def test_page_shows_button_size_and_version(self):
        response = self.client.get(reverse('core:download_app'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn(reverse('core:download_app_apk'), html)
        self.assertIn('Download for Android', html)
        self.assertIn('Version 2.0.8', html)
        self.assertIn(filesizeformat(len(APK_BYTES)), html)
        self.assertNotIn('coming to this page shortly', html)

    def test_endpoint_streams_apk_as_attachment(self):
        response = self.client.get(reverse('core:download_app_apk'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.android.package-archive')
        disposition = response['Content-Disposition']
        self.assertIn('attachment', disposition)
        self.assertIn('kpn-app.apk', disposition)
        body = b''.join(response.streaming_content)
        self.assertEqual(body, APK_BYTES)


class DownloadPageNoVersionTests(DownloadAppStorageMixin, TestCase):
    def test_page_without_version_file_shows_size_only(self):
        self.add_apk(version=None)
        response = self.client.get(reverse('core:download_app'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Download for Android', html)
        self.assertIn(filesizeformat(len(APK_BYTES)), html)
        self.assertNotIn('Version', html)


class FooterDownloadLinkTests(TestCase):
    def test_footer_links_to_download_page(self):
        response = self.client.get(reverse('core:about'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Download Android App', html)
        self.assertIn(reverse('core:download_app'), html)
