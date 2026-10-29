import io
import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from editorial.models import Item, Job


class BrainOutboxCommandTests(TestCase):
    def test_outbox_prints_waiting_items_as_json(self):
        Item.objects.create(key='cmd-1', kind='NEWS', title='Waiting story',
                            original={'title': 'Waiting story', 'text': 'Evidence'})
        out = io.StringIO()
        call_command('brain_outbox', stdout=out)
        rows = json.loads(out.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Waiting story')

    def test_outbox_writes_file(self):
        Item.objects.create(key='cmd-2', kind='NEWS', title='File story',
                            original={'title': 'File story', 'text': 'Evidence'})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.json')
            call_command('brain_outbox', output=path)
            with open(path) as fh:
                rows = json.load(fh)
        self.assertEqual(rows[0]['title'], 'File story')


class BrainInboxCommandTests(TestCase):
    def _inbox_file(self, payload):
        fh = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(payload, fh)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_inbox_accepts_valid_draft(self):
        item = Item.objects.create(key='cmd-3', kind='NEWS', title='Story',
                                   original={'title': 'Story', 'text': 'Evidence'})
        path = self._inbox_file([{'item_id': item.pk, 'version': item.version,
                                  'draft': {'title': 'Story', 'body': 'Written by Muse.'}}])
        call_command('brain_inbox', path)
        item.refresh_from_db()
        self.assertEqual(item.state, 'REVIEW')
        self.assertEqual(item.draft['body'], 'Written by Muse.')

    def test_inbox_rejection_raises_and_changes_nothing(self):
        item = Item.objects.create(key='cmd-4', kind='NEWS', title='Story',
                                   original={'title': 'Story', 'text': 'Evidence'})
        path = self._inbox_file([{'item_id': item.pk, 'version': item.version + 9,
                                  'draft': {'title': 'Story', 'body': 'Nope.'}}])
        with self.assertRaises(CommandError):
            call_command('brain_inbox', path)
        item.refresh_from_db()
        self.assertEqual(item.state, 'WAITING')

    def test_inbox_rejects_invalid_json(self):
        fh = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        fh.write('this is not json')
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        with self.assertRaises(CommandError):
            call_command('brain_inbox', fh.name)


class TestBrainLoopCommandTests(TestCase):
    def test_creates_synthetic_waiting_item_and_job(self):
        call_command('test_brain_loop')
        item = Item.objects.get(original__synthetic=True)
        self.assertEqual(item.state, 'WAITING')
        self.assertTrue(Job.objects.filter(item=item, kind='GENERATE').exists())


@override_settings(KPN_EDITORIAL_ENABLED=False)
class RunEditorialCommandTests(TestCase):
    def test_reports_paused_when_disabled(self):
        out = io.StringIO()
        call_command('run_editorial', max_jobs=5, max_seconds=60, stdout=out)
        self.assertIn('disabled or paused', out.getvalue())

    def test_bounds_are_validated(self):
        with self.assertRaises(CommandError):
            call_command('run_editorial', max_jobs=0, max_seconds=60)
        with self.assertRaises(CommandError):
            call_command('run_editorial', max_jobs=5, max_seconds=10)
