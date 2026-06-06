from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.models.health import FMPHealthResponse, HealthResponse
from app.services.fmp_client import FMPClient

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


@router.get(
    "/health/fmp",
    response_model=FMPHealthResponse,
    summary="Check FMP configuration",
    description="Safely reports whether FMP_API_KEY is configured without exposing the key.",
    operation_id="getFmpHealth",
)
def fmp_health(settings: Settings = Depends(get_settings)) -> FMPHealthResponse:
    configured = FMPClient(api_key=settings.fmp_api_key).is_configured
    return FMPHealthResponse(
        status="ok" if configured else "not_configured",
        configured=configured,
        message=("FMP_API_KEY is configured." if configured else "FMP_API_KEY is not configured."),
    )
