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
    summary="Check FMP configuration and connectivity",
    description=(
        "Public diagnostic endpoint that reports only whether FMP_API_KEY is configured and "
        "whether a lightweight FMP quote request succeeds. It never returns the API key."
    ),
    operation_id="getFmpHealth",
)
async def fmp_health(settings: Settings = Depends(get_settings)) -> FMPHealthResponse:
    client = FMPClient(api_key=settings.fmp_api_key)
    if not client.is_configured:
        return FMPHealthResponse(
            configured=False,
            connection_success=False,
            note="FMP_API_KEY is not configured.",
        )

    result = await client.check_connection()
    return FMPHealthResponse(
        configured=True,
        connection_success=result.ok and bool(result.data),
        note=(
            "FMP quote request succeeded."
            if result.ok and result.data
            else result.error or "FMP returned an empty quote response."
        ),
    )
