from datetime import date

from pydantic import BaseModel


class Scope(BaseModel):
    role: str
    driver_id: str | None = None      # None = all drivers (managers)
    driver_name: str | None = None
    date: date


class ManifestSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    total_items: int
    total_qty: float


class TripSummary(BaseModel):
    total: int
    by_status: dict[str, int]


class ManifestItem(BaseModel):
    manifest_id: str
    manifest_date: date
    status: str
    source_store: str | None = None
    destination_store: str | None = None
    trip: str | None = None
    priority: str | None = None
    total_items: int
    total_qty: float


class DashboardResponse(BaseModel):
    success: bool = True
    scope: Scope
    today: dict[str, ManifestSummary | TripSummary]
    overall: dict[str, ManifestSummary | TripSummary]
    today_manifests: list[ManifestItem]
