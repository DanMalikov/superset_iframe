from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.partners.models import Partner


User = get_user_model()


class UserModelTests(TestCase):
    def setUp(self):
        self.partner = Partner.objects.create(name="Партнёр")
        self.role = Role.objects.create(code="analyst", name="Аналитик")

    def test_active_user_requires_partner_and_role(self):
        user = User(username="ordinary")
        with self.assertRaises(ValidationError):
            user.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(username="invalid")

    def test_superuser_can_have_no_business_assignments(self):
        user = User.objects.create_superuser(username="admin", password="secret")
        user.full_clean()
        self.assertIsNone(user.partner_id)
        self.assertIsNone(user.role_id)

    def test_assigned_partner_and_role_are_protected(self):
        User.objects.create_user(
            username="ordinary", partner=self.partner, role=self.role
        )
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.partner.delete()
        with self.assertRaises(ProtectedError):
            self.role.delete()


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="secure-admin-password"
        )
        self.partner = Partner.objects.create(name="Партнёр")
        self.role = Role.objects.create(code="analyst", name="Аналитик")
        self.client.force_login(self.admin)

    def test_add_form_requires_partner_and_role(self):
        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="partner"')
        self.assertContains(response, 'name="role"')

        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "ordinary",
                "password1": "secure-user-password-1",
                "password2": "secure-user-password-1",
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="ordinary").exists())

    def test_add_and_change_forms_handle_assignments_and_staff(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "ordinary",
                "password1": "secure-user-password-1",
                "password2": "secure-user-password-1",
                "partner": self.partner.pk,
                "role": self.role.pk,
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="ordinary")
        self.assertTrue(user.check_password("secure-user-password-1"))
        self.assertFalse(user.is_staff)

        change_url = reverse("admin:accounts_user_change", args=[user.pk])
        response = self.client.get(change_url)
        self.assertContains(response, 'name="partner"')
        self.assertContains(response, 'name="role"')
        response = self.client.post(
            change_url,
            {
                "username": "ordinary",
                "password": user.password,
                "partner": self.partner.pk,
                "role": self.role.pk,
                "is_active": "on",
                "is_staff": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)

    def test_ordinary_user_cannot_open_admin(self):
        user = User.objects.create_user(
            username="ordinary", partner=self.partner, role=self.role
        )
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertNotEqual(response.status_code, 200)

    def test_change_form_rejects_missing_role(self):
        user = User.objects.create_user(
            username="ordinary", partner=self.partner, role=self.role
        )
        response = self.client.post(
            reverse("admin:accounts_user_change", args=[user.pk]),
            {
                "username": "ordinary",
                "password": user.password,
                "partner": self.partner.pk,
                "role": "",
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.role_id, self.role.pk)
