"""backfill_story_ids: idempotency and preservation of existing records."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from datetime import datetime, timezone as dt_timezone

from campaigns.models import Campaign
from editorial.tests.helpers import media_director
from story_intelligence.models import StorySequence


class BackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('backfill_editor')

    def _published(self, title, published_at, **kw):
        kw.setdefault('slug', title.lower().replace(' ', '-'))
        kw.setdefault('content', f'Content of {title}')
        return Campaign.objects.create(
            author=self.editor, title=title, status='PUBLISHED',
            published_at=published_at, **kw)

    def test_backfill_assigns_oldest_first_per_year(self):
        old = datetime(2025, 3, 1, 10, 0, tzinfo=dt_timezone.utc)
        older = datetime(2025, 1, 1, 10, 0, tzinfo=dt_timezone.utc)
        newer = datetime(2026, 2, 1, 10, 0, tzinfo=dt_timezone.utc)
        a_newer = self._published('Newer 2025', old)
        a_older = self._published('Older 2025', older)
        a_2026 = self._published('Story 2026', newer)
        call_command('backfill_story_ids', stdout=StringIO())
        a_older.refresh_from_db(); a_newer.refresh_from_db(); a_2026.refresh_from_db()
        self.assertEqual(a_older.story_id, 'KPN-SI-2025-00001')
        self.assertEqual(a_newer.story_id, 'KPN-SI-2025-00002')
        self.assertEqual(a_2026.story_id, 'KPN-SI-2026-00001')

    def test_backfill_is_idempotent(self):
        at = datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc)
        a = self._published('Idempotent Story', at)
        b = self._published('Idempotent Two', at)
        call_command('backfill_story_ids', stdout=StringIO())
        a.refresh_from_db(); b.refresh_from_db()
        first_ids = (a.story_id, b.story_id)
        seq_after_first = StorySequence.objects.get(year=2026).last_number
        call_command('backfill_story_ids', stdout=StringIO())
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.story_id, b.story_id), first_ids)
        self.assertEqual(StorySequence.objects.get(year=2026).last_number, seq_after_first)

    def test_backfill_preserves_article_fields(self):
        at = datetime(2026, 4, 4, 8, 30, tzinfo=dt_timezone.utc)
        a = self._published('Preserve Me', at, subheadline='Deck',
                            category='HEALTH', verification_status='VERIFIED',
                            location='Argungu')
        before = (a.title, a.slug, a.content, a.subheadline, a.category,
                  a.verification_status, a.location, a.status, a.published_at,
                  a.author_id, a.created_at, a.updated_at)
        call_command('backfill_story_ids', stdout=StringIO())
        a.refresh_from_db()
        after = (a.title, a.slug, a.content, a.subheadline, a.category,
                 a.verification_status, a.location, a.status, a.published_at,
                 a.author_id, a.created_at, a.updated_at)
        self.assertEqual(before, after)
        self.assertIsNotNone(a.story_id)

    def test_backfill_skips_drafts_and_existing_ids(self):
        at = datetime(2026, 5, 5, 8, 0, tzinfo=dt_timezone.utc)
        draft = Campaign.objects.create(
            author=self.editor, title='Still Draft', slug='still-draft',
            status='DRAFT', content='x')
        existing = self._published('Has Id Already', at, story_id='KPN-SI-2026-00042')
        call_command('backfill_story_ids', stdout=StringIO())
        draft.refresh_from_db(); existing.refresh_from_db()
        self.assertIsNone(draft.story_id)
        self.assertEqual(existing.story_id, 'KPN-SI-2026-00042')

    def test_backfill_dry_run_changes_nothing(self):
        at = datetime(2026, 6, 6, 8, 0, tzinfo=dt_timezone.utc)
        a = self._published('Dry Run Story', at)
        out = StringIO()
        call_command('backfill_story_ids', '--dry-run', stdout=out)
        a.refresh_from_db()
        self.assertIsNone(a.story_id)
        self.assertIn('DRY RUN', out.getvalue())
        self.assertFalse(StorySequence.objects.exists())

    def test_coverage_command_reports_complete(self):
        at = datetime(2026, 7, 7, 8, 0, tzinfo=dt_timezone.utc)
        self._published('Covered Story', at)
        call_command('backfill_story_ids', stdout=StringIO())
        out = StringIO()
        call_command('check_story_id_coverage', stdout=out)
        self.assertIn('Coverage complete', out.getvalue())

    def test_coverage_command_is_advisory_when_incomplete(self):
        # Since v2.9.1 the coverage report runs inside release_migrate
        # on every deploy. Its contract is advisory: it must REPORT a
        # gap (exit 0, nothing raised, nothing changed) and never fail
        # the release — a gap left by a still-draining old instance
        # self-heals on the next deploy's backfill.
        at = datetime(2026, 8, 8, 8, 0, tzinfo=dt_timezone.utc)
        a = self._published('Uncovered Story', at)
        out = StringIO()
        result = call_command('check_story_id_coverage', stdout=out)
        self.assertIsNone(result)
        text = out.getvalue()
        self.assertIn('Without a Story ID: 1', text)
        self.assertIn('MISSING', text)
        a.refresh_from_db()
        self.assertIsNone(a.story_id)
