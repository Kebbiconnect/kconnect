from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from editorial import worker
from editorial.models import Control, Item, Job, Source


@override_settings(KPN_EDITORIAL_ENABLED=True)
class WorkerTests(TestCase):
    def setUp(self):
        Control.objects.create(pk=1, enabled=True)
        self.source = Source.objects.create(name='Src', kind='NEWS', url='https://example.com/feed', enabled=True)

    def _patches(self):
        return [
            mock.patch.object(worker, 'discover', return_value=1),
            mock.patch.object(worker, 'link_checks', return_value=0),
            mock.patch.object(worker, 'deadline_reminders', return_value=None),
            mock.patch.object(worker, 'briefings', return_value=None),
        ]

    def _run(self, **kw):
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            return worker.run(**kw)
        finally:
            for p in patches:
                p.stop()

    def test_discovers_via_scheduled_job(self):
        done = self._run(max_jobs=5, max_seconds=60)
        self.assertGreaterEqual(done, 1)
        job = Job.objects.get(kind='DISCOVER')
        self.assertEqual(job.state, 'DONE')

    def test_generate_jobs_are_never_executed_by_worker(self):
        item = Item.objects.create(key='w-gen', kind='NEWS', title='Waiting story')
        Job.objects.create(key='generate:w-gen', kind='GENERATE', item=item)
        self._run(max_jobs=5, max_seconds=60)
        job = Job.objects.get(kind='GENERATE')
        self.assertEqual(job.state, 'QUEUED')
        item.refresh_from_db()
        self.assertEqual(item.state, 'WAITING')
        self.assertEqual(item.draft, {})

    def test_lease_blocks_second_worker(self):
        token = worker.acquire()
        with self.assertRaises(worker.Paused):
            worker.acquire()
        Control.objects.filter(pk=1).update(lease_token='', lease_until=None)

    def test_stale_running_job_is_recovered(self):
        job = Job.objects.create(key='discover:stale', kind='DISCOVER', source=self.source,
                                 state='RUNNING', attempts=1,
                                 started_at=timezone.now() - timedelta(minutes=30))
        self._run(max_jobs=5, max_seconds=60)
        job.refresh_from_db()
        self.assertEqual(job.state, 'DONE')

    def test_retry_limit_marks_failed(self):
        job = Job.objects.create(key='discover:stale3', kind='DISCOVER', source=self.source,
                                 state='RUNNING', attempts=3,
                                 started_at=timezone.now() - timedelta(minutes=30))
        token = worker.acquire()
        try:
            claimed = worker.claim(token)
        finally:
            Control.objects.filter(pk=1).update(lease_token='', lease_until=None)
        job.refresh_from_db()
        self.assertEqual(job.state, 'FAILED')
        self.assertEqual(job.error_code, 'retry_limit')


@override_settings(KPN_EDITORIAL_ENABLED=True)
class PausedWorkerTests(TestCase):
    def test_control_disabled_pauses(self):
        Control.objects.create(pk=1, enabled=False)
        with self.assertRaises(worker.Paused):
            worker.run(max_jobs=5, max_seconds=60)


@override_settings(KPN_EDITORIAL_ENABLED=False)
class EnvDisabledWorkerTests(TestCase):
    def test_env_flag_pauses(self):
        Control.objects.create(pk=1, enabled=True)
        with self.assertRaises(worker.Paused):
            worker.run(max_jobs=5, max_seconds=60)
