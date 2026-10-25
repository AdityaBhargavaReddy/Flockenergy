"""Cache synchronization management API endpoints."""

from fastapi import APIRouter, HTTPException

from app.client.exceptions import UrjaPortalError
from app.models.schemas import SyncStatusResponse
from app.services.meter_service import meter_service

router = APIRouter(prefix="/sync", tags=["Sync"])


@router.get(
    "/status",
    response_model=SyncStatusResponse,
    summary="Get cache synchronization status",
    description="Check the freshness of the local meter index, total records cached, and timestamp of last synchronization.",
)
async def get_sync_status():
    return meter_service.get_sync_status()


@router.post(
    "",
    response_model=SyncStatusResponse,
    summary="Trigger manual cache synchronization",
    description="Force an immediate re-synchronization of all meter and transformer records from the upstream portal.",
)
async def trigger_sync():
    try:
        return await meter_service.sync(force=True)
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
