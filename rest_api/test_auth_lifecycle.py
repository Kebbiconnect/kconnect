from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase,override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from leadership.models import RoleDefinition
from staff.models import User

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthLifecycleTests(TestCase):
 def setUp(self):
  self.client=APIClient(); self.role=RoleDefinition.objects.create(title="LGA Adviser",tier="LGA",seat_number=10)
  self.user=User.objects.create_user(username="member",password="StrongPass123!",email="member@example.com",phone="1",role="LGA",status="PENDING",role_definition=self.role)
 def test_login_trims_username_and_allows_pending_status_screen(self):
  response=self.client.post('/api/v1/auth/login/',{'username':'  member  ','password':'StrongPass123!'},format='json')
  self.assertEqual(response.status_code,200)
  self.assertIn('access',response.data); self.assertIn('refresh',response.data)
  self.assertEqual(response.data['user'],{'id':self.user.id,'status':'PENDING','role_title':'LGA Adviser','tier':'LGA'})
 def test_invalid_login_has_stable_error_and_request_id(self):
  response=self.client.post('/api/v1/auth/login/',{'username':'member','password':'wrong'},format='json',HTTP_X_REQUEST_ID='test-request')
  self.assertEqual(response.status_code,401); self.assertEqual(response.data['error']['code'],'authentication_failed')
  self.assertEqual(response.data['request_id'],'test-request'); self.assertEqual(response['X-Request-ID'],'test-request')
 def test_inactive_account_returns_account_dismissed(self):
  self.user.is_active=False; self.user.save(update_fields=['is_active'])
  response=self.client.post('/api/v1/auth/login/',{'username':'member','password':'StrongPass123!'},format='json')
  self.assertEqual(response.status_code,403); self.assertEqual(response.data['error']['code'],'account_dismissed')
 def test_refresh_rotates_and_logout_blacklists(self):
  refresh=str(RefreshToken.for_user(self.user))
  rotated=self.client.post('/api/v1/auth/refresh/',{'refresh':refresh},format='json')
  self.assertEqual(rotated.status_code,200); self.assertIn('refresh',rotated.data); self.assertNotEqual(rotated.data['refresh'],refresh)
  self.client.force_authenticate(self.user)
  logout=self.client.post('/api/v1/auth/logout/',{'refresh':rotated.data['refresh']},format='json')
  self.assertEqual(logout.status_code,204)
  self.client.force_authenticate(None)
  self.assertEqual(self.client.post('/api/v1/auth/refresh/',{'refresh':rotated.data['refresh']},format='json').status_code,401)
 def test_password_reset_is_non_enumerating_and_uses_website_token(self):
  known=self.client.post('/api/v1/auth/password-reset/',{'email':'member@example.com'},format='json')
  unknown=self.client.post('/api/v1/auth/password-reset/',{'email':'unknown@example.com'},format='json')
  self.assertEqual(known.data,unknown.data); self.assertEqual(len(mail.outbox),1)
  uid=urlsafe_base64_encode(force_bytes(self.user.pk)); token=default_token_generator.make_token(self.user)
  confirm=self.client.post('/api/v1/auth/password-reset/confirm/',{'uid':uid,'token':token,'new_password':'NewPass123!'},format='json')
  self.assertEqual(confirm.status_code,200); self.user.refresh_from_db(); self.assertTrue(self.user.check_password('NewPass123!'))
 def test_password_change_requires_current_password(self):
  self.client.force_authenticate(self.user)
  bad=self.client.post('/api/v1/profile/password/',{'old_password':'wrong','new_password':'Another123!'},format='json')
  self.assertEqual(bad.status_code,400); self.assertIn('old_password',bad.data['error']['details']['fields'])
  good=self.client.post('/api/v1/profile/password/',{'old_password':'StrongPass123!','new_password':'Another123!'},format='json')
  self.assertEqual(good.status_code,204)
