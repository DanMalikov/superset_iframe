from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt

from app.authentication import ServiceUser
from app.dashboards import Dashboard
from app.main import app
from app.settings import Settings
from app.superset_client import SupersetClient, SupersetError


EMBEDDED_ID = "d8755a51-1984-451b-9bd1-8a5f220ed205"


class FakeSupersetClient:
    def __init__(self):
        self.calls = []

    async def get_guest_token(self, settings, user, dashboards):
        self.calls.append((settings, user, dashboards))
        return "guest-token"


class EmbedEndpointTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        public_key = cls.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cls.key_directory = tempfile.TemporaryDirectory()
        cls.public_key_path = Path(cls.key_directory.name) / "public.pem"
        cls.public_key_path.write_bytes(public_key)

    @classmethod
    def tearDownClass(cls):
        cls.key_directory.cleanup()

    def setUp(self):
        self.superset = FakeSupersetClient()
        app.state.superset_client = self.superset
        self.environment = patch.dict(
            os.environ,
            {
                "SERVICE_JWT_PUBLIC_KEY_PATH": str(self.public_key_path),
                "SUPERSET_EMBED_USERNAME": "service",
                "SUPERSET_EMBED_PASSWORD": "secret",
                "TELEMETRY_OVERVIEW_EMBEDDED_ID": EMBEDDED_ID,
                "TELEMETRY_OVERVIEW_DATASET_ID": "7",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def token(self, **changes):
        now = datetime.now(timezone.utc)
        claims = {
            "sub": "15",
            "partner_id": 1,
            "role": "analyst",
            "iss": "servernet-admin",
            "aud": "telemetry-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        claims.update(changes)
        return jwt.encode(claims, self.private_key, algorithm="RS256")

    async def post(self, token=None):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post(
                "/internal/v1/telemetry/embed",
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )

    async def test_valid_token_and_both_roles(self):
        for role in ("analyst", "director"):
            response = await self.post(self.token(role=role))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["dashboards"][0]["embedded_id"], EMBEDDED_ID
            )
            self.assertEqual(response.json()["guest_token"], "guest-token")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(
            [call[1].role for call in self.superset.calls],
            ["analyst", "director"],
        )

    async def test_invalid_signature_and_missing_authorization(self):
        token = self.token()
        changed = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
        self.assertEqual((await self.post(changed)).status_code, 401)
        self.assertEqual((await self.post()).status_code, 401)
        self.assertFalse(self.superset.calls)

    async def test_invalid_claims(self):
        cases = (
            {"iss": "other"},
            {"aud": "other"},
            {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            {"partner_id": None},
            {"partner_id": 0},
            {"partner_id": "1"},
            {"sub": "0"},
            {"sub": "not-a-number"},
            {"iat": None},
        )
        for claims in cases:
            with self.subTest(claims=claims):
                response = await self.post(self.token(**claims))
                self.assertEqual(response.status_code, 401)
        self.assertFalse(self.superset.calls)

    async def test_unknown_role(self):
        response = await self.post(self.token(role="unknown"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.superset.calls)

    async def test_missing_or_wrong_configuration(self):
        for name, value in (
            ("TELEMETRY_OVERVIEW_DATASET_ID", ""),
            ("TELEMETRY_OVERVIEW_DATASET_ID", "0"),
            ("TELEMETRY_OVERVIEW_EMBEDDED_ID", "invalid"),
        ):
            with self.subTest(name=name, value=value), patch.dict(
                os.environ, {name: value}
            ):
                response = await self.post(self.token())
                self.assertEqual(response.status_code, 503)
        self.assertFalse(self.superset.calls)

    async def test_health(self):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class SupersetClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = Settings(
            superset_internal_url="http://superset:8088",
            superset_browser_url="http://localhost:8088",
            superset_username="service",
            superset_password="secret",
            overview_embedded_id=EMBEDDED_ID,
            overview_dataset_id=7,
        )
        self.user = ServiceUser(subject="15", partner_id=2, role="analyst")
        self.dashboard = Dashboard(
            code="overview",
            title="Company Overview",
            embedded_id=EMBEDDED_ID,
            dataset_ids=(7,),
            roles=frozenset({"analyst", "director"}),
        )

    async def test_login_csrf_rls_and_token_reuse(self):
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path.endswith("/login"):
                return httpx.Response(200, json={"access_token": "service-token"})
            if request.url.path.endswith("/csrf_token/"):
                return httpx.Response(
                    200,
                    json={"result": "csrf"},
                    headers={"Set-Cookie": "session=abc; Path=/"},
                )
            self.assertEqual(request.headers["X-CSRFToken"], "csrf")
            self.assertIn("session=abc", request.headers.get("Cookie", ""))
            self.assertEqual(request.headers["Authorization"], "Bearer service-token")
            self.assertEqual(request.read().decode().count("partner_id = 2"), 1)
            body = json.loads(request.content)
            self.assertEqual(
                body["resources"], [{"type": "dashboard", "id": EMBEDDED_ID}]
            )
            self.assertEqual(
                body["rls"], [{"dataset": 7, "clause": "partner_id = 2"}]
            )
            return httpx.Response(200, json={"token": "guest-token"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = SupersetClient(http_client)
            for _ in range(2):
                token = await client.get_guest_token(
                    self.settings, self.user, [self.dashboard]
                )
                self.assertEqual(token, "guest-token")
        self.assertEqual(
            sum(request.url.path.endswith("/login") for request in calls), 1
        )

    async def test_missing_rls_rejected_before_superset_call(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: self.fail("HTTP called"))
        ) as http_client:
            client = SupersetClient(http_client)
            bad_dashboard = Dashboard(
                "overview", "Company Overview", EMBEDDED_ID, (),
                frozenset({"analyst"}),
            )
            with self.assertRaises(SupersetError):
                await client.get_guest_token(self.settings, self.user, [bad_dashboard])

    async def test_superset_errors_do_not_expose_secrets(self):
        def handler(request):
            return httpx.Response(401, text="secret service-token guest-token")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = SupersetClient(http_client)
            with self.assertRaises(SupersetError) as caught:
                await client.get_guest_token(self.settings, self.user, [self.dashboard])
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn("secret", caught.exception.message)

    async def test_access_token_expiry_reauthenticates(self):
        login_count = 0

        def handler(request):
            nonlocal login_count
            if request.url.path.endswith("/login"):
                login_count += 1
                return httpx.Response(
                    200, json={"access_token": f"token-{login_count}"}
                )
            if request.url.path.endswith("/csrf_token/"):
                if request.headers["Authorization"] == "Bearer token-1":
                    return httpx.Response(401)
                return httpx.Response(
                    200,
                    json={"result": "csrf"},
                    headers={"Set-Cookie": "session=abc; Path=/"},
                )
            return httpx.Response(200, json={"token": "guest-token"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = SupersetClient(http_client)
            token = await client.get_guest_token(
                self.settings, self.user, [self.dashboard]
            )
            self.assertEqual(token, "guest-token")
        self.assertEqual(login_count, 2)

    async def test_guest_token_rejection_and_timeout_are_sanitized(self):
        def rejected(request):
            if request.url.path.endswith("/login"):
                return httpx.Response(200, json={"access_token": "service-token"})
            if request.url.path.endswith("/csrf_token/"):
                return httpx.Response(200, json={"result": "csrf"})
            return httpx.Response(400, text="secret guest-token")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(rejected)
        ) as http_client:
            client = SupersetClient(http_client)
            with self.assertRaises(SupersetError) as caught:
                await client.get_guest_token(self.settings, self.user, [self.dashboard])
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn("secret", caught.exception.message)

        def timed_out(request):
            raise httpx.ReadTimeout("secret", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(timed_out)
        ) as http_client:
            client = SupersetClient(http_client)
            with self.assertRaises(SupersetError) as caught:
                await client.get_guest_token(self.settings, self.user, [self.dashboard])
        self.assertEqual(caught.exception.status_code, 504)
        self.assertNotIn("secret", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
