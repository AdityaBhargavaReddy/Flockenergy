"""Unit tests for the Upstream Urja Portal Client."""

import pytest
import time
from app.client.urja_client import UrjaPortalClient
from app.client.exceptions import UrjaAuthenticationError, UrjaNotFoundError


def test_hmac_signature_generation():
    """Verify HMAC-SHA-256 signature computation conforms to portal expectations."""
    client = UrjaPortalClient()
    secret = "test-secret-key-12345"
    timestamp = "1729838400"
    method = "GET"
    path = "/portal/export"
    query = "page=1"

    sig = client.compute_hmac_signature(method, path, query, timestamp, secret)

    # Re-calculate independently
    import hmac, hashlib
    expected_msg = f"{method}\n{path}\n{query}\n{timestamp}"
    expected_sig = hmac.new(secret.encode(), expected_msg.encode(), hashlib.sha256).hexdigest()

    assert sig == expected_sig
    assert len(sig) == 64


def test_session_validity_check():
    """Test session expiration helper logic."""
    client = UrjaPortalClient()
    assert client._is_session_valid() is False

    client._session_token = "dummy_token"
    client._session_expires_at = time.time() + 1000
    assert client._is_session_valid() is True

    # Near expiry (within 60s margin)
    client._session_expires_at = time.time() + 30
    assert client._is_session_valid() is False


@pytest.mark.asyncio
async def test_live_portal_authentication():
    """Integration test verifying authenticating against the live Urja portal."""
    client = UrjaPortalClient()
    token = await client.authenticate()
    assert token is not None
    assert len(token) > 10
    assert client._is_session_valid() is True
    await client.close()
