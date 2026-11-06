from uuid import UUID
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.tokens import get_portal_user, issue_service_token


ALLOWED_ROLES = {"analyst", "director"}


@never_cache
@require_GET
def telemetry_view(request):
    if get_portal_user(request) is None:
        return redirect("portal_login")
    return render(request, "telemetry/index.html")


@never_cache
@require_POST
def telemetry_embed_view(request):
    user = get_portal_user(request)
    if user is None:
        return JsonResponse({"error": "Требуется вход"}, status=401)
    if user.role.code not in ALLOWED_ROLES:
        return JsonResponse({"error": "Нет доступа к телеметрии"}, status=403)

    try:
        service_token = issue_service_token(user)
    except ValueError:
        return JsonResponse({"error": "Нет доступа к телеметрии"}, status=403)
    except OSError:
        return JsonResponse({"error": "Сервис авторизации недоступен"}, status=503)

    try:
        response = httpx.post(
            f"{settings.TELEMETRY_API_INTERNAL_URL}/internal/v1/telemetry/embed",
            headers={"Authorization": f"Bearer {service_token}"},
            timeout=10.0,
        )
    except httpx.TimeoutException:
        return JsonResponse({"error": "Время ожидания телеметрии истекло"}, status=504)
    except httpx.RequestError:
        return JsonResponse({"error": "Сервис телеметрии недоступен"}, status=503)

    if response.status_code != 200:
        return JsonResponse({"error": "Не удалось получить дашборд"}, status=502)

    try:
        payload = response.json()
        superset_url = payload["superset_url"]
        dashboards = payload["dashboards"]
        guest_token = payload["guest_token"]
        parsed_url = urlsplit(superset_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.path not in {"", "/"}
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.username
            or parsed_url.password
            or not isinstance(guest_token, str)
            or not guest_token
            or not isinstance(dashboards, list)
            or not dashboards
        ):
            raise ValueError
        allowed_dashboards = []
        for dashboard in dashboards:
            embedded_id = dashboard["embedded_id"]
            if (
                not isinstance(dashboard["code"], str)
                or not dashboard["code"]
                or not isinstance(dashboard["title"], str)
                or not dashboard["title"]
                or not isinstance(embedded_id, str)
            ):
                raise ValueError
            UUID(embedded_id)
            allowed_dashboards.append(
                {
                    "code": dashboard["code"],
                    "title": dashboard["title"],
                    "embedded_id": embedded_id,
                }
            )
    except (ValueError, TypeError, KeyError, AttributeError):
        return JsonResponse({"error": "Некорректный ответ телеметрии"}, status=502)

    return JsonResponse(
        {
            "superset_url": superset_url.rstrip("/"),
            "dashboards": allowed_dashboards,
            "guest_token": guest_token,
        }
    )
