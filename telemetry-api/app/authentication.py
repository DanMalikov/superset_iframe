from dataclasses import dataclass
from pathlib import Path
import re
import os

import jwt
from fastapi import Header, HTTPException


SUBJECT_PATTERN = re.compile(r"[1-9][0-9]*\Z")
ALLOWED_ROLES = {"analyst", "director"}


@dataclass(frozen=True)
class ServiceUser:
    subject: str
    partner_id: int
    role: str


def get_service_user(authorization: str | None = Header(default=None)) -> ServiceUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Нужен межсервисный токен"
        )

    token = authorization.removeprefix("Bearer ")
    if not token or token.strip() != token:
        raise HTTPException(
            status_code=401, detail="Недействительный токен"
        )

    try:
        public_key = Path(
            os.environ.get(
                "SERVICE_JWT_PUBLIC_KEY_PATH", "/run/telemetry-keys/public.pem"
            )
        ).read_bytes()
    except OSError:
        raise HTTPException(
            status_code=503, detail="Публичный ключ недоступен"
        ) from None

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer="servernet-admin",
            audience="telemetry-api",
            options={
                "require": [
                    "sub", "partner_id", "role", "iss", "aud", "iat", "exp"
                ]
            },
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Недействительный токен") from None

    subject = claims["sub"]
    partner_id = claims["partner_id"]
    role = claims["role"]
    issued_at = claims["iat"]
    expires_at = claims["exp"]
    if (
        not isinstance(subject, str)
        or not SUBJECT_PATTERN.fullmatch(subject)
        or type(partner_id) is not int
        or partner_id <= 0
        or type(issued_at) is not int
        or type(expires_at) is not int
        or expires_at <= issued_at
        or claims["iss"] != "servernet-admin"
        or claims["aud"] != "telemetry-api"
    ):
        raise HTTPException(status_code=401, detail="Недействительные данные токена")

    if not isinstance(role, str) or role not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Роль не разрешена")

    return ServiceUser(subject=subject, partner_id=partner_id, role=role)
