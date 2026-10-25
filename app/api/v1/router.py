"""V1 API Router aggregation."""

from fastapi import APIRouter

from app.api.v1.meters import router as meters_router
from app.api.v1.transformers import router as transformers_router
from app.api.v1.network import router as network_router
from app.api.v1.sync import router as sync_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(meters_router)
v1_router.include_router(transformers_router)
v1_router.include_router(network_router)
v1_router.include_router(sync_router)
