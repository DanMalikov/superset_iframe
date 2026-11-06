from django.contrib.auth.forms import (
    AdminUserCreationForm as DjangoAdminUserCreationForm,
)
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError

from .models import User


class StaffPermissionFormMixin:
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_staff") and not cleaned_data.get("is_superuser"):
            raise ValidationError("Доступ в Admin разрешён только суперпользователям")
        return cleaned_data


class AdminUserCreationForm(StaffPermissionFormMixin, DjangoAdminUserCreationForm):
    class Meta(DjangoAdminUserCreationForm.Meta):
        model = User
        fields = ("username", "partner", "role", "is_active")


class AdminUserChangeForm(StaffPermissionFormMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"
