"""End-to-end integration tests for Urja Gateway API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """Test /health endpoint returns status, uptime, and cache details."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "cache" in data
    assert data["cache"]["total_meters_indexed"] >= 400


@pytest.mark.asyncio
async def test_list_meters_pagination(async_client: AsyncClient):
    """Test /api/v1/meters pagination structure."""
    resp = await async_client.get("/api/v1/meters?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 10
    pagination = data["pagination"]
    assert pagination["page"] == 1
    assert pagination["page_size"] == 10
    assert pagination["total_records"] >= 400
    assert pagination["has_next"] is True


@pytest.mark.asyncio
async def test_list_meters_filter_search(async_client: AsyncClient):
    """Test /api/v1/meters text search by ID or Serial."""
    resp = await async_client.get("/api/v1/meters?search=J100000")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
    assert data["data"][0]["meter_id"] == "J100000"


@pytest.mark.asyncio
async def test_get_meter_detail_found(async_client: AsyncClient):
    """Test /api/v1/meters/{id} returns complete specifications and hierarchy."""
    resp = await async_client.get("/api/v1/meters/J100000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meter_id"] == "J100000"
    assert data["serial_no"] == "SE33962"
    assert "hierarchy" in data
    assert data["hierarchy"]["zone"]["code"] == "Z-01"


@pytest.mark.asyncio
async def test_get_meter_detail_not_found(async_client: AsyncClient):
    """Test /api/v1/meters/{id} returns 404 for invalid ID."""
    resp = await async_client.get("/api/v1/meters/INVALID_METER_XYZ")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_meter_readings(async_client: AsyncClient):
    """Test /api/v1/meters/{id}/readings returns timeseries and metrics."""
    resp = await async_client.get("/api/v1/meters/J100000/readings?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meter_id"] == "J100000"
    assert len(data["readings"]) == 5
    assert "metrics" in data
    assert data["metrics"]["total_delta_kwh"] > 0
    assert data["metrics"]["avg_voltage_v"] > 200


@pytest.mark.asyncio
async def test_list_transformers(async_client: AsyncClient):
    """Test /api/v1/transformers returns transformers with meter counts."""
    resp = await async_client.get("/api/v1/transformers?page=1&page_size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 20
    assert data["data"][0]["meter_count"] > 0


@pytest.mark.asyncio
async def test_get_transformer_detail(async_client: AsyncClient):
    """Test /api/v1/transformers/{code} returns attached meters."""
    resp = await async_client.get("/api/v1/transformers/DT-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "DT-001"
    assert len(data["meters"]) > 0


@pytest.mark.asyncio
async def test_network_hierarchy(async_client: AsyncClient):
    """Test /api/v1/network/hierarchy returns tree structure."""
    resp = await async_client.get("/api/v1/network/hierarchy")
    assert resp.status_code == 200
    tree = resp.json()
    assert "zones" in tree


@pytest.mark.asyncio
async def test_nearby_meters(async_client: AsyncClient):
    """Test /api/v1/meters/nearby returns distance-ranked items."""
    resp = await async_client.get("/api/v1/meters/nearby?lat=26.9389&lng=75.8309&radius_km=5.0")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    assert "distance_km" in items[0]
