"""Pytest test configuration and fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.services.meter_service import meter_service


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def setup_test_cache():
    """Ensure in-memory cache is populated for testing."""
    await meter_service.sync(force=False)
    yield


@pytest.fixture
async def async_client():
    """Provide an asynchronous HTTP test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
