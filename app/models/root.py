from pydantic import BaseModel, ConfigDict


class RootResponse(BaseModel):
    app_name: str
    status: str
    environment: str
    docs_url: str
    openapi_url: str
    health_url: str
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "app_name": "Stock Discovery GPT API",
                    "status": "ok",
                    "environment": "production",
                    "docs_url": "/docs",
                    "openapi_url": "/openapi.json",
                    "health_url": "/health",
                    "message": (
                        "Research-only stock discovery backend. "
                        "No trading orders are placed."
                    ),
                }
            ]
        }
    )
