"""Story ID allocation: uniqueness, format, concurrency, rollback."""
import re
import threading
import time

from django.db import IntegrityError, OperationalError, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from campaigns.models import Campaign
from campaigns.services import publish_campaign
from editorial.tests.helpers import media_director
from story_intelligence.models import StorySequence
from story_intelligence.services import allocate_story_id

STORY_ID_RE = re.compile(r'^KPN-SI-\d{4}-\d{5}$')


def make_article(author, title, status='DRAFT', **kw):
    kw.setdefault('slug', title.lower().replace(' ', '-'))
    kw.setdefault('content', 'Body.')
    return Campaign.objects.create(author=author, title=title, status=status, **kw)


class AllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = media_director('alloc_editor')

    def test_allocate_formats_and_increments(self):
        a = make_article(self.editor, 'First Story')
        b = make_article(self.editor, 'Second Story')
        year = timezone.now().year
        self.assertEqual(allocate_story_id(a), f'KPN-SI-{year}-00001')
        self.assertEqual(allocate_story_id(b), f'KPN-SI-{year}-00002')
        self.assertTrue(STORY_ID_RE.match(a.story_id))

    def test_allocate_is_idempotent_for_same_article(self):
        a = make_article(self.editor, 'Only Story')
        first = allocate_story_id(a)
        self.assertEqual(allocate_story_id(a), first)
        seq = StorySequence.objects.get(year=timezone.now().year)
        self.assertEqual(seq.last_number, 1)

    def test_publish_campaign_sets_fields_and_story_id(self):
        a = make_article(self.editor, 'Pending Story', status='PENDING')
        publish_campaign(a, self.editor)
        a.refresh_from_db()
        self.assertEqual(a.status, 'PUBLISHED')
        self.assertEqual(a.approved_by, self.editor)
        self.assertIsNotNone(a.published_at)
        self.assertTrue(STORY_ID_RE.match(a.story_id))

    def test_allocation_failure_rolls_back_publish(self):
        """If the allocated ID collides, the publish transaction rolls
        back: the article stays PENDING with no ID and the sequence is
        unchanged — recoverable, never half-published."""
        year = timezone.now().year
        taken = f'KPN-SI-{year}-00001'
        make_article(self.editor, 'Already Has Id', status='PUBLISHED',
                     story_id=taken, published_at=timezone.now())
        StorySequence.objects.create(year=year, last_number=0)
        pending = make_article(self.editor, 'Will Collide', status='PENDING')
        with self.assertRaises(IntegrityError):
            publish_campaign(pending, self.editor)
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'PENDING')
        self.assertIsNone(pending.story_id)
        self.assertEqual(StorySequence.objects.get(year=year).last_number, 0)


class ConcurrentAllocationTests(TransactionTestCase):
    def test_concurrent_publishes_get_unique_ids(self):
        editor = media_director('conc_editor')
        articles = [
            Campaign.objects.create(
                author=editor, title=f'Concurrent {i}', slug=f'concurrent-{i}',
                status='PENDING', content='Body.')
            for i in range(8)
        ]
        errors = []

        def work(pk):
            try:
                for attempt in range(12):
                    try:
                        publish_campaign(Campaign.objects.get(pk=pk), editor)
                        break
                    except OperationalError:
                        time.sleep(0.05 * (attempt + 1))
            except Exception as exc:  # collected and asserted below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=work, args=(a.pk,)) for a in articles]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        ids = list(Campaign.objects.values_list('story_id', flat=True))
        self.assertEqual(len(ids), 8)
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 8)
        self.assertTrue(all(STORY_ID_RE.match(i) for i in ids))
