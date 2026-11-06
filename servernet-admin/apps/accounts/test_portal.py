from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.partners.models import Partner


@override_settings(PORTAL_JWT_SECRET="portal-test-secret-with-at-least-32-bytes")
class PortalAuthenticationTests(TestCase):
    def setUp(self):
        partner = Partner.objects.create(name="Партнёр")
        role = Role.objects.create(code="analyst", name="Аналитик")
        self.user = User.objects.create_user(
            username="analyst1",
            password="safe-test-password",
            partner=partner,
            role=role,
        )

    def login(self):
        return self.client.post(
            reverse("portal_login"),
            {"username": "analyst1", "password": "safe-test-password"},
        )

    def test_login_sets_http_only_token_and_opens_page(self):
        response = self.login()
        self.assertRedirects(response, reverse("telemetry"))
        cookie = response.cookies[settings.PORTAL_JWT_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(int(cookie["max-age"]), 3600)
        self.assertNotIn(cookie.value, response["Location"])
        self.assertContains(
            self.client.get(reverse("telemetry")), "dashboard-container"
        )
        self.assertTrue(self.user.password.startswith("bcrypt_sha256$"))

    def test_invalid_password_does_not_set_token(self):
        response = self.client.post(
            reverse("portal_login"),
            {"username": "analyst1", "password": "incorrect"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(settings.PORTAL_JWT_COOKIE_NAME, response.cookies)

    def test_existing_pbkdf2_password_is_upgraded_after_login(self):
        self.user.password = PBKDF2PasswordHasher().encode(
            "safe-test-password", "legacy-salt"
        )
        self.user.save(update_fields=["password"])
        self.assertEqual(self.login().status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.password.startswith("bcrypt_sha256$"))

    @override_settings(
        PORTAL_JWT_COOKIE_SECURE=True, PORTAL_JWT_COOKIE_SAMESITE="Strict"
    )
    def test_cookie_security_options_are_configurable(self):
        cookie = self.login().cookies[settings.PORTAL_JWT_COOKIE_NAME]
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Strict")

    def test_session_authentication_does_not_open_portal(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("telemetry"))
        self.assertRedirects(response, reverse("portal_login"))

    def test_admin_session_remains_separate(self):
        admin = User.objects.create_superuser(
            username="admin", password="safe-admin-password"
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse("telemetry")), reverse("portal_login")
        )
        self.client.logout()
        response = self.client.post(
            reverse("portal_login"),
            {"username": "admin", "password": "safe-admin-password"},
        )
        self.assertEqual(response.status_code, 401)

    def test_inactive_user_loses_access_after_token_issued(self):
        self.login()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertRedirects(
            self.client.get(reverse("telemetry")), reverse("portal_login")
        )

    def test_expired_and_invalid_signature_are_rejected(self):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(self.user.pk),
            "iss": "servernet-admin",
            "aud": "servernet-portal",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
        self.client.cookies[settings.PORTAL_JWT_COOKIE_NAME] = jwt.encode(
            payload, settings.PORTAL_JWT_SECRET, algorithm="HS256"
        )
        self.assertRedirects(
            self.client.get(reverse("telemetry")), reverse("portal_login")
        )
        payload["exp"] = now + timedelta(hours=1)
        self.client.cookies[settings.PORTAL_JWT_COOKIE_NAME] = jwt.encode(
            payload, "wrong-secret-with-at-least-32-bytes", algorithm="HS256"
        )
        self.assertRedirects(
            self.client.get(reverse("telemetry")), reverse("portal_login")
        )

    def test_logout_deletes_cookie(self):
        self.login()
        response = self.client.post(reverse("portal_logout"))
        self.assertRedirects(response, reverse("portal_login"))
        self.assertEqual(
            response.cookies[settings.PORTAL_JWT_COOKIE_NAME]["max-age"], 0
        )
        self.assertRedirects(
            self.client.get(reverse("telemetry")), reverse("portal_login")
        )

    def test_csrf_is_required_for_login_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(reverse("portal_login"), {}).status_code, 403
        )
        client.get(reverse("portal_login"))
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("portal_login"),
            {"username": "analyst1", "password": "safe-test-password"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.post(reverse("portal_logout")).status_code, 403)
        self.assertEqual(
            client.post(
                reverse("portal_logout"), HTTP_X_CSRFTOKEN=csrf_token
            ).status_code,
            302,
        )
