from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from staff.models import User

class RecoveryBaselineTests(TestCase):
    def setUp(self): self.client=APIClient()
    def test_public_api_routes_resolve_without_auth(self):
        for path in ('/api/v1/newsroom/','/api/v1/opportunities/','/api/v1/community/','/api/v1/civic/','/api/v1/advocacy/','/api/v1/patrons/','/api/v1/impact/','/api/v1/roles/'):
            self.assertNotIn(self.client.get(path).status_code,(401,403),path)
    def test_auth_me_requires_authentication(self):
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code,401)
    def test_general_member_self_registration_remains_unavailable(self):
        response=self.client.post('/api/v1/auth/register/',{'username':'general','password':'Strong-pass-123','password_confirm':'Strong-pass-123','role':'GENERAL'},format='json')
        self.assertEqual(response.status_code,400)
        self.assertFalse(User.objects.filter(username='general').exists())
