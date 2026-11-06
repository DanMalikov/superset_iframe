from django.contrib import admin
from django.urls import path

from apps.accounts import views as account_views
from apps.telemetry import views as telemetry_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/login", account_views.login_view, name="portal_login"),
    path("auth/logout", account_views.logout_view, name="portal_logout"),
    path("telemetry/", telemetry_views.telemetry_view, name="telemetry"),
    path(
        "api/telemetry/embed",
        telemetry_views.telemetry_embed_view,
        name="telemetry_embed",
    ),
]
