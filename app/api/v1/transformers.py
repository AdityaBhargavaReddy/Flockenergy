"""Transformers API endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from app.client.exceptions import UrjaNotFoundError, UrjaPortalError
from app.models.schemas import PaginatedResponse, TransformerDetail, TransformerSummary
from app.services.meter_service import meter_service

router = APIRouter(prefix="/transformers", tags=["Transformers"])


@router.get(
    "",
    response_model=PaginatedResponse[TransformerSummary],
    summary="List distribution transformers",
    description="Retrieve a paginated list of distribution transformers (DTs) with their parent feeder and connected smart meter counts.",
)
async def list_transformers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    try:
        return await meter_service.list_transformers(page=page, page_size=page_size)
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/{code}",
    response_model=TransformerDetail,
    summary="Get transformer details with connected meters",
    description="Retrieve transformer specifications along with a list of all smart meters attached downstream.",
)
async def get_transformer_detail(
    code: str,
):
    try:
        return await meter_service.get_transformer_detail(dt_code=code)
    except UrjaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except UrjaPortalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
