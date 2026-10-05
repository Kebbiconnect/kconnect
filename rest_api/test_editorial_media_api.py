from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from leadership.models import RoleDefinition
from staff.models import User
from campaigns.models import Campaign
from media.models import MediaItem

class EditorialMediaApiTests(TestCase):
 def setUp(self):
  self.client=APIClient()
  self.writer_role=RoleDefinition.objects.create(title='LGA Adviser',tier='LGA',seat_number=10)
  self.editor_role=RoleDefinition.objects.create(title='Director of Media & Communications',tier='STATE',seat_number=18)
  self.assistant_role=RoleDefinition.objects.create(title='Assistant Director of Media & Communications',tier='STATE',seat_number=19)
  self.writer=self.user('writer','LGA',self.writer_role); self.editor=self.user('editor','STATE',self.editor_role); self.assistant=self.user('assistant','STATE',self.assistant_role)
 def user(self,name,tier,role,status='VERIFIED'): return User.objects.create_user(username=name,password='x',phone='1',role=tier,status=status,role_definition=role)
 def auth(self,user): self.client.force_authenticate(user)
 def test_draft_submit_publish_flow(self):
  self.auth(self.writer); created=self.client.post('/api/v1/articles/mine/',{'title':'Real update','content':'Source-backed article','category':'GENERAL'},format='json')
  self.assertEqual(created.status_code,201); article=Campaign.objects.get(pk=created.data['id']); self.assertEqual(article.status,'DRAFT')
  submitted=self.client.post(f'/api/v1/articles/{article.id}/submit/',{},format='json'); self.assertEqual(submitted.status_code,200)
  self.auth(self.editor); queue=self.client.get('/api/v1/articles/review/'); self.assertEqual(queue.data['count'],1)
  published=self.client.post(f'/api/v1/articles/{article.id}/decision/',{'action':'publish'},format='json'); self.assertEqual(published.status_code,200); self.assertEqual(published.data['status'],'PUBLISHED')
 def test_return_requires_editor_note(self):
  article=Campaign.objects.create(title='Pending',slug='pending',content='Body',author=self.writer,status='PENDING')
  self.auth(self.editor); bad=self.client.post(f'/api/v1/articles/{article.id}/decision/',{'action':'return'},format='json'); self.assertEqual(bad.status_code,400)
  good=self.client.post(f'/api/v1/articles/{article.id}/decision/',{'action':'return','note':'Verify source'},format='json'); self.assertEqual(good.data['status'],'REJECTED')
 def test_verified_publicity_upload_is_not_blocked_by_obsolete_approved_status(self):
  self.auth(self.assistant); upload=SimpleUploadedFile('photo.jpg',b'jpeg-data',content_type='image/jpeg')
  response=self.client.post('/api/v1/media/mine/',{'title':'Field photo','description':'Activity','media_type':'PHOTO','file':upload},format='multipart')
  self.assertEqual(response.status_code,201); self.assertEqual(response.data['status'],'PENDING')
 def test_director_auto_approves_and_can_review_assistant_media(self):
  item=MediaItem.objects.create(title='Review',description='',media_type='PHOTO',file=SimpleUploadedFile('review.jpg',b'x'),uploaded_by=self.assistant,status='PENDING')
  self.auth(self.editor); decision=self.client.post(f'/api/v1/media/{item.id}/decision/',{'action':'approve'},format='json'); self.assertEqual(decision.data['status'],'APPROVED')
  upload=SimpleUploadedFile('director.jpg',b'x',content_type='image/jpeg'); own=self.client.post('/api/v1/media/mine/',{'title':'Director','media_type':'PHOTO','file':upload},format='multipart'); self.assertEqual(own.data['status'],'APPROVED')
 def test_non_publicity_role_cannot_upload_media(self):
  self.auth(self.writer); response=self.client.post('/api/v1/media/mine/',{},format='multipart'); self.assertEqual(response.status_code,403)
