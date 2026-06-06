from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "app_name": "Stock Discovery GPT API",
                    "environment": "development",
                }
            ]
        }
    )


class FMPHealthResponse(BaseModel):
    configured: bool
    connection_success: bool
    note: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "configured": True,
                    "connection_success": True,
                    "note": "FMP quote request succeeded.",
                }
            ]
        }
    )
