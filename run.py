"""Convenience script to launch the Urja Meter Ops Gateway API."""

import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    print(f"Starting Urja Meter Ops Gateway on http://localhost:{settings.api_port}")
    print(f"Interactive Swagger Documentation: http://localhost:{settings.api_port}/docs")
    print(f"Operations Console Dashboard:      http://localhost:{settings.api_port}/dashboard")
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
