import asyncio
from datetime import datetime, timezone
import time

import httpx
import jwt

from app.authentication import ServiceUser
from app.dashboards import Dashboard
from app.settings import Settings


class SupersetError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


class SupersetClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.access_token: str | None = None
        self.access_token_expires_at = 0.0
        self.lock = asyncio.Lock()

    async def get_guest_token(
        self,
        settings: Settings,
        user: ServiceUser,
        dashboards: list[Dashboard],
    ) -> str:
        if (
            type(user.partner_id) is not int
            or user.partner_id <= 0
            or not dashboards
            or any(not item.dataset_ids for item in dashboards)
        ):
            raise SupersetError(503, "Не настроены обязательные ограничения RLS")
        dataset_ids = {
            dataset_id
            for dashboard in dashboards
            for dataset_id in dashboard.dataset_ids
        }
        if not dataset_ids or any(
            type(dataset_id) is not int or dataset_id <= 0
            for dataset_id in dataset_ids
        ):
            raise SupersetError(503, "Не настроены обязательные ограничения RLS")

        payload = {
            "user": {"username": user.subject},
            "resources": [
                {"type": "dashboard", "id": dashboard.embedded_id}
                for dashboard in dashboards
            ],
            "rls": [
                {"dataset": dataset_id, "clause": f"partner_id = {user.partner_id}"}
                for dataset_id in sorted(dataset_ids)
            ],
        }
        try:
            async with self.lock:
                for attempt in range(2):
                    access_token = await self._get_access_token(
                        settings, force=attempt == 1
                    )
                    headers = {"Authorization": f"Bearer {access_token}"}
                    csrf_response = await self.http_client.get(
                        f"{settings.superset_internal_url}/api/v1/security/csrf_token/",
                        headers=headers,
                    )
                    if csrf_response.status_code == 401 and attempt == 0:
                        continue
                    if csrf_response.status_code != 200:
                        raise SupersetError(
                            502, "Не удалось получить CSRF-токен Superset"
                        )
                    csrf_token = self._json_value(csrf_response, "result")
                    headers["X-CSRFToken"] = csrf_token
                    response = await self.http_client.post(
                        f"{settings.superset_internal_url}"
                        "/api/v1/security/guest_token/",
                        json=payload,
                        headers=headers,
                    )
                    if response.status_code == 401 and attempt == 0:
                        continue
                    if response.status_code != 200:
                        raise SupersetError(
                            502, "Superset отказал в выдаче Guest Token"
                        )
                    return self._json_value(response, "token")
        except httpx.TimeoutException:
            raise SupersetError(
                504, "Время ожидания Superset истекло"
            ) from None
        except httpx.RequestError:
            raise SupersetError(503, "Superset недоступен") from None
        raise SupersetError(502, "Не удалось обновить доступ к Superset")

    async def _get_access_token(self, settings: Settings, force: bool = False) -> str:
        if (
            not force
            and self.access_token
            and time.monotonic() < self.access_token_expires_at
        ):
            return self.access_token

        response = await self.http_client.post(
            f"{settings.superset_internal_url}/api/v1/security/login",
            json={
                "username": settings.superset_username,
                "password": settings.superset_password,
                "provider": "db",
                "refresh": True,
            },
        )
        if response.status_code != 200:
            raise SupersetError(502, "Не удалось авторизоваться в Superset")

        token = self._json_value(response, "access_token")
        try:
            expiration = jwt.decode(token, options={"verify_signature": False})["exp"]
            remaining = expiration - datetime.now(timezone.utc).timestamp() - 30
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            remaining = 60
        self.access_token = token
        self.access_token_expires_at = time.monotonic() + max(0, min(remaining, 240))
        return token

    @staticmethod
    def _json_value(response: httpx.Response, field: str) -> str:
        try:
            value = response.json()[field]
        except (ValueError, KeyError, TypeError):
            raise SupersetError(502, "Некорректный ответ Superset") from None
        if not isinstance(value, str) or not value:
            raise SupersetError(502, "Некорректный ответ Superset")
        return value
