"""Business logic, caching layer, geospatial calculations, and data normalization."""

import asyncio
from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from app.client.urja_client import UrjaPortalClient
from app.client.exceptions import UrjaNotFoundError
from app.core.config import settings
from app.models.schemas import (
    GeoCoordinates,
    HierarchyNode,
    IntervalReading,
    MeterDetail,
    MeterNearbyItem,
    MeterReadingSummary,
    MeterSummary,
    NetworkHierarchy,
    PaginatedResponse,
    PaginationMetadata,
    ReadingsMetrics,
    ReadingsResponse,
    SyncStatusResponse,
    TransformerDetail,
    TransformerSummary,
)

logger = logging.getLogger(__name__)


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in kilometers between two points on Earth

    using the Haversine formula.
    """
    earth_radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(earth_radius_km * c, 3)


class MeterService:
    """Coordinates upstream data synchronization, in-memory caching,

    rich multi-attribute filtering, network hierarchy reconstruction,
    and geospatial querying.
    """

    def __init__(self, client: Optional[UrjaPortalClient] = None):
        self.client = client or UrjaPortalClient()

        # In-memory primary index structures
        self._meters_by_id: Dict[str, Dict[str, Any]] = {}
        self._transformers_by_code: Dict[str, Dict[str, Any]] = {}
        self._meters_by_dt: Dict[str, List[str]] = {}

        # Cache synchronization tracking
        self._last_synced_at: Optional[datetime] = None
        self._is_syncing: bool = False
        self._sync_lock = asyncio.Lock()

    @property
    def is_cache_fresh(self) -> bool:
        """Return True if cache has been populated and is within configured TTL."""
        if not self._last_synced_at or not self._meters_by_id:
            return False
        age = (datetime.now(timezone.utc) - self._last_synced_at).total_seconds()
        return age < settings.cache_ttl_seconds

    async def sync(self, force: bool = False) -> SyncStatusResponse:
        """Synchronize the local cache from upstream Urja Portal using bulk export and DT list."""
        if not force and self.is_cache_fresh:
            return self.get_sync_status()

        async with self._sync_lock:
            # Re-check under lock
            if not force and self.is_cache_fresh:
                return self.get_sync_status()

            self._is_syncing = True
            logger.info("Starting upstream synchronization with Urja Meter Ops...")

            try:
                # 1. Fetch all distribution transformers
                raw_dts = await self.client.get_all_transformers()
                new_dts: Dict[str, Dict[str, Any]] = {}
                for dt in raw_dts:
                    code = dt.get("code")
                    if code:
                        new_dts[code] = {
                            "code": code,
                            "name": dt.get("name", f"DT {code}"),
                            "feeder_code": dt.get("feederCode", "Unknown"),
                            "capacity_kva": float(dt.get("capacityKva", 100.0)),
                        }

                # 2. Fetch full meter registry via authenticated HMAC bulk export
                export_resp = await self.client.export_all_meters(page=1)
                raw_meters = export_resp.get("data", [])

                new_meters_by_id: Dict[str, Dict[str, Any]] = {}
                new_meters_by_dt: Dict[str, List[str]] = {}

                for m in raw_meters:
                    meter_id = m.get("meterId")
                    if not meter_id:
                        continue

                    dt_code = m.get("dtCode", "Unknown")
                    geo_data = m.get("geo")
                    location = None
                    if geo_data and "lat" in geo_data and "lng" in geo_data:
                        location = GeoCoordinates(
                            lat=float(geo_data["lat"]),
                            lng=float(geo_data["lng"]),
                        )

                    hierarchy_data = m.get("hierarchy", {})
                    network_hierarchy = None
                    if hierarchy_data:
                        try:
                            network_hierarchy = NetworkHierarchy(
                                zone=HierarchyNode(**hierarchy_data.get("zone", {"name": "Jaipur Zone 1", "code": "Z-01"})),
                                circle=HierarchyNode(**hierarchy_data.get("circle", {"name": "Circle 1", "code": "C-01"})),
                                division=HierarchyNode(**hierarchy_data.get("division", {"name": "Division 1", "code": "D-01"})),
                                subdivision=HierarchyNode(**hierarchy_data.get("subdivision", {"name": "Subdivision 1", "code": "SD-01"})),
                                substation=HierarchyNode(**hierarchy_data.get("substation", {"name": "Substation 1", "code": "SS-01"})),
                                feeder=HierarchyNode(**hierarchy_data.get("feeder", {"name": "Feeder 1", "code": "F-001"})),
                                dt=HierarchyNode(**hierarchy_data.get("dt", {"name": f"DT {dt_code}", "code": dt_code})),
                            )
                        except Exception as h_err:
                            logger.debug("Hierarchy parsing skipped for meter %s: %s", meter_id, h_err)

                    meter_entry = {
                        "meter_id": meter_id,
                        "serial_no": m.get("serialNo", ""),
                        "make": m.get("make", "Generic"),
                        "phase_type": m.get("phaseType", "single"),
                        "install_status": m.get("installStatus", "Installed"),
                        "install_type": m.get("installType", "Whole Current"),
                        "build": m.get("build", "legacy"),
                        "dt_code": dt_code,
                        "location": location,
                        "hierarchy": network_hierarchy,
                    }

                    new_meters_by_id[meter_id] = meter_entry
                    new_meters_by_dt.setdefault(dt_code, []).append(meter_id)

                # Atomically replace cache references
                self._meters_by_id = new_meters_by_id
                self._transformers_by_code = new_dts
                self._meters_by_dt = new_meters_by_dt
                self._last_synced_at = datetime.now(timezone.utc)

                logger.info(
                    "Synchronization complete: indexed %d meters across %d transformers",
                    len(self._meters_by_id),
                    len(self._transformers_by_code),
                )

            except Exception as exc:
                logger.error("Synchronization failed: %s", exc)
                raise
            finally:
                self._is_syncing = False

        return self.get_sync_status()

    def get_sync_status(self) -> SyncStatusResponse:
        """Return the current sync and cache health status."""
        return SyncStatusResponse(
            status="syncing" if self._is_syncing else ("synced" if self._meters_by_id else "uninitialized"),
            total_meters_indexed=len(self._meters_by_id),
            total_transformers_indexed=len(self._transformers_by_code),
            last_synced_at=self._last_synced_at.isoformat() if self._last_synced_at else None,
            cache_ttl_seconds=settings.cache_ttl_seconds,
            is_fresh=self.is_cache_fresh,
        )

    async def _ensure_cache(self):
        """Trigger background or immediate synchronization if cache is uninitialized or stale."""
        if not self._meters_by_id:
            await self.sync(force=True)
        elif not self.is_cache_fresh and not self._is_syncing:
            # Stale-While-Revalidate: trigger async background sync without blocking client
            asyncio.create_task(self.sync(force=True))

    def _to_meter_summary(self, item: Dict[str, Any]) -> MeterSummary:
        """Convert internal dictionary to public MeterSummary model."""
        return MeterSummary(
            meter_id=item["meter_id"],
            serial_no=item["serial_no"],
            make=item["make"],
            phase_type=item["phase_type"],
            install_status=item["install_status"],
            install_type=item.get("install_type"),
            build=item.get("build"),
            dt_code=item["dt_code"],
            location=item.get("location"),
        )

    async def list_meters(
        self,
        search: Optional[str] = None,
        make: Optional[str] = None,
        phase_type: Optional[str] = None,
        install_status: Optional[str] = None,
        dt_code: Optional[str] = None,
        build: Optional[str] = None,
        install_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[MeterSummary]:
        """Query and paginate meters with flexible multi-attribute filtering."""
        await self._ensure_cache()

        results: List[Dict[str, Any]] = list(self._meters_by_id.values())

        # 1. Search text filter (matches meter_id or serial_no case-insensitive)
        if search:
            query_clean = search.strip().lower()
            results = [
                m for m in results
                if query_clean in m["meter_id"].lower() or query_clean in m["serial_no"].lower()
            ]

        # 2. Make filter
        if make:
            make_clean = make.strip().lower()
            results = [m for m in results if m["make"].lower() == make_clean]

        # 3. Phase type filter (single, three)
        if phase_type:
            phase_clean = phase_type.strip().lower()
            results = [m for m in results if m["phase_type"].lower() == phase_clean]

        # 4. Installation status filter (Installed, Faulty, Decommissioned)
        if install_status:
            status_clean = install_status.strip().lower()
            results = [m for m in results if m["install_status"].lower() == status_clean]

        # 5. DT code filter
        if dt_code:
            dt_clean = dt_code.strip().upper()
            results = [m for m in results if m["dt_code"].upper() == dt_clean]

        # 6. Build filter (legacy, v2)
        if build:
            build_clean = build.strip().lower()
            results = [m for m in results if (m.get("build") or "").lower() == build_clean]

        # 7. Install type filter (Whole Current, CT Operated)
        if install_type:
            type_clean = install_type.strip().lower()
            results = [m for m in results if (m.get("install_type") or "").lower() == type_clean]

        total_records = len(results)
        page_size = max(1, min(page_size, 100))
        total_pages = max(1, math.ceil(total_records / page_size))
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = results[start_idx:end_idx]

        summaries = [self._to_meter_summary(m) for m in paginated_items]

        return PaginatedResponse(
            data=summaries,
            pagination=PaginationMetadata(
                page=page,
                page_size=page_size,
                total_records=total_records,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_meter_detail(self, meter_id: str) -> MeterDetail:
        """Retrieve full meter profile including network hierarchy and latest reading."""
        await self._ensure_cache()
        meter_id = meter_id.strip()

        meter_entry = self._meters_by_id.get(meter_id)
        if not meter_entry:
            # Fallback check against portal search in case of newly added meter
            search_res = await self.client.search_meters(query=meter_id, page=1)
            matching = [m for m in search_res.get("data", []) if m.get("meterId") == meter_id]
            if not matching:
                raise UrjaNotFoundError(f"Meter with ID '{meter_id}' not found")
            # If found upstream, trigger sync to update index
            asyncio.create_task(self.sync(force=True))
            # Temporary entry
            meter_entry = {
                "meter_id": meter_id,
                "serial_no": matching[0].get("serialNo", ""),
                "make": matching[0].get("make", "Generic"),
                "phase_type": matching[0].get("phaseType", "single"),
                "install_status": matching[0].get("installStatus", "Installed"),
                "install_type": "Whole Current",
                "build": "legacy",
                "dt_code": matching[0].get("dtCode", "Unknown"),
                "location": None,
                "hierarchy": None,
            }

        # Fetch latest reading snapshot from energy timeseries
        latest_reading = None
        try:
            raw_energy = await self.client.get_meter_energy(meter_id)
            if raw_energy:
                last = raw_energy[-1]
                latest_reading = MeterReadingSummary(
                    timestamp=last.get("timestamp", ""),
                    kwh=float(last.get("kwh", 0.0)),
                    kvah=float(last.get("kvah", 0.0)),
                    voltage_r=float(last["voltR"]) if "voltR" in last else None,
                )
        except Exception as e:
            logger.debug("Could not fetch energy readings for meter %s: %s", meter_id, e)

        return MeterDetail(
            meter_id=meter_entry["meter_id"],
            serial_no=meter_entry["serial_no"],
            make=meter_entry["make"],
            phase_type=meter_entry["phase_type"],
            install_status=meter_entry["install_status"],
            install_type=meter_entry.get("install_type"),
            build=meter_entry.get("build"),
            dt_code=meter_entry["dt_code"],
            location=meter_entry.get("location"),
            hierarchy=meter_entry.get("hierarchy"),
            latest_reading=latest_reading,
        )

    async def get_meter_readings(
        self,
        meter_id: str,
        limit: Optional[int] = None,
        order: str = "asc",
    ) -> ReadingsResponse:
        """Fetch chronological interval consumption readings and calculate interval deltas and metrics."""
        meter_id = meter_id.strip()
        raw_readings = await self.client.get_meter_energy(meter_id)

        if not raw_readings:
            # Check if meter exists
            await self._ensure_cache()
            if meter_id not in self._meters_by_id:
                raise UrjaNotFoundError(f"Meter with ID '{meter_id}' not found")

        # Process interval deltas and power factor
        processed: List[IntervalReading] = []
        prev_kwh: Optional[float] = None
        prev_kvah: Optional[float] = None

        voltages: List[float] = []
        delta_kwhs: List[float] = []
        power_factors: List[float] = []

        for r in raw_readings:
            kwh = float(r.get("kwh", 0.0))
            kvah = float(r.get("kvah", 0.0))
            voltage = float(r["voltR"]) if "voltR" in r else None

            delta_kwh = None
            power_factor = None

            if prev_kwh is not None:
                delta_kwh = max(0.0, round(kwh - prev_kwh, 3))
                delta_kwhs.append(delta_kwh)

            if prev_kvah is not None and prev_kwh is not None:
                delta_kvah = max(0.001, kvah - prev_kvah)
                if delta_kwh is not None and delta_kvah > 0:
                    pf = min(1.0, max(0.0, round(delta_kwh / delta_kvah, 3)))
                    power_factor = pf
                    power_factors.append(pf)

            if voltage is not None:
                voltages.append(voltage)

            processed.append(
                IntervalReading(
                    timestamp=r.get("timestamp", ""),
                    kwh=kwh,
                    kvah=kvah,
                    voltage_r=voltage,
                    delta_kwh=delta_kwh,
                    power_factor=power_factor,
                )
            )

            prev_kwh = kwh
            prev_kvah = kvah

        # Metrics compilation
        readings_count = len(processed)
        total_delta = round(sum(delta_kwhs), 2) if delta_kwhs else 0.0
        peak_delta = max(delta_kwhs) if delta_kwhs else 0.0
        avg_delta = round(total_delta / len(delta_kwhs), 3) if delta_kwhs else 0.0

        min_v = min(voltages) if voltages else 0.0
        max_v = max(voltages) if voltages else 0.0
        avg_v = round(sum(voltages) / len(voltages), 1) if voltages else 0.0
        avg_pf = round(sum(power_factors) / len(power_factors), 2) if power_factors else None

        metrics = ReadingsMetrics(
            readings_count=readings_count,
            window_start=processed[0].timestamp if processed else None,
            window_end=processed[-1].timestamp if processed else None,
            total_delta_kwh=total_delta,
            peak_interval_kwh=peak_delta,
            avg_interval_kwh=avg_delta,
            min_voltage_v=min_v,
            max_voltage_v=max_v,
            avg_voltage_v=avg_v,
            avg_power_factor=avg_pf,
        )

        # Sorting and pagination
        if order.lower() == "desc":
            processed.reverse()

        if limit and limit > 0:
            processed = processed[:limit]

        return ReadingsResponse(
            meter_id=meter_id,
            total_readings=len(processed),
            metrics=metrics,
            readings=processed,
        )

    async def list_transformers(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[TransformerSummary]:
        """List distribution transformers with downstream meter counts."""
        await self._ensure_cache()

        all_dts = list(self._transformers_by_code.values())
        total_records = len(all_dts)

        page_size = max(1, min(page_size, 100))
        total_pages = max(1, math.ceil(total_records / page_size))
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_dts = all_dts[start_idx:end_idx]

        summaries = [
            TransformerSummary(
                code=dt["code"],
                name=dt["name"],
                feeder_code=dt["feeder_code"],
                capacity_kva=dt["capacity_kva"],
                meter_count=len(self._meters_by_dt.get(dt["code"], [])),
            )
            for dt in paged_dts
        ]

        return PaginatedResponse(
            data=summaries,
            pagination=PaginationMetadata(
                page=page,
                page_size=page_size,
                total_records=total_records,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_transformer_detail(self, dt_code: str) -> TransformerDetail:
        """Get transformer specifications along with all connected smart meters."""
        await self._ensure_cache()
        dt_code = dt_code.strip().upper()

        dt = self._transformers_by_code.get(dt_code)
        if not dt:
            raise UrjaNotFoundError(f"Transformer '{dt_code}' not found")

        meter_ids = self._meters_by_dt.get(dt_code, [])
        connected_meters = [
            self._to_meter_summary(self._meters_by_id[m_id])
            for m_id in meter_ids
            if m_id in self._meters_by_id
        ]

        return TransformerDetail(
            code=dt["code"],
            name=dt["name"],
            feeder_code=dt["feeder_code"],
            capacity_kva=dt["capacity_kva"],
            meter_count=len(connected_meters),
            meters=connected_meters,
        )

    async def find_nearby_meters(
        self,
        lat: float,
        lng: float,
        radius_km: float = 5.0,
        limit: int = 20,
    ) -> List[MeterNearbyItem]:
        """Perform geospatial radius query to find smart meters near given coordinates."""
        await self._ensure_cache()

        nearby_items: List[Tuple[float, Dict[str, Any]]] = []

        for m in self._meters_by_id.values():
            loc = m.get("location")
            if not loc:
                continue
            dist = calculate_haversine_distance(lat, lng, loc.lat, loc.lng)
            if dist <= radius_km:
                nearby_items.append((dist, m))

        # Sort closest first
        nearby_items.sort(key=lambda x: x[0])

        if limit > 0:
            nearby_items = nearby_items[:limit]

        results: List[MeterNearbyItem] = []
        for dist, m in nearby_items:
            summary = self._to_meter_summary(m)
            results.append(
                MeterNearbyItem(
                    **summary.model_dump(),
                    distance_km=dist,
                )
            )

        return results

    async def get_network_hierarchy_tree(self) -> Dict[str, Any]:
        """Reconstruct the entire hierarchical electrical distribution tree:

        Zone -> Circle -> Division -> Subdivision -> Substation -> Feeder -> DT -> Meters.
        """
        await self._ensure_cache()

        tree: Dict[str, Any] = {
            "name": "Jaipur Distribution Grid",
            "zones": {},
        }

        for m in self._meters_by_id.values():
            h: Optional[NetworkHierarchy] = m.get("hierarchy")
            if not h:
                continue

            z_code = h.zone.code
            c_code = h.circle.code
            d_code = h.division.code
            sd_code = h.subdivision.code
            ss_code = h.substation.code
            f_code = h.feeder.code
            dt_code = h.dt.code

            # Nest zone
            if z_code not in tree["zones"]:
                tree["zones"][z_code] = {"name": h.zone.name, "code": z_code, "circles": {}}
            zone = tree["zones"][z_code]

            # Nest circle
            if c_code not in zone["circles"]:
                zone["circles"][c_code] = {"name": h.circle.name, "code": c_code, "divisions": {}}
            circle = zone["circles"][c_code]

            # Nest division
            if d_code not in circle["divisions"]:
                circle["divisions"][d_code] = {"name": h.division.name, "code": d_code, "subdivisions": {}}
            division = circle["divisions"][d_code]

            # Nest subdivision
            if sd_code not in division["subdivisions"]:
                division["subdivisions"][sd_code] = {"name": h.subdivision.name, "code": sd_code, "substations": {}}
            subdivision = division["subdivisions"][sd_code]

            # Nest substation
            if ss_code not in subdivision["substations"]:
                subdivision["substations"][ss_code] = {"name": h.substation.name, "code": ss_code, "feeders": {}}
            substation = subdivision["substations"][ss_code]

            # Nest feeder
            if f_code not in substation["feeders"]:
                substation["feeders"][f_code] = {"name": h.feeder.name, "code": f_code, "transformers": {}}
            feeder = substation["feeders"][f_code]

            # Nest transformer
            if dt_code not in feeder["transformers"]:
                feeder["transformers"][dt_code] = {
                    "name": h.dt.name,
                    "code": dt_code,
                    "meters_count": 0,
                    "meter_ids": [],
                }
            dt_entry = feeder["transformers"][dt_code]
            dt_entry["meters_count"] += 1
            dt_entry["meter_ids"].append(m["meter_id"])

        return tree


meter_service = MeterService()
