import tempfile
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings

from apps.accounts.models import Role, User
from apps.accounts.tokens import issue_service_token
from apps.partners.models import Partner


class ServiceTokenTests(TestCase):
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
        cls.settings_override = override_settings(
            SERVICE_JWT_PRIVATE_KEY_PATH=str(cls.private_key_path)
        )
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        cls.key_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.partner = Partner.objects.create(name="Партнёр один")
        self.role = Role.objects.create(code="analyst", name="Аналитик")
        self.user = User.objects.create_user(
            username="analyst1", partner=self.partner, role=self.role
        )

    def test_token_has_required_claims_and_valid_signature(self):
        token = issue_service_token(self.user)
        payload = jwt.decode(
            token,
            self.public_key,
            algorithms=["RS256"],
            issuer="servernet-admin",
            audience="telemetry-api",
        )
        self.assertEqual(payload["sub"], str(self.user.pk))
        self.assertEqual(payload["partner_id"], self.partner.pk)
        self.assertEqual(payload["role"], "analyst")
        self.assertEqual(payload["exp"] - payload["iat"], 300)

    def test_new_token_uses_current_database_assignments(self):
        new_partner = Partner.objects.create(name="Партнёр два")
        new_role = Role.objects.create(code="director", name="Директор")
        self.user.partner = new_partner
        self.user.role = new_role
        self.user.save(update_fields=["partner", "role"])

        payload = jwt.decode(
            issue_service_token(User(pk=self.user.pk)),
            self.public_key,
            algorithms=["RS256"],
            issuer="servernet-admin",
            audience="telemetry-api",
        )
        self.assertEqual(payload["partner_id"], new_partner.pk)
        self.assertEqual(payload["role"], "director")

    def test_inactive_or_unassigned_user_cannot_receive_token(self):
        self.user.is_active = False
        self.user.partner = None
        self.user.save(update_fields=["is_active", "partner"])
        with self.assertRaises(ValueError):
            issue_service_token(self.user)
