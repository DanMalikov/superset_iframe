from dataclasses import dataclass

from fastapi import HTTPException

from app.settings import Settings


@dataclass(frozen=True)
class Dashboard:
    code: str
    title: str
    embedded_id: str
    dataset_ids: tuple[int, ...]
    roles: frozenset[str]


def get_allowed_dashboards(role: str, settings: Settings) -> list[Dashboard]:
    dashboards = [
        Dashboard(
            code="overview",
            title="Company Overview",
            embedded_id=settings.overview_embedded_id,
            dataset_ids=(settings.overview_dataset_id,),
            roles=frozenset({"analyst", "director"}),
        )
    ]
    allowed = [dashboard for dashboard in dashboards if role in dashboard.roles]
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет разрешённых дашбордов")
    if any(
        not dashboard.dataset_ids
        or any(dataset_id <= 0 for dataset_id in dashboard.dataset_ids)
        for dashboard in allowed
    ):
        raise ValueError("Не настроен обязательный Dataset ID")
    return allowed
