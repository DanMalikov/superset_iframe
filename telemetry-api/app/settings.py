from dataclasses import dataclass
import os
from urllib.parse import urlsplit
from uuid import UUID


@dataclass(frozen=True)
class Settings:
    superset_internal_url: str
    superset_browser_url: str
    superset_username: str
    superset_password: str
    overview_embedded_id: str
    overview_dataset_id: int

    @classmethod
    def from_environment(cls) -> "Settings":
        required = (
            "SUPERSET_EMBED_USERNAME",
            "SUPERSET_EMBED_PASSWORD",
            "TELEMETRY_OVERVIEW_EMBEDDED_ID",
            "TELEMETRY_OVERVIEW_DATASET_ID",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError("Отсутствуют настройки: " + ", ".join(missing))

        embedded_id = os.environ["TELEMETRY_OVERVIEW_EMBEDDED_ID"]
        dataset_id_value = os.environ["TELEMETRY_OVERVIEW_DATASET_ID"]
        try:
            if str(UUID(embedded_id)) != embedded_id.lower():
                raise ValueError
            dataset_id = int(dataset_id_value)
        except ValueError:
            raise ValueError("Некорректные Embedded UUID или Dataset ID") from None
        if dataset_id <= 0 or str(dataset_id) != dataset_id_value:
            raise ValueError("Dataset ID должен быть положительным целым числом")

        internal_url = os.environ.get("SUPERSET_INTERNAL_URL", "http://superset:8088")
        browser_url = os.environ.get("SUPERSET_BROWSER_URL", "http://localhost:8088")
        for name, value in (
            ("SUPERSET_INTERNAL_URL", internal_url),
            ("SUPERSET_BROWSER_URL", browser_url),
        ):
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError(f"Некорректный адрес {name}")

        return cls(
            superset_internal_url=internal_url.rstrip("/"),
            superset_browser_url=browser_url.rstrip("/"),
            superset_username=os.environ["SUPERSET_EMBED_USERNAME"],
            superset_password=os.environ["SUPERSET_EMBED_PASSWORD"],
            overview_embedded_id=str(UUID(embedded_id)),
            overview_dataset_id=dataset_id,
        )
