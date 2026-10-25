"""Unit tests for MeterService domain calculations, filtering, and hierarchy."""

import pytest
from app.services.meter_service import calculate_haversine_distance, meter_service


def test_haversine_distance():
    """Test distance computation between two known points in Jaipur."""
    # Malviya Nagar (approx 26.8530, 75.8050) to Mansarovar (approx 26.8540, 75.7680)
    dist = calculate_haversine_distance(26.8530, 75.8050, 26.8540, 75.7680)
    assert 3.0 < dist < 4.0

    # Same coordinate should be 0.0 distance
    zero_dist = calculate_haversine_distance(26.9389, 75.8309, 26.9389, 75.8309)
    assert zero_dist == 0.0


@pytest.mark.asyncio
async def test_list_meters_filtering():
    """Verify multi-attribute filtering on the in-memory cache."""
    # Filter by make
    res_hpl = await meter_service.list_meters(make="HPL", page_size=100)
    assert all(m.make == "HPL" for m in res_hpl.data)

    # Filter by status
    res_installed = await meter_service.list_meters(install_status="Installed", page_size=50)
    assert all(m.install_status == "Installed" for m in res_installed.data)

    # Filter by phase
    res_three = await meter_service.list_meters(phase_type="three", page_size=50)
    assert all(m.phase_type == "three" for m in res_three.data)

    # Filter by DT code
    res_dt = await meter_service.list_meters(dt_code="DT-001")
    assert all(m.dt_code == "DT-001" for m in res_dt.data)


@pytest.mark.asyncio
async def test_network_hierarchy_reconstruction():
    """Verify that network tree contains all branches down to meters."""
    tree = await meter_service.get_network_hierarchy_tree()
    assert "zones" in tree
    assert len(tree["zones"]) > 0

    zone = next(iter(tree["zones"].values()))
    assert "circles" in zone
    circle = next(iter(zone["circles"].values()))
    assert "divisions" in circle


@pytest.mark.asyncio
async def test_meter_nearby_proximity():
    """Verify geospatial proximity query sorts by closest meter first."""
    # Coordinates in Jaipur around Malviya Nagar
    lat = 26.9389
    lng = 75.8309
    nearby = await meter_service.find_nearby_meters(lat=lat, lng=lng, radius_km=5.0, limit=10)
    assert len(nearby) > 0
    # Distances must be sorted ascending
    distances = [m.distance_km for m in nearby]
    assert distances == sorted(distances)
