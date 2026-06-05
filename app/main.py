from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, score, screen
from app.core.config import get_settings
from app.models.root import RootResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Research-only stock discovery and scoring backend for Custom GPT Actions. "
        "This API ranks and explains stock candidates; it does not place trades."
    ),
    version="0.1.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(score.router)
app.include_router(screen.router)


@app.get(
    "/",
    response_model=RootResponse,
    summary="Get API root information",
    description="Public Render-friendly root endpoint with links to health and OpenAPI metadata.",
    operation_id="getRoot",
)
def root() -> RootResponse:
    return RootResponse(
        app_name=settings.app_name,
        status="ok",
        environment=settings.environment,
        docs_url="/docs",
        openapi_url="/openapi.json",
        health_url="/health",
        message="Research-only stock discovery backend. No trading orders are placed.",
    )
