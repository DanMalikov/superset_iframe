from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Role(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class User(AbstractUser):
    partner = models.ForeignKey(
        "partners.Partner", on_delete=models.PROTECT, null=True, blank=True
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(is_superuser=True)
                    | Q(is_active=False)
                    | (Q(partner__isnull=False) & Q(role__isnull=False))
                ),
                name="active_user_has_partner_and_role",
            )
        ]

    def clean(self):
        super().clean()
        if self.is_active and not self.is_superuser:
            errors = {}
            if self.partner_id is None:
                errors["partner"] = "Активному пользователю нужен партнёр"
            if self.role_id is None:
                errors["role"] = "Активному пользователю нужна роль"
            if errors:
                raise ValidationError(errors)
