"""Meters API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.client.exceptions import UrjaNotFoundError, UrjaPortalError
from app.models.schemas import (
    MeterDetail,
    MeterNearbyItem,
    MeterSummary,
    PaginatedResponse,
    ReadingsResponse,
)
from app.services.meter_service import meter_service

router = APIRouter(prefix="/meters", tags=["Meters"])


@router.get(
    "",
    response_model=PaginatedResponse[MeterSummary],
    summary="List and filter smart meters",
    description="Retrieve a paginated list of smart meters with rich filtering capabilities not natively supported by the Urja portal.",
)
async def list_meters(
    search: Optional[str] = Query(None, description="Search term matching meter ID or hardware serial number"),
    make: Optional[str] = Query(None, description="Filter by manufacturer: HPL, Genus, L&T, Secure, Allied"),
    phase_type: Optional[str] = Query(None, description="Filter by electrical phase: 'single' or 'three'"),
    install_status: Optional[str] = Query(None, description="Filter by operational status: 'Installed', 'Faulty', 'Decommissioned'"),
    dt_code: Optional[str] = Query(None, description="Filter by Distribution Transformer code (e.g. DT-001)"),
    build: Optional[str] = Query(None, description="Filter by firmware/generation: 'legacy' or 'v2'"),
    install_type: Optional[str] = Query(None, description="Filter by installation type: 'Whole Current' or 'CT Operated'"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    try:
        return await meter_service.list_meters(
            search=search,
            make=make,
            phase_type=phase_type,
            install_status=install_status,
            dt_code=dt_code,
            build=build,
            install_type=install_type,
            page=page,
            page_size=page_size,
        )
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/nearby",
    response_model=List[MeterNearbyItem],
    summary="Find smart meters near GPS coordinates",
    description="Perform a geospatial proximity search using the Haversine formula to find meters within a given radius.",
)
async def find_nearby_meters(
    lat: float = Query(..., description="Latitude of target origin coordinate", example=26.9389),
    lng: float = Query(..., description="Longitude of target origin coordinate", example=75.8309),
    radius_km: float = Query(5.0, ge=0.1, le=100.0, description="Search radius in kilometers", example=5.0),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of nearby meters to return"),
):
    try:
        return await meter_service.find_nearby_meters(
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            limit=limit,
        )
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/{meter_id}",
    response_model=MeterDetail,
    summary="Get detailed meter profile",
    description="Retrieve comprehensive specifications for a meter, including its location, full electrical hierarchy, and latest energy reading snapshot.",
)
async def get_meter_detail(
    meter_id: str,
):
    try:
        return await meter_service.get_meter_detail(meter_id=meter_id)
    except UrjaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/{meter_id}/readings",
    response_model=ReadingsResponse,
    summary="Get timeseries consumption readings and power metrics",
    description="Retrieve 30-minute interval readings for a meter with calculated interval consumption delta (kWh), power factor, and voltage metrics.",
)
async def get_meter_readings(
    meter_id: str,
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Limit the number of interval readings returned"),
    order: str = Query("asc", regex="^(asc|desc)$", description="Sort order by timestamp: 'asc' (oldest first) or 'desc' (newest first)"),
):
    try:
        return await meter_service.get_meter_readings(
            meter_id=meter_id,
            limit=limit,
            order=order,
        )
    except UrjaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
