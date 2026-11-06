from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import Role, User
from apps.partners.models import Partner


class SeedReferenceDataTests(TestCase):
    def test_seed_is_idempotent_and_preserves_assignments(self):
        call_command("seed_reference_data", verbosity=0)
        user = User.objects.create_user(
            username="ordinary",
            partner=Partner.objects.get(pk=1),
            role=Role.objects.get(code="analyst"),
        )
        call_command("seed_reference_data", verbosity=0)

        self.assertEqual(Partner.objects.count(), 2)
        self.assertEqual(Role.objects.count(), 2)
        self.assertEqual(Partner.objects.get(pk=1).name, "Партнер один")
        self.assertEqual(Partner.objects.get(pk=2).name, "Партнер два")
        user.refresh_from_db()
        self.assertEqual(user.partner_id, 1)
        self.assertEqual(user.role.code, "analyst")

    def test_seed_does_not_overwrite_existing_partner(self):
        Partner.objects.create(pk=1, name="Иное имя")
        call_command("seed_reference_data", verbosity=0)
        self.assertEqual(Partner.objects.get(pk=1).name, "Иное имя")

    def test_seed_rejects_name_collision_with_other_id(self):
        Partner.objects.create(pk=3, name="Партнер один")
        with self.assertRaises(CommandError):
            call_command("seed_reference_data", verbosity=0)
        self.assertEqual(Partner.objects.count(), 1)
