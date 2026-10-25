"""Main FastAPI application entry point for Urja Meter Ops Gateway."""

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import v1_router
from app.client.exceptions import UrjaAuthenticationError, UrjaNotFoundError, UrjaPortalError
from app.core.config import settings
from app.services.meter_service import meter_service

# Logging setup
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("urja_gateway")

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and graceful shutdown tasks."""
    logger.info("Initializing Urja Meter Ops Gateway Service...")

    if settings.sync_on_startup:
        # Run sync in the background to avoid blocking server boot
        asyncio.create_task(meter_service.sync(force=False))

    yield

    logger.info("Shutting down Urja Meter Ops Gateway Service...")
    await meter_service.client.close()


app = FastAPI(
    title="Flock Energy - Urja Meter Ops Gateway API",
    version="1.0.0",
    description="""
# Urja Meter Ops Gateway

A clean, modern, and documented REST API service bridging the legacy **Urja Meter Ops** utility portal.

## Overview
- **Data Normalization**: Unifies legacy & modern v2 smart meter schemas into clean Pydantic entities.
- **Advanced Querying**: Enables multi-attribute filtering (status, make, phase, DT) and GPS radius searches that the original portal cannot perform.
- **Network Hierarchy Reconstructor**: Reconstructs the utility tree down from Zone to Circle, Division, Subdivision, Substation, Feeder, DT, and connected meters.
- **Analytical Metrics**: Automatically calculates interval consumption deltas (kWh), voltage variance, and power factor from cumulative meter registers.
- **Resilient Upstream Integration**: Automates session authentication, cookie management, HMAC-SHA-256 export signing, and retry mechanisms.
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(UrjaNotFoundError)
async def not_found_handler(request: Request, exc: UrjaNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "not_found", "message": exc.message},
    )


@app.exception_handler(UrjaAuthenticationError)
async def auth_error_handler(request: Request, exc: UrjaAuthenticationError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": "upstream_auth_failure", "message": exc.message},
    )


@app.exception_handler(UrjaPortalError)
async def portal_error_handler(request: Request, exc: UrjaPortalError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "upstream_error", "message": exc.message},
    )


# Health Check
@app.get(
    "/health",
    tags=["System"],
    summary="Service Health Check",
    description="Check gateway health, uptime, and upstream portal sync readiness.",
)
async def health_check():
    sync_status = meter_service.get_sync_status()
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "upstream_target": settings.urja_portal_url,
        "cache": sync_status.model_dump(),
    }


# Include V1 Routers
app.include_router(v1_router)

# Static Dashboard & Frontend Web Client
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root requests to the modern operations dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return RedirectResponse(url="/docs")


@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    """Serve the modern operations web client dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return RedirectResponse(url="/docs")
