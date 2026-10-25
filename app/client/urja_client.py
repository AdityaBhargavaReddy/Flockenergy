"""HTTP Client interface to the upstream Urja Meter Ops legacy portal."""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.client.exceptions import (
    UrjaAuthenticationError,
    UrjaNotFoundError,
    UrjaPortalError,
    UrjaUpstreamError,
)

logger = logging.getLogger(__name__)


class UrjaPortalClient:
    """Encapsulates authentication, HMAC signing, session persistence,

    and error normalization when interfacing with Urja Meter Ops.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.urja_portal_url).rstrip("/")
        self.username = username or settings.urja_username
        self.password = password or settings.urja_password
        self.timeout = timeout or settings.request_timeout_seconds

        self._session_token: Optional[str] = None
        self._session_expires_at: float = 0.0
        self._auth_lock: Optional[asyncio.Lock] = None
        self._signing_secret: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazily initialize or retrieve the underlying HTTP client bound to the active loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._client is None
            or self._client.is_closed
            or self._client_loop != current_loop
        ):
            self._client_loop = current_loop
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=False,
                headers={
                    "User-Agent": "Urja-Gateway-Integration/1.0",
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/login",
                },
            )
        return self._client

    @property
    def auth_lock(self) -> asyncio.Lock:
        """Lazily initialize asyncio.Lock inside the active event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._auth_lock is None or self._client_loop != current_loop:
            self._auth_lock = asyncio.Lock()
        return self._auth_lock

    async def close(self):
        """Close the underlying HTTP client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _is_session_valid(self) -> bool:
        """Check if cached session token is still valid (with a 60-second safety margin)."""
        return bool(self._session_token and (time.time() < self._session_expires_at - 60))

    async def authenticate(self, force: bool = False) -> str:
        """Authenticate with the portal via POST /login and extract session cookie."""
        if not force and self._is_session_valid():
            return self._session_token  # type: ignore

        async with self.auth_lock:
            # Re-check inside lock to prevent concurrent redundant logins
            if not force and self._is_session_valid():
                return self._session_token  # type: ignore

            logger.info("Authenticating with upstream Urja portal as %s", self.username)
            login_url = f"{self.base_url}/login"
            payload = {
                "email": self.username,
                "password": self.password,
            }

            try:
                # SvelteKit checks Origin and Referer headers for form actions
                resp = await self.client.post(
                    "/login",
                    data=payload,
                    headers={
                        "Origin": self.base_url,
                        "Referer": login_url,
                    },
                )
            except httpx.RequestError as exc:
                logger.error("Network error during Urja login: %s", exc)
                raise UrjaUpstreamError(f"Connection failure during login: {exc}") from exc

            # The portal sets __Secure-better-auth.session_token
            session_cookie = resp.cookies.get("__Secure-better-auth.session_token")
            if not session_cookie and resp.status_code not in (200, 303):
                logger.error("Authentication rejected by Urja portal (HTTP %d): %s", resp.status_code, resp.text)
                raise UrjaAuthenticationError(f"Authentication rejected (HTTP {resp.status_code})")

            if not session_cookie:
                # Fallback to inspecting raw Set-Cookie header if cookies jar didn't parse
                set_cookie_header = resp.headers.get("set-cookie", "")
                if "__Secure-better-auth.session_token" in set_cookie_header:
                    parts = set_cookie_header.split("__Secure-better-auth.session_token=")[1].split(";")[0]
                    session_cookie = parts

            if not session_cookie:
                raise UrjaAuthenticationError("No session token cookie returned in login response")

            self._session_token = session_cookie
            # Portal sets Max-Age=3600 (1 hour). We store expiry.
            self._session_expires_at = time.time() + 3500
            logger.info("Successfully established authenticated session with Urja portal")
            return self._session_token

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Any] = None,
        allow_retry_auth: bool = True,
    ) -> httpx.Response:
        """Execute an authenticated request against the portal with auto-renewal & retry."""
        token = await self.authenticate()

        req_headers = {
            "Cookie": f"__Secure-better-auth.session_token={token}",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/meters",
        }
        if headers:
            req_headers.update(headers)

        for attempt in range(1, settings.max_retries + 1):
            try:
                resp = await self.client.request(
                    method=method,
                    url=path,
                    params=params,
                    headers=req_headers,
                    data=data,
                    json=json_data,
                )

                # Check for session expiration / auth redirect
                if resp.status_code in (401, 403) or (
                    resp.status_code == 303 and "/login" in resp.headers.get("location", "")
                ):
                    if allow_retry_auth and attempt < settings.max_retries:
                        logger.warning("Session token rejected or expired (HTTP %d). Re-authenticating...", resp.status_code)
                        token = await self.authenticate(force=True)
                        req_headers["Cookie"] = f"__Secure-better-auth.session_token={token}"
                        continue
                    raise UrjaAuthenticationError("Authentication expired and could not be renewed")

                if resp.status_code == 404:
                    raise UrjaNotFoundError(f"Resource not found at upstream {path}")

                if resp.status_code >= 500:
                    logger.warning("Upstream portal returned 5xx error (HTTP %d) on attempt %d", resp.status_code, attempt)
                    if attempt < settings.max_retries:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise UrjaUpstreamError(f"Upstream portal returned status {resp.status_code}")

                return resp

            except httpx.RequestError as exc:
                logger.warning("Network failure during request to %s (attempt %d): %s", path, attempt, exc)
                if attempt < settings.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise UrjaUpstreamError(f"Failed to communicate with portal: {exc}") from exc

        raise UrjaUpstreamError("Max retries exceeded while calling upstream portal")

    async def search_meters(self, query: str = "", page: int = 1) -> Dict[str, Any]:
        """Fetch paginated meters matching query from portal search endpoint."""
        resp = await self._request(
            "GET",
            "/portal/meters/search",
            params={"q": query, "page": page},
        )
        return resp.json()

    async def get_meter_geo(self, meter_id: str) -> Dict[str, Any]:
        """Retrieve geolocation coordinates for a specific meter."""
        resp = await self._request("GET", f"/portal/meters/{meter_id}/geo")
        return resp.json().get("data", {})

    async def get_meter_energy(self, meter_id: str) -> List[Dict[str, Any]]:
        """Retrieve recent timeseries consumption readings for a meter."""
        resp = await self._request("GET", f"/portal/meters/{meter_id}/energy")
        return resp.json().get("data", [])

    async def get_transformers_page(self, page: int = 1) -> Dict[str, Any]:
        """Fetch a single page of distribution transformers."""
        resp = await self._request("GET", "/portal/dts", params={"page": page})
        return resp.json()

    async def get_all_transformers(self) -> List[Dict[str, Any]]:
        """Fetch all distribution transformers across all pages."""
        all_dts: List[Dict[str, Any]] = []
        page = 1
        while True:
            res = await self.get_transformers_page(page=page)
            data = res.get("data", [])
            if not data:
                break
            all_dts.extend(data)
            total = res.get("total", len(all_dts))
            if len(all_dts) >= total:
                break
            page += 1
        return all_dts

    async def get_signing_secret(self) -> str:
        """Fetch the current HMAC signing secret for the bulk export API."""
        if self._signing_secret:
            return self._signing_secret

        resp = await self._request("GET", "/portal/keys")
        secret = resp.json().get("data", {}).get("signingSecret")
        if not secret:
            raise UrjaPortalError("Failed to retrieve signing secret from portal")
        self._signing_secret = secret
        return secret

    def compute_hmac_signature(self, method: str, path: str, query: str, timestamp: str, secret: str) -> str:
        """Compute HMAC-SHA-256 hex digest for signed endpoints."""
        message = f"{method}\n{path}\n{query}\n{timestamp}"
        return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

    async def export_all_meters(self, page: int = 1) -> Dict[str, Any]:
        """Call the bulk /portal/export endpoint using an HMAC-SHA-256 signature."""
        secret = await self.get_signing_secret()
        method = "GET"
        path = "/portal/export"
        query = f"page={page}"
        timestamp = str(int(time.time()))

        signature = self.compute_hmac_signature(method, path, query, timestamp, secret)

        resp = await self._request(
            method,
            f"{path}?{query}",
            headers={
                "x-timestamp": timestamp,
                "x-signature": signature,
            },
        )
        return resp.json()
