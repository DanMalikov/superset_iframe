import os
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY must be set")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.partners",
    "apps.accounts",
    "apps.telemetry",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
database_url = os.environ.get("DATABASE_URL")
if database_url:
    parsed_database_url = urlparse(database_url)
    if parsed_database_url.scheme != "sqlite":
        raise ValueError("DATABASE_URL supports only sqlite for local tests")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": parsed_database_url.path,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DB_NAME", "servernet_db"),
            "USER": os.environ.get("DB_USER", "servernet_user"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "mysql"),
            "PORT": os.environ.get("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PORTAL_JWT_SECRET = os.environ.get("PORTAL_JWT_SECRET")
if not PORTAL_JWT_SECRET:
    raise ValueError("PORTAL_JWT_SECRET must be set")
if len(PORTAL_JWT_SECRET.encode("utf-8")) < 32:
    raise ValueError("PORTAL_JWT_SECRET must contain at least 32 bytes")
PORTAL_JWT_TTL_SECONDS = int(os.environ.get("PORTAL_JWT_TTL_SECONDS", "3600"))
if PORTAL_JWT_TTL_SECONDS <= 0:
    raise ValueError("PORTAL_JWT_TTL_SECONDS must be positive")
PORTAL_JWT_COOKIE_NAME = "servernet_portal_token"
PORTAL_JWT_COOKIE_SECURE = os.environ.get("PORTAL_JWT_COOKIE_SECURE", "0") == "1"
PORTAL_JWT_COOKIE_SAMESITE = os.environ.get("PORTAL_JWT_COOKIE_SAMESITE", "Lax")
if PORTAL_JWT_COOKIE_SAMESITE not in {"Lax", "Strict", "None"}:
    raise ValueError("PORTAL_JWT_COOKIE_SAMESITE must be Lax, Strict or None")
if PORTAL_JWT_COOKIE_SAMESITE == "None" and not PORTAL_JWT_COOKIE_SECURE:
    raise ValueError("SameSite=None requires PORTAL_JWT_COOKIE_SECURE=1")
CSRF_COOKIE_SECURE = PORTAL_JWT_COOKIE_SECURE
SESSION_COOKIE_SECURE = PORTAL_JWT_COOKIE_SECURE

SERVICE_JWT_PRIVATE_KEY_PATH = os.environ.get(
    "SERVICE_JWT_PRIVATE_KEY_PATH", "/run/telemetry-keys/private.pem"
)
SERVICE_JWT_TTL_SECONDS = int(os.environ.get("SERVICE_JWT_TTL_SECONDS", "300"))
if SERVICE_JWT_TTL_SECONDS <= 0:
    raise ValueError("SERVICE_JWT_TTL_SECONDS must be positive")
TELEMETRY_API_INTERNAL_URL = os.environ.get(
    "TELEMETRY_API_INTERNAL_URL", "http://telemetry-api:8001"
).rstrip("/")

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
