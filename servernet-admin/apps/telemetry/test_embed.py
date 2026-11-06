import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.tokens import issue_portal_token
from apps.partners.models import Partner


EMBEDDED_ID = "d8755a51-1984-451b-9bd1-8a5f220ed205"


@override_settings(PORTAL_JWT_SECRET="portal-test-secret-with-at-least-32-bytes")
class TelemetryEmbedTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key_directory = tempfile.TemporaryDirectory()
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key_path = Path(cls.key_directory.name) / "private.pem"
        cls.private_key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cls.public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cls.key_override = override_settings(
            SERVICE_JWT_PRIVATE_KEY_PATH=str(cls.private_key_path)
        )
        cls.key_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.key_override.disable()
        cls.key_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.partner = Partner.objects.create(name="Партнёр один")
        self.role = Role.objects.create(code="analyst", name="Аналитик")
        self.user = User.objects.create_user(
            username="analyst1", partner=self.partner, role=self.role
        )

    def authorize(self, client=None):
        target_client = client or self.client
        target_client.cookies[settings.PORTAL_JWT_COOKIE_NAME] = (
            issue_portal_token(self.user)
        )
        return target_client

    @staticmethod
    def telemetry_response():
        return httpx.Response(
            200,
            json={
                "superset_url": "http://localhost:8088",
                "dashboards": [{
                    "code": "overview",
                    "title": "Company Overview",
                    "embedded_id": EMBEDDED_ID,
                }],
                "guest_token": "guest-secret-token",
                "extra": "must-not-appear",
            },
        )

    def test_valid_cookie_uses_current_user_and_hides_service_token(self):
        self.authorize()
        with patch("apps.telemetry.views.httpx.post") as upstream:
            upstream.return_value = self.telemetry_response()
            response = self.client.post(reverse("telemetry_embed"))

        self.assertEqual(response.status_code, 200)
        service_token = upstream.call_args.kwargs["headers"]["Authorization"].split()[1]
        claims = jwt.decode(
            service_token,
            self.public_key,
            algorithms=["RS256"],
            issuer="servernet-admin",
            audience="telemetry-api",
        )
        self.assertEqual(claims["sub"], str(self.user.pk))
        self.assertEqual(claims["partner_id"], self.partner.pk)
        self.assertEqual(claims["role"], "analyst")
        self.assertNotIn(service_token, response.content.decode())
        self.assertNotIn("extra", response.json())
        self.assertEqual(response.json()["guest_token"], "guest-secret-token")
        self.assertIn("no-store", response["Cache-Control"])

    def test_missing_or_blocked_user_cannot_get_guest_token(self):
        with patch("apps.telemetry.views.httpx.post") as upstream:
            self.assertEqual(
                self.client.post(reverse("telemetry_embed")).status_code, 401
            )
            self.authorize()
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])
            self.assertEqual(
                self.client.post(reverse("telemetry_embed")).status_code, 401
            )
            upstream.assert_not_called()

    def test_role_change_is_checked_against_database(self):
        self.authorize()
        self.user.role = Role.objects.create(code="other", name="Другая роль")
        self.user.save(update_fields=["role"])
        with patch("apps.telemetry.views.httpx.post") as upstream:
            response = self.client.post(reverse("telemetry_embed"))
            upstream.assert_not_called()
        self.assertEqual(response.status_code, 403)

    def test_partner_change_is_used_for_new_service_token(self):
        self.authorize()
        new_partner = Partner.objects.create(name="Партнёр два")
        self.user.partner = new_partner
        self.user.save(update_fields=["partner"])
        with patch("apps.telemetry.views.httpx.post") as upstream:
            upstream.return_value = self.telemetry_response()
            self.client.post(reverse("telemetry_embed"))
        service_token = upstream.call_args.kwargs["headers"]["Authorization"].split()[1]
        claims = jwt.decode(
            service_token, self.public_key, algorithms=["RS256"],
            audience="telemetry-api", issuer="servernet-admin",
        )
        self.assertEqual(claims["partner_id"], new_partner.pk)

    def test_csrf_is_required(self):
        client = self.authorize(Client(enforce_csrf_checks=True))
        page = client.get(reverse("telemetry"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(client.post(reverse("telemetry_embed")).status_code, 403)
        with patch("apps.telemetry.views.httpx.post") as upstream:
            upstream.return_value = self.telemetry_response()
            response = client.post(
                reverse("telemetry_embed"),
                HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            )
        self.assertEqual(response.status_code, 200)

    def test_upstream_errors_are_sanitized(self):
        self.authorize()
        with patch("apps.telemetry.views.httpx.post") as upstream:
            upstream.return_value = httpx.Response(400, text="secret service JWT")
            response = self.client.post(reverse("telemetry_embed"))
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret", response.content.decode())

        with patch("apps.telemetry.views.httpx.post") as upstream:
            upstream.side_effect = httpx.ReadTimeout("secret")
            response = self.client.post(reverse("telemetry_embed"))
        self.assertEqual(response.status_code, 504)
        self.assertNotIn("secret", response.content.decode())

    def test_page_loads_local_sdk_and_portal_auth_remains_required(self):
        self.assertEqual(self.client.get(reverse("telemetry")).status_code, 302)
        self.authorize()
        response = self.client.get(reverse("telemetry"))
        self.assertContains(response, "vendor/superset-embedded-sdk/index.js")
        self.assertContains(response, "telemetry/embed.js")
        self.assertContains(response, reverse("telemetry_embed"))
        self.assertIsNotNone(
            finders.find("vendor/superset-embedded-sdk/index.js")
        )
        self.assertIsNotNone(finders.find("telemetry/embed.js"))


