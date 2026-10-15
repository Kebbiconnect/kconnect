from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from staff.models import User


class PasswordChangeTests(TestCase):
    url = "/api/v1/profile/password/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="test_member", password="OriginalPass123!",
            phone="synthetic", role="GENERAL", status="VERIFIED",
        )
        self.client = APIClient()

    def authenticate(self):
        token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_anonymous_request_is_rejected_without_server_error(self):
        response = self.client.post(self.url, {
            "old_password": "OriginalPass123!", "new_password": "UpdatedPass123!"
        }, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "authentication_failed")

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 401)

    def test_current_password_must_match(self):
        self.authenticate()
        response = self.client.post(self.url, {
            "old_password": "wrong", "new_password": "UpdatedPass123!"
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("old_password", response.data["error"]["details"]["fields"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OriginalPass123!"))

    def test_missing_new_password_is_validation_error(self):
        self.authenticate()
        response = self.client.post(self.url, {
            "old_password": "OriginalPass123!"
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data["error"]["details"]["fields"])

    def test_null_password_is_validation_error(self):
        self.authenticate()
        response = self.client.post(self.url, {
            "old_password": "OriginalPass123!", "new_password": None
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_configured_password_policy_is_used(self):
        self.authenticate()
        response = self.client.post(self.url, {
            "old_password": "OriginalPass123!", "new_password": "short"
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_success_preserves_existing_response_contract(self):
        self.authenticate()
        response = self.client.post(self.url, {
            "old_password": "OriginalPass123!", "new_password": "UpdatedPass123!"
        }, format="json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("UpdatedPass123!"))

    def test_password_whitespace_is_not_trimmed(self):
        self.authenticate()
        password = " UpdatedPass123! "
        response = self.client.post(self.url, {
            "old_password": "OriginalPass123!", "new_password": password
        }, format="json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))