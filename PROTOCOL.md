# PROTOCOL.md — Reverse Engineering the Urja Meter Ops Portal

This document details the internal architecture, authentication mechanics, data contracts, quirks, and hidden paths discovered while reverse-engineering the **Urja Meter Ops** legacy portal (`https://urja-ops.flockenergy.tech`).

---

## 1. Architecture & Tech Stack Discovery

Inspection of the HTTP headers, HTML structure, and client JavaScript bundles revealed that the portal is built on modern web primitives rather than classic server-rendered PHP or Java monoliths:

- **Framework**: **SvelteKit** (indicated by `X-Sveltekit-Page: true`, `body[data-sveltekit-preload-data]`, and `_app/immutable/` client bundles).
- **Client Rendering**: Hydrated Single-Page Application (SPA) with Svelte 5 runes (`$state`, `$derived`, runes-minified runtime `DHWw2r--.js`).
- **Session Layer**: Powered by **`better-auth`**, issuing an HTTP-only secure cookie named `__Secure-better-auth.session_token`.
- **Hosting / Network**: Cloudflare / Fastly reverse proxy with HTTP/3 support (`Alt-Svc: h3=":443"`).

---

## 2. Authentication & Session Management

### 2.1 The Login Flow
The portal login is hosted at `/login`. Attempting to submit credentials to the root `/` yields `405 Method Not Allowed`, as the SvelteKit form action is bound strictly to `/login`.

- **Endpoint**: `POST /login`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Payload**:
  ```http
  email=operator%40urja.local&password=urja-ops-2026
  ```

### 2.2 Security Quirks: CSRF & Origin Validation
SvelteKit enforces server-side Cross-Site Request Forgery (CSRF) protection on all form submissions. 
- Requests omitting the `Origin` or `Referer` headers receive `403 Forbidden`.
- **Solution in our Client**: The integration client explicitly sets:
  ```http
  Origin: https://urja-ops.flockenergy.tech
  Referer: https://urja-ops.flockenergy.tech/login
  ```

### 2.3 Session Lifetime & Invalidation
Upon successful authentication, the server responds with:
- **HTTP Status**: `200 OK` (with JSON `{"type":"redirect","status":303,"location":"/meters"}`)
- **Cookie**: `Set-Cookie: __Secure-better-auth.session_token=<token>; Max-Age=3600; Path=/; HttpOnly; Secure; SameSite=Lax`

**Key Observations**:
1. **Cookie Expiry**: The session expires after **3,600 seconds (1 hour)**.
2. **Behavior on Expiration**: When a token expires, calls to `/portal/*` return `401 Unauthorized` or redirect with `303 See Other` to `/login`.
3. **Resilience Strategy**: Our client maintains an in-memory expiration tracker (`time.time() + 3500`), pre-emptively refreshing the token before it expires, and catches any mid-flight `401`/`403` to automatically re-authenticate and retry.

---

## 3. Discovered Internal Endpoints

By analyzing the compiled Vite bundle map (`app.03ZTmlg3.js`, `4.2Bgc2kUI.js`, `5.C4dYcCRt.js`, `6.l777LXKL.js`), we mapped out the internal API surface consumed by the frontend:

### 3.1 Meter Search & Listing
- **Endpoint**: `GET /portal/meters/search?q={query}&page={page}`
- **Authentication**: `Cookie: __Secure-better-auth.session_token=...`
- **Response Structure**:
  ```json
  {
    "data": [
      {
        "meterId": "J100000",
        "serialNo": "SE33962",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Decommissioned",
        "dtCode": "DT-001"
      }
    ],
    "total": 403,
    "page": 1,
    "pageSize": 20
  }
  ```
- **Limitations Discovered**:
  - `pageSize` is **hardcoded to 20** on the portal; passing `pageSize=50` is ignored.
  - The query parameter `q` **only matches against `meterId` or `serialNo`**. Searching by `make` (e.g. `HPL`), `status` (e.g. `Faulty`), or `dtCode` (e.g. `DT-001`) returns **0 results**.
  - This severely limits utility operations staff who want to query by transformer or fault status.

### 3.2 Distribution Transformers (DTs)
- **Endpoint**: `GET /portal/dts?page={page}`
- **Response Structure**:
  ```json
  {
    "data": [
      {
        "code": "DT-001",
        "name": "Malviya Nagar DT 1",
        "feederCode": "F-001",
        "capacityKva": 100
      }
    ],
    "total": 40,
    "page": 1,
    "pageSize": 20
  }
  ```
- **Observations**:
  - Exactly 40 distribution transformers exist in the system across 2 pages.
  - There is **no individual DT endpoint** (calling `/portal/dts/DT-001` returns `404 Not Found`).

### 3.3 Meter Geolocation
- **Endpoint**: `GET /portal/meters/{meterId}/geo`
- **Response Structure**:
  ```json
  {
    "data": {
      "latitude": "26.938961002479868",
      "longitude": "75.83095696146852"
    }
  }
  ```
- **Surprise**: Coordinates are returned as strings rather than floating-point numbers.

