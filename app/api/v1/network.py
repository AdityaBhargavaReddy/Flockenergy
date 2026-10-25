"""Electrical grid network hierarchy API endpoints."""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException

from app.client.exceptions import UrjaPortalError
from app.services.meter_service import meter_service

router = APIRouter(prefix="/network", tags=["Network"])


@router.get(
    "/hierarchy",
    response_model=Dict[str, Any],
    summary="Get reconstructed electrical network hierarchy",
    description="Reconstructs and exposes the complete distribution grid topology: Zone -> Circle -> Division -> Subdivision -> Substation -> Feeder -> DT -> Meters.",
)
async def get_network_hierarchy():
    try:
        return await meter_service.get_network_hierarchy_tree()
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
