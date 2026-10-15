from django.test import TestCase, override_settings
from leadership.models import RoleDefinition
from staff.models import User
from telegram_integration.models import TelegramMembership


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class DashboardGateTests(TestCase):
    def setUp(self):
        role = RoleDefinition.objects.create(
            title="President", tier="STATE", seat_number=1
        )
        self.user = User.objects.create_user(
            username="test_president", password="TestPass123!",
            phone="synthetic", status="VERIFIED", role="STATE",
            role_definition=role,
        )

    def test_anonymous_direct_dashboard_requires_login(self):
        response = self.client.get("/account/dashboards/president/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/account/login/", response.url)

    def test_entry_and_direct_dashboard_share_telegram_gate(self):
        self.client.force_login(self.user)
        for path in ("/account/dashboard/", "/account/dashboards/president/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "telegram_integration/gate.html")
            self.assertTemplateNotUsed(response, "staff/dashboards/president.html")

    def test_verified_telegram_membership_allows_direct_dashboard(self):
        TelegramMembership.objects.create(
            user=self.user, telegram_user_id=999000001,
            is_verified=True, telegram_status="member",
        )
        self.client.force_login(self.user)
        response = self.client.get("/account/dashboards/president/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/dashboards/president.html")

    def test_lost_telegram_verification_restores_gate(self):
        TelegramMembership.objects.create(
            user=self.user, telegram_user_id=999000002,
            is_verified=False, telegram_status="left",
        )
        self.client.force_login(self.user)
        response = self.client.get("/account/dashboards/president/")
        self.assertTemplateUsed(response, "telegram_integration/gate.html")