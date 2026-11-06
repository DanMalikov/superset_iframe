from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import User


@admin.register(User)
class ServernetUserAdmin(UserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    fieldsets = UserAdmin.fieldsets + (
        ("Бизнес-данные", {"fields": ("partner", "role")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Бизнес-данные", {"fields": ("partner", "role", "is_active")}),
    )
    list_display = UserAdmin.list_display + ("partner", "role")
    list_select_related = ("partner", "role")
