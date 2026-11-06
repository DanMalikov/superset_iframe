from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.authentication import ServiceUser, get_service_user
from app.dashboards import get_allowed_dashboards
from app.settings import Settings
from app.superset_client import SupersetClient, SupersetError


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        application.state.superset_client = SupersetClient(http_client)
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/internal/v1/telemetry/embed")
async def create_embed(request: Request, user: ServiceUser = Depends(get_service_user)):
    try:
        settings = Settings.from_environment()
        dashboards = get_allowed_dashboards(user.role, settings)
        guest_token = await request.app.state.superset_client.get_guest_token(
            settings, user, dashboards
        )
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except SupersetError as error:
        raise HTTPException(
            status_code=error.status_code, detail=error.message
        ) from None

    return JSONResponse(
        {
            "superset_url": settings.superset_browser_url,
            "dashboards": [
                {
                    "code": dashboard.code,
                    "title": dashboard.title,
                    "embedded_id": dashboard.embedded_id,
                }
                for dashboard in dashboards
            ],
            "guest_token": guest_token,
        },
        headers={"Cache-Control": "no-store"},
    )
