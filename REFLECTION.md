# REFLECTION.md — Engineering Reflection & Trade-offs

This document reflects on the development of the Urja Meter Ops Gateway API, answering the core reflection questions outlined in the take-home specification.

---

### 1. What assumptions did you make?

- **Upstream Read-Only Invariance**: I assumed the Urja portal is strictly an operational inspection tool and that its underlying database schema and endpoints remain stable over the lifetime of a deployed gateway. I treated the portal strictly as read-only.
- **Single-Zone Grid Boundary**: All 403 meters in the portal are currently located within the greater Jaipur metropolitan area (lat ~26.9, lng ~75.8). I assumed that spatial proximity queries would primarily operate within municipal utility ranges (< 50 km) and used the Haversine formula on a spherical earth model rather than complex ellipsoidal projections (like WGS84 geodesic Vincenty), which would be unnecessary overhead for this scale.
- **Fixed Meter Population**: With 403 smart meters and 40 distribution transformers, the entire topology comfortably fits in memory (~2 MB footprint). I assumed that in-memory caching with asynchronous background refreshes (stale-while-revalidate) would deliver the best possible p99 latency (< 5ms) without burdening the local setup with Redis or PostgreSQL dependencies.
- **Register Cumulative Mechanics**: Based on standard utility AMI (Advanced Metering Infrastructure) conventions, I assumed the `kwh` and `kvah` metrics in `/portal/meters/{id}/energy` are cumulative register indices (like a car odometer). Delta consumption for any 30-minute interval was therefore assumed to be $C_t = \max(0, R_t - R_{t-1})$.

---

### 2. Which part was the most difficult, and how did you get unstuck?

The most challenging hurdle was discovering and deciphering the **bulk export HMAC signature mechanism**.

Initially, inspecting the UI network traffic only showed paginated search queries (`/portal/meters/search?q=&page=1`) returning 20 records at a time, with no attributes other than basic nameplate info. To assemble the full picture (location, hierarchy, technical specs) for all 403 meters, a naive approach would have required making hundreds of sequential HTTP calls. 

I decided to download and unpack the compiled Vite chunks (`4.2Bgc2kUI.js` and `6.l777LXKL.js`). Searching for `fetch(` calls in the AST revealed the `export_all` routine bound to `/portal/export?page=1`. However, direct requests returned `401 Unauthorized`. Reading through the minified JavaScript uncovered function `C`:
```javascript
let a = [e, t, n, i].join("\n");
let o = await crypto.subtle.importKey("raw", new TextEncoder().encode(r), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
```
By tracing `e` (HTTP method), `t` (path), `n` (query string), and `i` (unix timestamp in seconds), along with fetching the dynamic signing secret from `/portal/keys`, I was able to write an exact Python `hmac.new(secret, message, hashlib.sha256).hexdigest()` implementation. Unlocking this bulk path turned what would have been an unreliable, rate-limited crawling chore into an instantaneous, single-request sync.

---

### 3. If you had another day, what would you improve?

- **Persistent Relational / Geo Spatial Store**: While the in-memory cache is blazingly fast for 403 meters, an enterprise utility network managing 500,000+ smart meters would outgrow process memory. I would migrate the index to **PostgreSQL with PostGIS** (`ST_DWithin` spatial indices for sub-millisecond radius lookups) and **TimescaleDB** for hypertable timeseries partitioning of interval energy readings.
- **WebSocket / Event Stream for Anomalies**: I would introduce a streaming SSE (Server-Sent Events) or WebSocket channel to broadcast instant grid alerts when meters enter `Faulty` status or when voltage drifts outside standard Indian distribution limits ($230\text{V} \pm 6\% \implies [216.2\text{V}, 243.8\text{V}]$).
- **Automated Upstream Health Probing & Circuit Breaking**: If Urja Ops experiences an outage or database lockup, the client currently retries up to 3 times before returning a 502 Bad Gateway. With more time, I would implement a formal Circuit Breaker pattern (e.g. `pybreaker`) that trips to open state, serving cached data gracefully with an `X-Cache-Stale: true` header.

---

### 4. What mistake did you make while solving this (there's always one)?

When initially writing the login routine in Python, I fired a simple `requests.post(url, data={'email': ..., 'password': ...})` and was surprised to receive a `403 Forbidden` response despite valid credentials.

I initially suspected rate limiting, custom CAPTCHA cookies, or a hidden CSRF token in the HTML. However, after inspecting the DOM, no hidden CSRF token input existed. I then remembered that modern SvelteKit forms validate the HTTP `Origin` and `Referer` headers by default to protect against cross-site POST attacks. Because standard HTTP clients omit the `Origin` header on form submissions, SvelteKit immediately dropped the request. Once I added `Origin: https://urja-ops.flockenergy.tech` and `Referer: https://urja-ops.flockenergy.tech/login`, the portal instantly returned `200 OK` and issued the session cookie.

---

### 5. If you were reviewing your own submission, what would you criticise?

- **Tight Coupling to Portal Export Format**: The current `MeterService.sync()` relies heavily on `/portal/export` returning the complete 403-meter dataset with its existing hierarchy dictionary format. If the portal developers alter the casing or nesting of keys in `/portal/export`, the sync routine would fail and fall back to the slower search pagination. A more defensive mapper with schema fallback heuristics would make it even more resilient.
- **Synthetic Delta Readings on Edge Boundary**: In the `/readings` endpoint, the very first reading in the 7-day window does not have a preceding $t-1$ interval in the payload, so its `delta_kwh` is reported as `null` or `0.0`. In a production utility billing engine, we would query the preceding interval outside the window to compute an exact first delta.
- **Synchronous Testing Against Live Portal**: Although the tests run in just over 2 seconds, `test_live_portal_authentication` depends on external internet connectivity to `urja-ops.flockenergy.tech`. In a CI/CD environment with restricted outbound access, this could be flaky. Adding a complete set of recorded mock responses (using `respx` or `pytest-mock`) alongside the live integration tests would be best practice.
