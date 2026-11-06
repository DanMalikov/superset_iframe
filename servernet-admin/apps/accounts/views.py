from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from .tokens import issue_portal_token


@never_cache
def login_view(request):
    if request.method == "GET":
        return render(
            request, "accounts/login.html", {"form": AuthenticationForm(request)}
        )
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    form = AuthenticationForm(request, data=request.POST)
    if form.is_valid():
        user = form.get_user()
        if (
            not user.is_superuser
            and user.partner_id
            and user.role_id
            and user.role.code
        ):
            response = redirect("telemetry")
            response.set_cookie(
                settings.PORTAL_JWT_COOKIE_NAME,
                issue_portal_token(user),
                max_age=settings.PORTAL_JWT_TTL_SECONDS,
                httponly=True,
                secure=settings.PORTAL_JWT_COOKIE_SECURE,
                samesite=settings.PORTAL_JWT_COOKIE_SAMESITE,
                path="/",
            )
            return response
        form.add_error(None, "Нет доступа к пользовательскому порталу")

    return render(request, "accounts/login.html", {"form": form}, status=401)


@never_cache
def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    response = redirect("portal_login")
    response.delete_cookie(
        settings.PORTAL_JWT_COOKIE_NAME,
        path="/",
        samesite=settings.PORTAL_JWT_COOKIE_SAMESITE,
    )
    return response
