import os
import re
from urllib.parse import quote
from uuid import UUID


SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
GUEST_TOKEN_JWT_SECRET = os.environ["SUPERSET_GUEST_TOKEN_JWT_SECRET"]
GUEST_TOKEN_JWT_EXP_SECONDS = 300
GUEST_TOKEN_JWT_AUDIENCE = "superset"
GUEST_ROLE_NAME = "EmbeddedGuest"


def validate_telemetry_guest_token(body):
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db
    from superset.models.embedded_dashboard import EmbeddedDashboard

    embedded_id = os.environ.get("TELEMETRY_OVERVIEW_EMBEDDED_ID", "")
    dataset_id = os.environ.get("TELEMETRY_OVERVIEW_DATASET_ID", "")
    if (
        not embedded_id
        or not dataset_id.isdecimal()
        or int(dataset_id) <= 0
        or str(int(dataset_id)) != dataset_id
    ):
        return False
    try:
        expected_uuid = UUID(embedded_id)
    except ValueError:
        return False

    if body.get("resources") != [{"type": "dashboard", "id": str(expected_uuid)}]:
        return False
    user = body.get("user") or {}
    if not re.fullmatch(r"[1-9][0-9]*", user.get("username", "")):
        return False
    rules = body.get("rls")
    if not isinstance(rules, list) or len(rules) != 1:
        return False
    rule = rules[0]
    if rule.get("dataset") != int(dataset_id):
        return False
    if not re.fullmatch(r"partner_id = [1-9][0-9]*", rule.get("clause", "")):
        return False

    embedded = (
        db.session.query(EmbeddedDashboard)
        .filter_by(uuid=expected_uuid)
        .one_or_none()
    )
    if embedded is None or embedded.dashboard is None:
        return False
    datasources = embedded.dashboard.datasources
    if len(datasources) != 1:
        return False
    datasource = next(iter(datasources))
    return (
        isinstance(datasource, SqlaTable)
        and datasource.id == int(dataset_id)
        and datasource.table_name == "metrics"
        and not datasource.sql
        and any(column.column_name == "partner_id" for column in datasource.columns)
    )


GUEST_TOKEN_VALIDATOR_HOOK = validate_telemetry_guest_token

database_password = quote(os.environ["SUPERSET_DB_PASSWORD"], safe="")
SQLALCHEMY_DATABASE_URI = (
    f"mysql://superset_user:{database_password}@mysql:3306/superset_db"
    "?charset=utf8mb4"
)

FEATURE_FLAGS = {"EMBEDDED_SUPERSET": True}

TALISMAN_CONFIG = {
    "content_security_policy": {
        "base-uri": ["'self'"],
        "default-src": ["'self'"],
        "img-src": [
            "'self'",
            "blob:",
            "data:",
            "https://apachesuperset.gateway.scarf.sh",
            "https://static.scarf.sh/",
            "ows.terrestris.de",
            "https://cdn.document360.io",
        ],
        "worker-src": ["'self'", "blob:"],
        "connect-src": [
            "'self'",
            "https://api.mapbox.com",
            "https://events.mapbox.com",
            "https://tile.openstreetmap.org",
            "https://tile.osm.ch",
            "https://a.basemaps.cartocdn.com",
        ],
        "object-src": "'none'",
        "style-src": ["'self'", "'unsafe-inline'"],
        "font-src": ["'self'"],
        "script-src": ["'self'", "'strict-dynamic'"],
        "frame-ancestors": ["'self'", "http://localhost:8000"],
    },
    "content_security_policy_nonce_in": ["script-src"],
    "force_https": False,
    "frame_options": None,
    "session_cookie_secure": False,
}
