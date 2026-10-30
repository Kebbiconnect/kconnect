"""Branded email tests (v2.4.3): password reset and membership approval
must go out as professional HTML emails with a button, and approving a
member through decide_application must email the applicant."""
from django.core import mail
from django.test import TestCase, override_settings

from leadership.models import LGA, RoleDefinition, Ward, Zone
from staff.emails import send_account_approved_email, send_password_reset_email
from staff.models import User
from staff.services.member_admin import decide_application


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SITE_URL='https://www.kpn.com.ng')
class BrandedEmailTests(TestCase):
    def _user(self, **kw):
        defaults = dict(username='mail_member', phone='0800', role='GENERAL',
                        status='PENDING', email='member@example.com',
                        first_name='Mail', last_name='Member')
        defaults.update(kw)
        return User.objects.create_user(**defaults)

    def _html(self, message):
        html = [c for c, t in message.alternatives if t == 'text/html']
        self.assertEqual(len(html), 1)
        return html[0]

    def test_password_reset_email_has_button_and_text_fallback(self):
        user = self._user()
        link = 'https://www.kpn.com.ng/account/reset-password/AbC/token-x/'
        sent = send_password_reset_email(user, link)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['member@example.com'])
        self.assertIn('Reset your KPN password', message.subject)
        self.assertIn(link, message.body)  # plain-text part keeps the link
        html = self._html(message)
        self.assertIn('Reset Password', html)
        self.assertIn(f'href="{link}"', html)
        self.assertIn('KEBBI PROGRESSIVE YOUTH NETWORK', html)

    def test_approval_email_has_button_and_role(self):
        role = RoleDefinition.objects.create(title='Ward Coordinator', tier='WARD', seat_number=1)
        user = self._user(role_definition=role, role='WARD')
        sent = send_account_approved_email(user)
        self.assertEqual(sent, 1)
        message = mail.outbox[0]
        self.assertIn('approved', message.subject)
        html = self._html(message)
        self.assertIn('Open Your Dashboard', html)
        self.assertIn('Ward Coordinator', html)
        self.assertIn('https://www.kpn.com.ng/account/dashboard/', html)

    def test_approval_through_decide_application_sends_email(self):
        zone = Zone.objects.create(name='Mail Zone')
        lga = LGA.objects.create(name='Mail LGA', zone=zone)
        Ward.objects.create(name='Mail Ward', lga=lga)
        president_role = RoleDefinition.objects.create(title='President', tier='STATE', seat_number=1)
        lead_role = RoleDefinition.objects.create(title='LGA Network Lead', tier='LGA', seat_number=1)
        approver = User.objects.create_user(
            username='mail_president', phone='0801', role='STATE',
            status='VERIFIED', role_definition=president_role)
        applicant = self._user(username='mail_applicant', role='LGA',
                               status='PENDING', role_definition=lead_role,
                               zone=zone, lga=lga)
        with self.captureOnCommitCallbacks(execute=True):
            decide_application(approver, applicant.pk, 'approve')
        applicant.refresh_from_db()
        self.assertEqual(applicant.status, 'VERIFIED')
        approval_mail = [m for m in mail.outbox if 'approved' in m.subject]
        self.assertEqual(len(approval_mail), 1)
        self.assertEqual(approval_mail[0].to, ['member@example.com'])

    def test_rejection_sends_no_approval_email(self):
        zone = Zone.objects.create(name='Mail Zone 2')
        lga = LGA.objects.create(name='Mail LGA 2', zone=zone)
        president_role = RoleDefinition.objects.create(title='President', tier='STATE', seat_number=1)
        lead_role = RoleDefinition.objects.create(title='LGA Network Lead', tier='LGA', seat_number=1)
        approver = User.objects.create_user(
            username='mail_president2', phone='0802', role='STATE',
            status='VERIFIED', role_definition=president_role)
        applicant = self._user(username='mail_applicant2', role='LGA',
                               status='PENDING', role_definition=lead_role,
                               zone=zone, lga=lga)
        with self.captureOnCommitCallbacks(execute=True):
            decide_application(approver, applicant.pk, 'reject', 'Not eligible')
        self.assertEqual(
            [m for m in mail.outbox if 'approved' in m.subject], [])
