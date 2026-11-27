"""Section 26 (27 Nov 2026): General Member registration in the app,
approver notifications for new applications, and member notifications
when new content is published."""
import io
import shutil
import tempfile

from PIL import Image

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from campaigns.models import Campaign
from campaigns.services import publish_campaign
from core.models import Notification
from leadership.models import LGA, RoleDefinition, Ward, Zone
from staff.models import User


class Section26Base(TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix='kpn-s26-')
        self.storage = override_settings(MEDIA_ROOT=self.temp)
        self.storage.enable()
        self.z = Zone.objects.create(name='Kebbi Central')
        self.l = LGA.objects.create(name='Birnin Kebbi', zone=self.z)
        self.w = Ward.objects.create(name='Nasarawa 1', lga=self.l)
        self.z2 = Zone.objects.create(name='Kebbi North')
        self.l2 = LGA.objects.create(name='Argungu', zone=self.z2)
        self.w2 = Ward.objects.create(name='Kokani North', lga=self.l2)
        self.c = APIClient()

    def tearDown(self):
        self.storage.disable()
        shutil.rmtree(self.temp, ignore_errors=True)

    def make_leader(self, username, title, tier, **scope):
        rd, _ = RoleDefinition.objects.get_or_create(tier=tier, title=title, defaults={'seat_number': 1})
        return User.objects.create_user(
            username=username, password='S26-Local-Password-1!', email=f'{username}@example.invalid',
            phone=f's26-{username}', role=tier, status='VERIFIED', role_definition=rd, **scope)

    def image(self, name='s26.png'):
        out = io.BytesIO()
        Image.new('RGB', (16, 16), 'green').save(out, 'PNG')
        return SimpleUploadedFile(name, out.getvalue(), content_type='image/png')

    def register(self, **extra):
        data = {
            'username': 's26_applicant', 'password': 'S26-Local-Password-1!',
            'password_confirm': 'S26-Local-Password-1!', 'email': 'applicant@example.invalid',
            'first_name': 'Amina', 'last_name': 'Bello', 'phone': 's26-applicant-phone',
            'gender': 'F', 'photo': self.image(),
            'zone': self.z.pk, 'lga': self.l.pk, 'ward': self.w.pk,
        }
        data.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.c.post('/api/v1/auth/register/', data, format='multipart')


class GeneralMemberRegistrationTests(Section26Base):
    def test_general_member_application_accepted_without_role(self):
        response = self.register(username='s26_general', general_member='true')
        self.assertEqual(response.status_code, 201, response.content[:400])
        user = User.objects.get(username='s26_general')
        self.assertEqual(user.role, 'GENERAL')
        self.assertIsNone(user.role_definition)
        self.assertEqual(user.status, 'PENDING')
        self.assertEqual(user.ward, self.w)

    def test_registration_without_role_and_without_general_flag_rejected(self):
        response = self.register(username='s26_norole')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username='s26_norole').exists())

    def test_general_member_application_requires_ward(self):
        response = self.register(username='s26_noward', general_member='true', ward='')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username='s26_noward').exists())


class ApproverNotificationTests(Section26Base):
    def setUp(self):
        super().setUp()
        self.president = self.make_leader('s26_president', 'President', 'STATE')
        self.senatorial = self.make_leader('s26_senatorial', 'Senatorial Director', 'ZONAL', zone=self.z)
        self.lga_lead = self.make_leader('s26_lga_lead', 'LGA Network Lead', 'LGA', zone=self.z, lga=self.l)
        self.other_lga_lead = self.make_leader('s26_other_lead', 'LGA Network Lead', 'LGA', zone=self.z2, lga=self.l2)
        self.ward_lead = self.make_leader('s26_ward_lead', 'Ward Community Lead', 'WARD', zone=self.z, lga=self.l, ward=self.w)

    def notified(self, user, applicant):
        return Notification.objects.filter(user=user, event='MEMBER_APPLIED', target_id=applicant.id).exists()

    def test_ward_application_notifies_responsible_leaders_only(self):
        rd, _ = RoleDefinition.objects.get_or_create(tier='WARD', title='Ward Programmes Officer', defaults={'seat_number': 3})
        response = self.register(username='s26_ward_applicant', role_definition=rd.pk)
        self.assertEqual(response.status_code, 201, response.content[:400])
        applicant = User.objects.get(username='s26_ward_applicant')
        self.assertTrue(self.notified(self.president, applicant))
        self.assertTrue(self.notified(self.senatorial, applicant))
        self.assertTrue(self.notified(self.lga_lead, applicant))
        self.assertFalse(self.notified(self.other_lga_lead, applicant))
        # Ward leaders cannot decide applications, so they are not notified.
        self.assertFalse(self.notified(self.ward_lead, applicant))
        note = Notification.objects.get(user=self.lga_lead, event='MEMBER_APPLIED', target_id=applicant.id)
        self.assertIn('Ward Programmes Officer', note.message)
        self.assertIn('Nasarawa 1', note.message)
        self.assertIn('Birnin Kebbi', note.message)

    def test_general_application_notifies_responsible_leaders(self):
        response = self.register(username='s26_general_applicant', general_member='true')
        self.assertEqual(response.status_code, 201, response.content[:400])
        applicant = User.objects.get(username='s26_general_applicant')
        self.assertTrue(self.notified(self.president, applicant))
        self.assertTrue(self.notified(self.lga_lead, applicant))
        self.assertFalse(self.notified(self.other_lga_lead, applicant))
        note = Notification.objects.get(user=self.president, event='MEMBER_APPLIED', target_id=applicant.id)
        self.assertIn('General Member', note.message)


class PublishNotificationTests(Section26Base):
    def test_publish_campaign_notifies_members_once(self):
        member = User.objects.create_user(
            username='s26_member', password='S26-Local-Password-1!', email='m@example.invalid',
            phone='s26-member', role='GENERAL', status='VERIFIED', zone=self.z, lga=self.l, ward=self.w)
        author = self.make_leader('s26_author', 'President', 'STATE')
        article = Campaign.objects.create(
            author=author, title='S26 publish notice story', slug='s26-publish-notice-story',
            content='Body', category='GENERAL', status='PENDING')
        with self.captureOnCommitCallbacks(execute=True):
            publish_campaign(article, author)
        self.assertEqual(
            Notification.objects.filter(user=member, event='NEW_ARTICLE', target_id=article.id).count(), 1)
        # Republishing an already-live article does not notify again.
        with self.captureOnCommitCallbacks(execute=True):
            publish_campaign(article, author)
        self.assertEqual(
            Notification.objects.filter(user=member, event='NEW_ARTICLE', target_id=article.id).count(), 1)
