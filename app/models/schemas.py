"""Pydantic models and schemas for the Urja Meter Ops Gateway API."""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class GeoCoordinates(BaseModel):
    """Geographic coordinates for a smart meter."""

    lat: float = Field(..., description="Latitude coordinate", example=26.938961)
    lng: float = Field(..., description="Longitude coordinate", example=75.830956)

    model_config = ConfigDict(from_attributes=True)


class HierarchyNode(BaseModel):
    """A node in the power distribution network hierarchy."""

    name: str = Field(..., description="Human-readable node name", example="Malviya Nagar DT 1")
    code: str = Field(..., description="Standard utility identifier code", example="DT-001")


class NetworkHierarchy(BaseModel):
    """Complete path in the utility distribution hierarchy."""

    zone: HierarchyNode = Field(..., description="Zone level")
    circle: HierarchyNode = Field(..., description="Circle level")
    division: HierarchyNode = Field(..., description="Division level")
    subdivision: HierarchyNode = Field(..., description="Subdivision level")
    substation: HierarchyNode = Field(..., description="Substation level")
    feeder: HierarchyNode = Field(..., description="Feeder level")
    dt: HierarchyNode = Field(..., description="Distribution transformer level")


class MeterReadingSummary(BaseModel):
    """Snapshot of the latest energy reading for a meter."""

    timestamp: str = Field(..., description="Reading timestamp", example="30/06/2026 23:30")
    kwh: float = Field(..., description="Cumulative active energy in kWh", example=48580.79)
    kvah: float = Field(..., description="Cumulative apparent energy in kVAh", example=52467.25)
    voltage_r: Optional[float] = Field(None, description="R-phase voltage in Volts", example=220.0)


class MeterSummary(BaseModel):
    """Standardized summary information for an electrical smart meter."""

    meter_id: str = Field(..., description="Unique meter identifier", example="J100000")
    serial_no: str = Field(..., description="Manufacturer hardware serial number", example="SE33962")
    make: str = Field(..., description="Meter manufacturer (HPL, Genus, L&T, Secure, Allied)", example="HPL")
    phase_type: str = Field(..., description="Phase configuration: single or three", example="single")
    install_status: str = Field(..., description="Operational status: Installed, Faulty, or Decommissioned", example="Installed")
    install_type: Optional[str] = Field(None, description="Metering setup: Whole Current or CT Operated", example="Whole Current")
    build: Optional[str] = Field(None, description="Firmware / device hardware generation (legacy or v2)", example="legacy")
    dt_code: str = Field(..., description="Connected distribution transformer code", example="DT-001")
    location: Optional[GeoCoordinates] = Field(None, description="GPS location of the meter")

    model_config = ConfigDict(populate_by_name=True)


class MeterDetail(MeterSummary):
    """Comprehensive meter profile including electrical hierarchy and latest reading."""

    hierarchy: Optional[NetworkHierarchy] = Field(None, description="Electrical network tree ancestry")
    latest_reading: Optional[MeterReadingSummary] = Field(None, description="Most recent cumulative energy reading")


class MeterNearbyItem(MeterSummary):
    """Meter returned from a spatial proximity query with calculated distance."""

    distance_km: float = Field(..., description="Calculated distance in kilometers from search point", example=1.42)


class IntervalReading(BaseModel):
    """Single timestamped consumption record."""

    timestamp: str = Field(..., description="Reading timestamp (DD/MM/YYYY HH:MM)", example="24/06/2026 00:00")
    kwh: float = Field(..., description="Cumulative register reading in kWh", example=48439.16)
    kvah: float = Field(..., description="Cumulative register reading in kVAh", example=52314.29)
    voltage_r: Optional[float] = Field(None, description="R-phase voltage (V)", example=229.0)
    delta_kwh: Optional[float] = Field(None, description="Calculated interval energy consumed (kWh) during this 30-min window", example=0.42)
    power_factor: Optional[float] = Field(None, description="Calculated power factor (kWh / kVAh ratio) for interval", example=0.92)


class ReadingsMetrics(BaseModel):
    """Aggregated consumption and power quality metrics over the reading period."""

    readings_count: int = Field(..., description="Total intervals analyzed")
    window_start: Optional[str] = Field(None, description="Start timestamp of interval window")
    window_end: Optional[str] = Field(None, description="End timestamp of interval window")
    total_delta_kwh: float = Field(..., description="Total active energy consumed over the period (kWh)", example=142.05)
    peak_interval_kwh: float = Field(..., description="Maximum consumption in a single 30-min window (kWh)", example=0.88)
    avg_interval_kwh: float = Field(..., description="Average consumption per 30-min interval (kWh)", example=0.42)
    min_voltage_v: float = Field(..., description="Minimum recorded voltage (V)", example=220.0)
    max_voltage_v: float = Field(..., description="Maximum recorded voltage (V)", example=240.0)
    avg_voltage_v: float = Field(..., description="Average recorded voltage (V)", example=229.8)
    avg_power_factor: Optional[float] = Field(None, description="Average estimated power factor", example=0.93)


class ReadingsResponse(BaseModel):
    """Timeseries energy reading dataset with analytical metrics."""

    meter_id: str = Field(..., description="Target meter ID", example="J100000")
    total_readings: int = Field(..., description="Number of readings returned", example=337)
    metrics: ReadingsMetrics = Field(..., description="Calculated consumption metrics")
    readings: List[IntervalReading] = Field(..., description="Chronological interval readings")


class TransformerSummary(BaseModel):
    """Distribution Transformer (DT) summary with downstream meter counts."""

    code: str = Field(..., description="DT identifier code", example="DT-001")
    name: str = Field(..., description="DT substation/asset name", example="Malviya Nagar DT 1")
    feeder_code: str = Field(..., description="Parent 11kV feeder code", example="F-001")
    capacity_kva: float = Field(..., description="Rated transformer capacity in kVA", example=100.0)
    meter_count: int = Field(..., description="Number of smart meters connected to this DT", example=11)


class TransformerDetail(TransformerSummary):
    """Detailed DT asset record with downstream connected smart meters."""

    meters: List[MeterSummary] = Field(default_factory=list, description="Downstream meters connected to this transformer")


class PaginationMetadata(BaseModel):
    """Pagination tracking information."""

    page: int = Field(..., description="Current page number (1-indexed)", example=1)
    page_size: int = Field(..., description="Items per page", example=20)
    total_records: int = Field(..., description="Total matching items across all pages", example=403)
    total_pages: int = Field(..., description="Total number of pages available", example=21)
    has_next: bool = Field(..., description="Whether a subsequent page exists", example=True)
    has_previous: bool = Field(..., description="Whether a previous page exists", example=False)


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized wrapper for paginated endpoints."""

    data: List[T]
    pagination: PaginationMetadata


class SyncStatusResponse(BaseModel):
    """Health and synchronization status of the gateway's local cache."""

    status: str = Field(..., description="System sync status: synced, syncing, or error", example="synced")
    total_meters_indexed: int = Field(..., description="Total meters currently in the local cache", example=403)
    total_transformers_indexed: int = Field(..., description="Total transformers indexed", example=40)
    last_synced_at: Optional[str] = Field(None, description="ISO timestamp of last successful upstream synchronization")
    cache_ttl_seconds: int = Field(..., description="Cache duration before next refresh cycle")
    is_fresh: bool = Field(..., description="True if local cache is within TTL, False if stale")
