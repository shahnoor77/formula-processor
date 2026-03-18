"""Main entry point for the application."""
import uvicorn
from core.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info"
    )