### 3.4 Meter Timeseries Consumption
- **Endpoint**: `GET /portal/meters/{meterId}/energy`
- **Response Structure**:
  ```json
  {
    "data": [
      {
        "timestamp": "23/06/2026 23:30",
        "kwh": "48438.74",
        "kvah": "52313.84",
        "voltR": "226"
      },
      ...
      {
        "timestamp": "30/06/2026 23:30",
        "kwh": "48580.79",
        "kvah": "52467.25",
        "voltR": "220"
      }
    ]
  }
  ```
- **Domain Insights**:
  - The portal provides a fixed **7-day sliding window** with 30-minute intervals (337 records per meter).
  - Values represent **cumulative meter registers** (odometer style), not interval deltas. To find consumption in a 30-minute slot, one must calculate $\Delta\text{kWh} = \text{kwh}_t - \text{kwh}_{t-1}$.
  - Numbers are returned as strings; voltage is provided as `voltR` (R-phase voltage in Volts).

---

## 4. The Hidden Bulk Export Protocol (HMAC-SHA-256)

While inspecting the Transformers bundle (`4.2Bgc2kUI.js`), we uncovered a client function wired to an "Export" button:

```javascript
async function F() {
  let e = (await (await fetch('/portal/keys')).json()).data.signingSecret;
  let t = 'page=1';
  let { timestamp: n, signature: r } = await C('GET', '/portal/export', t, e);
  let i = await fetch('/portal/export?' + t, {
    headers: { 'x-timestamp': n, 'x-signature': r }
  });
  let a = await i.json();
}
```

### 4.1 How the Signature is Built:
1. Call `GET /portal/keys` to retrieve the current secret:
   ```json
   { "data": { "signingSecret": "I3dZPPf5CgTp7JyGNMI8i6z8LFR7TmSR" } }
   ```
2. Construct the canonical message:
   $$\text{message} = \text{METHOD} + \text{"\\n"} + \text{PATH} + \text{"\\n"} + \text{QUERY} + \text{"\\n"} + \text{TIMESTAMP}$$
   Example:
   ```text
   GET
   /portal/export
   page=1
   1729838400
   ```
3. Compute `HMAC-SHA-256(secret, message)` and encode as hexadecimal.
4. Pass headers:
   - `x-timestamp: <timestamp>`
   - `x-signature: <hex_signature>`

### 4.2 Why This Endpoint is Game-Changing:
Rather than issuing 403 individual HTTP requests to stitch together meter details, geo-coordinates, and network hierarchies, **`/portal/export?page=1` dumps the entire meter registry (all 403 meters) in a single normalized payload**.

Each record in the export contains:
- Nameplate attributes (`meterId`, `serialNo`, `make`, `phaseType`, `installStatus`, `installType`, `build`).
- Geo coordinates: `{ "lat": 26.9389..., "lng": 75.8309... }`.
- Complete 7-tier network hierarchy (`zone`, `circle`, `division`, `subdivision`, `substation`, `feeder`, `dt`).

---

## 5. Inconsistencies & Data Schema Fragmentation

When investigating the meter detail SSR route (`/meters/[id]/__data.json`), we discovered that the utility underwent a system migration that left behind two radically different schema designs:

### 5.1 Legacy Meters (238 devices)
Old firmware/deployments return details as an array of key-value tuples:
```json
"detail": {
  "data": [
    { "parameterName": "Meter ID", "parameterValue": "J100000" },
    { "parameterName": "Serial No", "parameterValue": "SE33962" },
    { "parameterName": "Make", "parameterValue": "HPL" },
    { "parameterName": "Phase Type", "parameterValue": "single" },
    { "parameterName": "Installation Status", "parameterValue": "Decommissioned" },
    { "parameterName": "Installation Type", "parameterValue": "Whole Current" }
  ]
}
```

### 5.2 V2 Meters (165 devices)
Newer firmware returns details as an embedded, escaped JSON string under `classData` with PascalCase keys:
```json
"detail": {
  "classData": "{\"installed_meter\":{\"MeterId\":\"J100004\",\"SerialNo\":\"SE65293\",\"Make\":\"Genus\",\"PhaseType\":\"single\",\"InstallationStatus\":\"Faulty\",\"InstallationType\":\"CT Operated\"}}"
}
```

### 5.3 How Our API Resolves This:
Our service normalizes both schema variants into a unified Pydantic `MeterSummary` and `MeterDetail` contract. Downstream consumers never need to know whether a meter was deployed in 2021 or 2026.

---

## 6. Grid Hierarchy Anatomy

The Jaipur electricity distribution utility models its grid across 7 organizational tiers:

```
[Zone]        Jaipur Zone 1 (Z-01)
  │
  └── [Circle]       Circle 1 (C-01)
        │
        └── [Division]      Division 1 (D-01)
              │
              └── [Subdivision]   Subdivision 1 (SD-01)
                    │
                    └── [Substation]    Substation 1 (SS-01)
                          │
                          └── [Feeder]        Feeder 1 (F-001) [11kV]
                                │
                                └── [DT]            Malviya Nagar DT 1 (DT-001)
                                      │
                                      └── [Meters]       J100000, J100001, ...
```

- **Meters per Transformer**: Average of 10–11 meters per DT across 40 DTs.
- **Feeder Mapping**: Every transformer belongs to a specific 11kV feeder (e.g. `F-001` to `F-004`).
