"""Emergency redaction: text replaced, files verifiably destroyed,
and neither the audit trail nor the public notice copies the secret.
The Cloudinary destroy call is exercised through a test double — this
verifies the code path and response handling, not the live provider.
"""
import base64
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from story_intelligence.models import (
    Claim, Correction, EvidenceRecord, StoryAudit, StoryUpdate,
)
from story_intelligence.services import (
    REDACTION_MARKER, RedactionError, perform_redaction,
)

SECRET = 'SECRET-NAME-XYZZY-12345'
PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


class RedactionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('redact_editor')

    def setUp(self):
        self.article = Campaign.objects.create(
            author=self.editor, title='Redaction Story', slug='redaction-story',
            status='PUBLISHED', content=f'Body mentioning {SECRET}.',
            published_at=timezone.now(), story_id='KPN-SI-2026-00061')

    def test_claim_text_redacted_and_audit_is_clean(self):
        claim = Claim.objects.create(
            article=self.article, text=f'{SECRET} said the road is done.',
            status='DEVELOPING', noted_by=self.editor)
        result = perform_redaction(
            actor=self.editor, target_type='claim', target_id=claim.pk,
            reason_category='PERSONAL_DATA')
        claim.refresh_from_db()
        self.assertEqual(claim.text, REDACTION_MARKER)
        correction = Correction.objects.get(pk=result['correction_id'])
        self.assertEqual(correction.kind, 'REDACTION')
        self.assertNotIn(SECRET, correction.text)
        audit = StoryAudit.objects.get(action='REDACTION_PERFORMED')
        self.assertNotIn(SECRET, json.dumps(audit.detail))
        self.assertEqual(audit.detail['reason_category'], 'PERSONAL_DATA')

    def test_update_body_redacted(self):
        update = StoryUpdate.objects.create(
            article=self.article, title='U', body=f'Update naming {SECRET}',
            status='PUBLISHED', published_at=timezone.now(), author=self.editor)
        perform_redaction(actor=self.editor, target_type='update',
                          target_id=update.pk, reason_category='SAFETY')
        update.refresh_from_db()
        self.assertEqual(update.body, REDACTION_MARKER)

    def test_article_body_redacted(self):
        perform_redaction(actor=self.editor, target_type='article',
                          target_id=self.article.pk, reason_category='LEGAL')
        self.article.refresh_from_db()
        self.assertEqual(self.article.content, REDACTION_MARKER)
        self.assertNotIn(SECRET, json.dumps(self.article.content_json))

    def test_evidence_file_destroyed_and_verified(self):
        evidence = EvidenceRecord.objects.create(
            article=self.article, title='Leaked document', kind='DOCUMENT',
            file=SimpleUploadedFile('leak.txt', b'secret-bytes'),
            added_by=self.editor)
        with mock.patch('cloudinary.uploader.destroy',
                        return_value={'result': 'ok'}) as destroy:
            result = perform_redaction(
                actor=self.editor, target_type='evidence',
                target_id=evidence.pk, reason_category='PERSONAL_DATA')
        self.assertEqual(destroy.call_count, 1)
        self.assertEqual(result['file_removal'], 'ok')
        evidence.refresh_from_db()
        self.assertFalse(evidence.file)
        self.assertEqual(evidence.url, '')
        self.assertEqual(evidence.title, 'Redacted evidence')

    def test_evidence_destroy_failure_changes_nothing(self):
        evidence = EvidenceRecord.objects.create(
            article=self.article, title='Sensitive document', kind='DOCUMENT',
            description=f'About {SECRET}',
            file=SimpleUploadedFile('sensitive.txt', b'secret-bytes'),
            added_by=self.editor)
        with mock.patch('cloudinary.uploader.destroy',
                        return_value={'result': 'error'}):
            with self.assertRaises(RedactionError):
                perform_redaction(
                    actor=self.editor, target_type='evidence',
                    target_id=evidence.pk, reason_category='PERSONAL_DATA')
        evidence.refresh_from_db()
        self.assertTrue(evidence.file)
        self.assertEqual(evidence.title, 'Sensitive document')
        self.assertFalse(Correction.objects.filter(article=self.article).exists())
        self.assertFalse(StoryAudit.objects.filter(action='REDACTION_PERFORMED').exists())

    def test_article_featured_image_destroyed(self):
        self.article.featured_image.save(
            'redact-me.png', SimpleUploadedFile('redact-me.png', PNG_1PX), save=True)
        with mock.patch('cloudinary.uploader.destroy',
                        return_value={'result': 'ok'}) as destroy:
            result = perform_redaction(
                actor=self.editor, target_type='article',
                target_id=self.article.pk, reason_category='SAFETY')
        self.assertEqual(destroy.call_count, 1)
        self.assertEqual(result['file_removal'], 'ok')
        self.article.refresh_from_db()
        self.assertFalse(self.article.featured_image)
