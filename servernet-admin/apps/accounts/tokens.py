from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model


PORTAL_ISSUER = "servernet-admin"
PORTAL_AUDIENCE = "servernet-portal"
SERVICE_AUDIENCE = "telemetry-api"


def issue_portal_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.pk),
            "iss": PORTAL_ISSUER,
            "aud": PORTAL_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=settings.PORTAL_JWT_TTL_SECONDS),
        },
        settings.PORTAL_JWT_SECRET,
        algorithm="HS256",
    )


def get_portal_user(request):
    token = request.COOKIES.get(settings.PORTAL_JWT_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.PORTAL_JWT_SECRET,
            algorithms=["HS256"],
            issuer=PORTAL_ISSUER,
            audience=PORTAL_AUDIENCE,
            options={"require": ["sub", "iss", "aud", "iat", "exp"]},
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        return None

    return get_user_model().objects.filter(
        pk=user_id,
        is_active=True,
        is_superuser=False,
        partner__isnull=False,
        role__isnull=False,
    ).exclude(role__code="").first()


def issue_service_token(user):
    current_user = get_user_model().objects.select_related("role").filter(
        pk=user.pk, is_active=True, is_superuser=False
    ).first()
    if (
        not current_user
        or not current_user.partner_id
        or not current_user.role_id
        or not current_user.role.code
    ):
        raise ValueError("Для пользователя недоступен межсервисный токен")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(current_user.pk),
        "partner_id": current_user.partner_id,
        "role": current_user.role.code,
        "iss": PORTAL_ISSUER,
        "aud": SERVICE_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=settings.SERVICE_JWT_TTL_SECONDS),
    }
    private_key = Path(settings.SERVICE_JWT_PRIVATE_KEY_PATH).read_bytes()
    return jwt.encode(payload, private_key, algorithm="RS256")
