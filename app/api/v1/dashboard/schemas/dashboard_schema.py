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


class OrderSummary(BaseModel):
    """Stock Entries (Material Transfers, e.g. GFTNMT26000179) carried by the manifests."""
    total: int
    by_status: dict[str, int]
    total_qty: float


class OrderItem(BaseModel):
    order_id: str                      # Stock Entry name, e.g. GFTNMT26000179
    logistics_status: str | None = None
    transfer_status: str | None = None
    from_warehouse: str | None = None
    to_warehouse: str | None = None
    qty: float
    delivery_challan: str | None = None
    material_request: str | None = None


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
    orders: list[OrderItem] = []


class DashboardResponse(BaseModel):
    success: bool = True
    scope: Scope
    today: dict[str, ManifestSummary | TripSummary | OrderSummary]
    overall: dict[str, ManifestSummary | TripSummary | OrderSummary]
    today_manifests: list[ManifestItem]
