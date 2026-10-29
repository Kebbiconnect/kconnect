from django.test import TestCase

from core.models import Report
from editorial import access
from editorial.models import Item
from editorial.tests.helpers import assistant_media, general_member, make_user, media_director, president


class AccessFlagTests(TestCase):
    def test_media_director_is_editor_and_manager(self):
        user = media_director()
        self.assertTrue(access.active(user))
        self.assertTrue(access.editor(user))
        self.assertTrue(access.manager(user))

    def test_president_is_editor_not_manager(self):
        user = president()
        self.assertTrue(access.editor(user))
        self.assertFalse(access.manager(user))

    def test_general_member_is_active_but_not_editor(self):
        user = general_member()
        self.assertTrue(access.active(user))
        self.assertFalse(access.editor(user))
        self.assertFalse(access.manager(user))

    def test_pending_user_is_not_active(self):
        user = make_user('ed_pending', title='President', status='PENDING')
        self.assertFalse(access.active(user))
        self.assertFalse(access.editor(user))

    def test_anonymous_is_not_active(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(access.active(AnonymousUser()))


class ItemScopingTests(TestCase):
    def setUp(self):
        self.director = media_director()
        self.president = president()
        self.member = general_member()
        self.news = Item.objects.create(key='n1', kind='NEWS', title='News item')
        self.caption = Item.objects.create(key='c1', kind='CAPTION', title='Caption item')

    def _report_item(self, submitted_to, key='r1'):
        author = make_user(f'author_{key}', title=None, role='LGA')
        report = Report.objects.create(
            title='Ward report', report_type='WARD_TO_LGA', content='Body',
            submitted_by=author, submitted_to=submitted_to, status='SUBMITTED')
        return Item.objects.create(key=key, kind='REPORT_EDIT', title='Ward report', report=report)

    def test_member_sees_nothing(self):
        self.assertEqual(access.items_for(self.member).count(), 0)

    def test_editor_sees_news_and_caption_but_not_reports(self):
        item = self._report_item(self.president)
        seen = set(access.items_for(assistant_media()).values_list('pk', flat=True))
        self.assertIn(self.news.pk, seen)
        self.assertIn(self.caption.pk, seen)
        self.assertNotIn(item.pk, seen)

    def test_assigned_supervisor_sees_own_report_item(self):
        item = self._report_item(self.president)
        seen = set(access.items_for(self.president).values_list('pk', flat=True))
        self.assertIn(item.pk, seen)

    def test_other_supervisor_does_not_see_report_item(self):
        other = make_user('ed_other_sup', title='General Secretary')
        item = self._report_item(self.president)
        seen = set(access.items_for(other).values_list('pk', flat=True))
        self.assertNotIn(item.pk, seen)

    def test_full_access_sees_all_report_items(self):
        item = self._report_item(self.president)
        seen = set(access.items_for(self.director).values_list('pk', flat=True))
        self.assertIn(item.pk, seen)
