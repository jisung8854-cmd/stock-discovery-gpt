from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.models.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service health",
    description="Public endpoint used by deployment platforms and Custom GPT setup checks.",
    operation_id="getHealth",
)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
    )
