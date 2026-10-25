# Flock Energy — Urja Meter Ops Gateway API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-17%20Passed-10b981.svg)]()
[![OpenAPI](https://img.shields.io/badge/OpenAPI-3.1.0-6BA539.svg?logo=openapiinitiative&logoColor=white)](./openapi.json)

A clean, modern, documented, and resilient REST API service built in front of the legacy **Urja Meter Ops** internal portal (`https://urja-ops.flockenergy.tech`).

This gateway allows engineering, product, and data teams to access smart-meter registries, electrical network hierarchies, interval consumption timeseries, and geospatial proximity queries programmatically without interacting with the legacy portal.

---

## Quick Links to Key Deliverables

- 📄 **[PROTOCOL.md](./PROTOCOL.md)**: Forensic reverse-engineering report detailing how Urja Ops works, internal endpoints discovered, the hidden HMAC export path, SvelteKit CSRF quirks, and schema inconsistencies.
- 📐 **[openapi.json](./openapi.json)**: Complete OpenAPI 3.1 schema specification of this gateway service.
- 💭 **[REFLECTION.md](./REFLECTION.md)**: Candid engineering answers to the 5 take-home reflection prompts.
- 📊 **Interactive API Documentation**: Hosted locally at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` (ReDoc).
- ⚡ **Modern Operations Console**: Hosted locally at `http://localhost:8000/dashboard`.

---

## 1. What Was Built & Architecture

The service bridges the legacy Urja Ops portal and presents a unified, developer-friendly interface:

```
┌────────────────────────────────────────────────────────┐
│     Downstream Consumers (Data / Product / Engineers)  │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                 FastAPI Gateway Service                │
│  • OpenAPI 3.1 Documentation (/docs, /redoc)           │
│  • Operations Console Web Client (/dashboard)          │
│  • Spatial Proximity Engine (Haversine Formula)        │
│  • Hierarchy Tree Reconstructor (7-tier grid)          │
│  • Consumption Analytics (Interval deltas & voltage)   │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│          In-Memory Cache & Local Query Layer           │
│  • Stale-While-Revalidate TTL Caching                  │
│  • Multi-attribute filtering (Status, Make, DT, Phase) │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│             Resilient Urja Portal Client               │
│  • Session Cookie Persistence (better-auth)            │
│  • Auto-Reauthentication on Expiry (1-hr TTL)          │
│  • HMAC-SHA-256 Request Signing (/portal/export)       │
│  • Exponential Backoff & Retry Mechanism               │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│    Upstream Urja Meter Ops Portal (SvelteKit / Cloud)  │
└────────────────────────────────────────────────────────┘
```

### Core Capabilities
1. **Unified Schema Normalization**: Normalizes disparate data formats from older "legacy" meters (`detail.data` array of key-value tuples) and newer "v2" meters (`detail.classData` stringified JSON) into consistent Pydantic models.
2. **Advanced Multi-Attribute Querying**: The original portal search only matches meter IDs or serial numbers. This gateway adds multi-filter querying by `make` (HPL, Genus, L&T, Secure, Allied), `install_status` (Installed, Faulty, Decommissioned), `phase_type` (single, three), and `dt_code`.
3. **Geospatial Radius Query (`/api/v1/meters/nearby`)**: Answers "what's near this location?" using the Haversine formula to compute distance and rank meters within radius $R$ of given GPS coordinates.
4. **Electrical Network Hierarchy Reconstructor (`/api/v1/network/hierarchy`)**: Reconstructs the 7-tier distribution topology:
   $$\text{Zone} \to \text{Circle} \to \text{Division} \to \text{Subdivision} \to \text{Substation} \to \text{Feeder} \to \text{DT} \to \text{Meters}$$
5. **Consumption Register to Interval Delta Calculation**: Converts raw cumulative register readings (kWh / kVAh odometer values) into discrete 30-minute interval delta consumption, power factor estimations, and voltage metrics (min, max, average).
6. **The Bulk Path (HMAC-SHA-256 Export)**: Uses the discovered `/portal/export` endpoint signed with dynamic secrets from `/portal/keys` to sync all 403 meters in a single operation rather than making hundreds of sequential HTTP calls.
7. **Modern Web Client Dashboard**: A responsive operations console with live consumption timeseries charts (Chart.js), interactive hierarchy explorer, and spatial radius finder.

---

## 2. Project Structure

```
flockenergy/
├── .env.example              # Template environment variables
├── .env                      # Local environment configuration
├── .gitignore                # Git ignore rules
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest settings
├── run.py                    # Server launch script
├── run_tests.py              # Test suite runner script
├── openapi.json              # OpenAPI 3.1 specification (deliverable)
├── PROTOCOL.md               # Reverse engineering technical report (deliverable)
├── REFLECTION.md             # Reflection & trade-offs writeup (deliverable)
├── README.md                 # Primary documentation
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI application setup & lifespan
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py         # Pydantic BaseSettings management
│   ├── client/
│   │   ├── __init__.py
│   │   ├── urja_client.py    # Resilient upstream HTTP client (auth + HMAC)
│   │   └── exceptions.py     # Custom exception hierarchy
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py        # Pydantic v2 schemas and response contracts
│   ├── services/
│   │   ├── __init__.py
│   │   └── meter_service.py  # Cache, geo-spatial, and hierarchy logic
│   ├── api/
│   │   └── v1/
│   │       ├── router.py     # Router aggregator
│   │       ├── meters.py     # /meters, /meters/nearby, /meters/{id}/readings
│   │       ├── transformers.py # /transformers, /transformers/{code}
│   │       ├── network.py    # /network/hierarchy
│   │       └── sync.py       # /sync, /sync/status
│   └── static/               # Operations Console Web Client
│       ├── index.html        # Modern dashboard UI
│       ├── style.css         # Clean, dark-slate utility styling
│       └── app.js            # Client-side reactivity & Chart.js integration
└── tests/
    ├── __init__.py
    ├── conftest.py           # Test fixtures & test client setup
    ├── test_client.py        # UrjaPortalClient unit tests
    ├── test_meter_service.py # Domain math, geo distance, and hierarchy tests
    └── test_api.py           # End-to-end API integration tests
```

---

## 3. Installation & Getting Started

### Prerequisites
- Python 3.10+ (tested on Python 3.11)
- `pip` package manager

### Step 1: Clone & Setup
```bash
git clone https://github.com/your-username/flockenergy.git
cd flockenergy
```

### Step 2: Create Virtual Environment (Optional but Recommended)
```bash
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
A `.env` file is included, but you can configure `.env` based on `.env.example`:
```env
URJA_PORTAL_URL=https://urja-ops.flockenergy.tech
URJA_USERNAME=operator@urja.local
URJA_PASSWORD=urja-ops-2026

CACHE_TTL_SECONDS=300
SYNC_ON_STARTUP=true

API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

### Step 5: Start the API Gateway
```bash
python run.py
```
*Alternatively, run directly via Uvicorn:*
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Exploring the API & Dashboard

Once running, navigate to:
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Operations Console Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard) (or [http://localhost:8000/](http://localhost:8000/))
- **Raw OpenAPI Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 5. Sample API Requests & Responses

### 1. Health Check
```bash
curl -X GET "http://localhost:8000/health"
```
```json
{
  "status": "healthy",
  "uptime_seconds": 12.4,
  "upstream_target": "https://urja-ops.flockenergy.tech",
  "cache": {
    "status": "synced",
    "total_meters_indexed": 403,
    "total_transformers_indexed": 40,
    "last_synced_at": "2026-10-25T07:15:00.000000+00:00",
    "cache_ttl_seconds": 300,
    "is_fresh": true
  }
}
```

### 2. Multi-Attribute Meter Filtering
Query faulty, three-phase meters manufactured by Genus:
```bash
curl -X GET "http://localhost:8000/api/v1/meters?make=Genus&phase_type=three&install_status=Faulty"
```
```json
{
  "data": [
    {
      "meter_id": "J100014",
      "serial_no": "GE52551",
      "make": "Genus",
      "phase_type": "three",
      "install_status": "Faulty",
      "install_type": "Whole Current",
      "build": "legacy",
      "dt_code": "DT-015",
      "location": {
        "lat": 26.938961,
        "lng": 75.830956
      }
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_records": 1,
    "total_pages": 1,
    "has_next": false,
    "has_previous": false
  }
}
```

### 3. Detailed Meter Profile & Hierarchy
```bash
curl -X GET "http://localhost:8000/api/v1/meters/J100000"
```
```json
{
  "meter_id": "J100000",
  "serial_no": "SE33962",
  "make": "HPL",
  "phase_type": "single",
  "install_status": "Decommissioned",
  "install_type": "Whole Current",
  "build": "legacy",
  "dt_code": "DT-001",
  "location": {
    "lat": 26.938961002479868,
    "lng": 75.83095696146852
  },
  "hierarchy": {
    "zone": { "name": "Jaipur Zone 1", "code": "Z-01" },
    "circle": { "name": "Circle 1", "code": "C-01" },
    "division": { "name": "Division 1", "code": "D-01" },
    "subdivision": { "name": "Subdivision 1", "code": "SD-01" },
    "substation": { "name": "Substation 1", "code": "SS-01" },
    "feeder": { "name": "Feeder 1", "code": "F-001" },
    "dt": { "name": "Malviya Nagar DT 1", "code": "DT-001" }
  },
  "latest_reading": {
    "timestamp": "30/06/2026 23:30",
    "kwh": 48580.79,
    "kvah": 52467.25,
    "voltage_r": 220.0
  }
}
```

### 4. Timeseries Readings & Computed Delta Analytics
```bash
curl -X GET "http://localhost:8000/api/v1/meters/J100000/readings?limit=3&order=asc"
```
```json
{
  "meter_id": "J100000",
  "total_readings": 3,
  "metrics": {
    "readings_count": 337,
    "window_start": "23/06/2026 23:30",
    "window_end": "30/06/2026 23:30",
    "total_delta_kwh": 142.05,
    "peak_interval_kwh": 0.88,
    "avg_interval_kwh": 0.423,
    "min_voltage_v": 220.0,
    "max_voltage_v": 240.0,
    "avg_voltage_v": 229.8,
    "avg_power_factor": 0.93
  },
  "readings": [
    {
      "timestamp": "23/06/2026 23:30",
      "kwh": 48438.74,
      "kvah": 52313.84,
      "voltage_r": 226.0,
      "delta_kwh": null,
      "power_factor": null
    },
    {
      "timestamp": "24/06/2026 00:00",
      "kwh": 48439.16,
      "kvah": 52314.29,
      "voltage_r": 229.0,
      "delta_kwh": 0.42,
      "power_factor": 0.933
    },
    {
      "timestamp": "24/06/2026 00:30",
      "kwh": 48439.58,
      "kvah": 52314.75,
      "voltage_r": 220.0,
      "delta_kwh": 0.42,
      "power_factor": 0.913
    }
  ]
}
```

### 5. Geospatial Proximity Search
Find meters within 3 km of coordinates:
```bash
curl -X GET "http://localhost:8000/api/v1/meters/nearby?lat=26.9389&lng=75.8309&radius_km=3.0&limit=5"
```
```json
[
  {
    "meter_id": "J100000",
    "serial_no": "SE33962",
    "make": "HPL",
    "phase_type": "single",
    "install_status": "Decommissioned",
    "install_type": "Whole Current",
    "build": "legacy",
    "dt_code": "DT-001",
    "location": {
      "lat": 26.938961,
      "lng": 75.830956
    },
    "distance_km": 0.007
  }
]
```

---

## 6. Design Decisions & Trade-Offs

### In-Memory Query Engine vs. External Database
- **Decision**: Keep the primary index and geospatial calculations in memory within `MeterService`.
- **Rationale**: The total dataset is 403 meters and 40 distribution transformers (< 2 MB in RAM). For this volume, an external database (PostgreSQL/Redis) adds operational friction, external service requirements, and configuration complexity for reviewers. In-memory indexing provides sub-millisecond p99 latency without third-party dependencies.
- **Scale Limit**: This design remains effective up to approximately 100,000 meters. Beyond that, memory overhead, linear scanning, and garbage collection pressure require transitioning to PostgreSQL with PostGIS (`ST_DWithin` spatial indices) and TimescaleDB hypertables.

### Stale-While-Revalidate Caching
- **Decision**: When the 5-minute TTL expires, serve requests immediately from the existing in-memory cache and asynchronously spawn a background synchronization task.
- **Rationale**: Prevents cache-stampede issues and guarantees that user requests never experience latency spikes caused by waiting for upstream portal network roundtrips.

### Automatic Session Re-Authentication
- **Decision**: Track session expiration (`Max-Age=3600`) and automatically renew before expiry, with an inline fallback catch for unexpected 401/403 responses.
- **Rationale**: Urja Ops session cookies expire after 1 hour. A naive client would fail on the 61st minute; this client operates unattended indefinitely.

---

## 7. What Was Intentionally Left Out

1. **Write / Mutation Operations**: The prompt instructed: *"Treat the portal as read-only. You don't need to (and shouldn't try to) attack or break it"*. Consequently, no endpoints for creating, editing, or decommissioning meters were added.
2. **Third-Party Geospatial Database (PostGIS)**: Spatial indexing was implemented using the Haversine formula in pure Python rather than requiring a running PostgreSQL/PostGIS instance, ensuring any reviewer can clone and run the service without container setup.
3. **Heavy Front-End Build Tooling**: The operations dashboard uses vanilla HTML5/CSS and native JavaScript with Chart.js over CDN rather than a multi-gigabyte Webpack/Vite/Node toolchain, allowing FastAPI to serve it directly.

---

## 8. Running the Test Suite

The repository contains 17 comprehensive unit and integration tests covering the client, service calculations, geospatial proximity, and end-to-end API endpoints:

```bash
python run_tests.py
```
*Or using pytest directly:*
```bash
pytest -v
```

All 17 tests validate live upstream connectivity, error handling, signature hashing, and data normalization.

---

## 9. Deliverables Summary

| Deliverable | Location | Description |
|---|---|---|
| **API Source Code** | `app/` | FastAPI application, resilient client, Pydantic schemas, and routers |
| **API Documentation** | `openapi.json` | Complete OpenAPI 3.1 schema specification |
| **Reverse Engineering Protocol** | [PROTOCOL.md](./PROTOCOL.md) | Technical investigation report of Urja Ops |
| **Engineering Reflection** | [REFLECTION.md](./REFLECTION.md) | Answers to the 5 reflection questions & trade-off critique |
| **Operations Web Client** | `app/static/` | Visual operations dashboard (Charts, Hierarchy, Spatial search) |
| **Test Suite** | `tests/` | 17 unit and integration tests (`run_tests.py`) |
