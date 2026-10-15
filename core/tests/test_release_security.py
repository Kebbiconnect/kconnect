import os,secrets,subprocess,sys
from unittest.mock import patch
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings, RequestFactory
from campaigns.templatetags.campaign_extras import render_article_blocks,clean_article_html
from telegram_integration.webhook import process_webhook_update

class ContentSecurityTests(SimpleTestCase):
    def test_stored_article_blocks_do_not_execute_html(self):
        result=str(render_article_blocks({'blocks':[{'type':'paragraph','data':{'text':'<b>Allowed</b><img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)">Bad link</a>'}},{'type':'header','data':{'level':'not-a-number','text':'Malformed'}}]}))
        self.assertIn('<b>Allowed</b>',result)
        for marker in ('onerror=','<script','javascript:'):self.assertNotIn(marker,result)
    def test_legacy_html_is_cleaned_and_untrusted_embeds_removed(self):
        result=str(clean_article_html('<p>Safe</p><iframe src="https://untrusted.example/path"></iframe><img src="javascript:alert(1)" onload="alert(2)">'))
        self.assertIn('<p>Safe</p>',result);self.assertNotIn('https://untrusted.example',result);self.assertNotIn('javascript:',result);self.assertNotIn('onload',result)
    def test_malformed_block_structures_do_not_crash_renderer(self):
        self.assertEqual(str(render_article_blocks({'blocks':'bad'})),'')
        self.assertEqual(str(render_article_blocks({'blocks':[None,{'data':'bad'}]})),'')
    @override_settings(TELEGRAM_WEBHOOK_SECRET='')
    def test_webhook_fails_closed_without_secret(self):
        request=RequestFactory().post('/synthetic-webhook/',data='{}',content_type='application/json')
        self.assertFalse(process_webhook_update(request))
    @override_settings(TELEGRAM_WEBHOOK_SECRET='synthetic-only')
    def test_webhook_requires_secret_and_dictionary_payload(self):
        rf=RequestFactory()
        self.assertFalse(process_webhook_update(rf.post('/',data='{}',content_type='application/json')))
        self.assertFalse(process_webhook_update(rf.post('/',data='[]',content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='synthetic-only')))
        self.assertTrue(process_webhook_update(rf.post('/',data='{}',content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='synthetic-only')))

class ProductionConfigurationTests(SimpleTestCase):
    def load_config(self,**values):
        env=os.environ.copy()
        env.update(SESSION_SECRET=secrets.token_urlsafe(48),KPN_ENV='production',DEBUG='False',DATABASE_URL='',CLOUDINARY_CLOUD_NAME='',CLOUDINARY_API_KEY='',CLOUDINARY_API_SECRET='',SITE_URL='https://www.kpn.com.ng')
        env.update(values)
        return subprocess.run([sys.executable,'-c','import dotenv,decouple;dotenv.load_dotenv=lambda *a,**k:None;decouple.config=decouple.Config(decouple.RepositoryEmpty());import KPN.settings'],cwd=settings.BASE_DIR,env=env,capture_output=True,text=True,timeout=30)
    def test_production_cannot_fallback_to_sqlite(self):
        result=self.load_config();self.assertNotEqual(result.returncode,0);self.assertIn('DATABASE_URL must',result.stderr)
        result=self.load_config(DATABASE_URL='sqlite:///:memory:');self.assertIn('Production requires PostgreSQL',result.stderr)
    def test_production_cannot_fallback_to_local_uploads(self):
        result=self.load_config(DATABASE_URL='postgresql://synthetic@localhost/synthetic?sslmode=require')
        self.assertNotEqual(result.returncode,0);self.assertIn('All Cloudinary credentials',result.stderr)
    def test_production_rejects_debug_and_unencrypted_database(self):
        self.assertIn('DEBUG must',self.load_config(DEBUG='True').stderr)
        self.assertIn('must require TLS',self.load_config(DATABASE_URL='postgresql://synthetic@localhost/synthetic?sslmode=disable').stderr)

class PublicAPIReleaseTests(TestCase):
    def test_public_content_endpoints_are_accessible_without_login(self):
        for route in ('newsroom/','opportunities/','community/','civic/','advocacy/','leadership/','patrons/','impact/','locations/zones/','locations/lgas/','locations/wards/','content/home/','content/about/','content/contact/','content/support/','content/code-of-conduct/','content/faq/','gallery/'):
            with self.subTest(route=route):self.assertEqual(self.client.get('/api/v1/'+route).status_code,200)
    def test_member_and_management_data_require_authentication(self):
        for route in ('members/','members/pending/','auth/me/','profile/','management/catalog/','notifications/summary/'):
            with self.subTest(route=route):self.assertIn(self.client.get('/api/v1/'+route).status_code,(401,403))
