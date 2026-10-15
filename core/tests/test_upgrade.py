import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import timedelta
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from core.models import Opportunity
from staff.models import Announcement, User


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class ConfigurationTests(SimpleTestCase):
    def test_missing_secret_fails_closed(self):
        env = os.environ.copy()
        env.pop("SESSION_SECRET", None)
        result = subprocess.run(
            [sys.executable, "-c",
             "import decouple, dotenv; "
             "dotenv.load_dotenv=lambda *a, **k: None; "
             "decouple.config=decouple.Config(decouple.RepositoryEmpty()); "
             "import KPN.settings"],
            cwd=settings.BASE_DIR, env=env, capture_output=True, text=True,
            timeout=30,
        )
        # Run from an isolated source copy without a populated .env file.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SESSION_SECRET must be configured", result.stderr)

    def test_worker_has_root_scope_and_revalidation_headers(self):
        response = self.client.get("/service-worker.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertIn("application/javascript", response["Content-Type"])

    def test_worker_endpoint_does_not_accept_mutations(self):
        self.assertEqual(self.client.post("/service-worker.js").status_code, 405)

    def test_manifest_icons_have_declared_dimensions(self):
        from PIL import Image
        root = Path(settings.BASE_DIR)
        manifest = json.loads((root / "static/manifest.json").read_text())
        self.assertEqual(manifest["name"], "Kebbi Progressive Youth Network")
        for icon in manifest["icons"]:
            expected = tuple(int(x) for x in icon["sizes"].split("x"))
            with Image.open(root / icon["src"].lstrip("/")) as image:
                self.assertEqual(image.size, expected)

    def test_web_and_android_action_and_brand_tokens_match(self):
        root = Path(settings.BASE_DIR)
        css = (root / "static/staff/css/kpn-design.css").read_text().lower()
        theme = (root / "Kpn_android/app/src/main/java/com/kpn/mobile/ui/Theme.kt").read_text().lower()
        for hex_value in ("28a745", "0066cc", "176b36"):
            self.assertIn("#" + hex_value, css)
            self.assertIn("0xff" + hex_value, theme)

    def test_all_project_templates_compile(self):
        from django.template.loader import get_template
        root = Path(settings.BASE_DIR)
        for directory in (
            "templates", "core/templates", "staff/templates",
            "campaigns/templates", "events/templates", "donations/templates",
            "media/templates", "telegram_integration/templates",
        ):
            for path in (root / directory).rglob("*.html"):
                with self.subTest(template=str(path.relative_to(root))):
                    get_template(str(path.relative_to(root / directory)))


@override_settings(STORAGES=TEST_STORAGES)
class PublicHomeTests(TestCase):
    def test_empty_home_has_clear_states_and_local_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No stories published yet")
        self.assertContains(response, "No current opportunities listed")
        self.assertContains(response, "staff/css/tailwind.css")
        self.assertNotContains(response, "cdn.tailwindcss.com")
        self.assertNotContains(response, "alpinejs@3.x.x")
        self.assertContains(response, "Code of Conduct")
        self.assertNotContains(response, ">Privacy</a>")
        self.assertNotContains(response, ">Terms</a>")

    def test_home_omits_closed_and_expired_opportunities(self):
        today = timezone.localdate()
        for slug, status, deadline in (
            ("active", "OPEN", today + timedelta(days=7)),
            ("expired", "OPEN", today - timedelta(days=1)),
            ("closed", "CLOSED", today + timedelta(days=7)),
            ("undated", "OPEN", None),
        ):
            Opportunity.objects.create(
                title=slug, slug=slug, provider="Synthetic provider",
                description="Synthetic opportunity", status=status,
                deadline=deadline,
            )
        response = self.client.get("/")
        self.assertEqual(
            {item.slug for item in response.context["latest_opportunities"]},
            {"active", "undated"},
        )

    def test_announcements_are_json_encoded_not_inserted_as_html(self):
        user = User.objects.create_user(
            username="test_announcement_reader", password="TestPass123!",
            phone="synthetic", status="VERIFIED", role="GENERAL",
        )
        announcement = Announcement.objects.create(
            title="<script>synthetic</script>",
            content='<img src="missing" onerror="synthetic()">',
            scope="GENERAL", created_by=user,
        )
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, 'id="kpn-announcement-data"')
        self.assertContains(response, r"\u003Cscript\u003E")
        self.assertNotContains(response, announcement.content)
        self.assertNotContains(response, "content.innerHTML")
        self.assertContains(response, "staff/js/announcements.js")

    def test_login_has_associated_labels_and_password_controls(self):
        response = self.client.get('/account/login/')
        self.assertContains(response, 'for="loginUsername"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, 'aria-label="Show password"')

    def test_registration_help_matches_upload_limit_and_signup_policy(self):
        response = self.client.get('/account/register/')
        self.assertContains(response, 'maximum 400 KiB')
        self.assertNotContains(response, 'max 5MB')
        self.assertNotContains(response, 'register as a General Member')
