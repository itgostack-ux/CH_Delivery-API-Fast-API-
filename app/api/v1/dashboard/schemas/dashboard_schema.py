from datetime import date, datetime

from pydantic import BaseModel


class Scope(BaseModel):
    role: str
    driver_id: str | None = None      # None = all drivers (managers without a Driver record)
    driver_name: str | None = None
    driver_ids: list[str] | None = None   # every Driver record of the user
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
    box_labels: list[str] = []          # QR labels on the boxes, e.g. GFTNDC26000355-B01
    qr: str | None = None               # first box label = what to send as `qr` at pickup/deliver


class ManifestItem(BaseModel):
    manifest_id: str
    manifest_date: date
    trip_date: date | None = None
    status: str
    source_store: str | None = None
    destination_store: str | None = None
    trip: str | None = None
    trip_status: str | None = None
    driver: str | None = None
    driver_name: str | None = None
    stop_sequence: int | None = None
    priority: str | None = None
    total_items: int
    total_qty: float
    driver_accepted_at: datetime | None = None
    pickup_datetime: datetime | None = None
    delivery_datetime: datetime | None = None
    orders: list[OrderItem] = []


class DashboardResponse(BaseModel):
    success: bool = True
    scope: Scope
    today: dict[str, ManifestSummary | TripSummary | OrderSummary]
    overall: dict[str, ManifestSummary | TripSummary | OrderSummary]
    today_manifests: list[ManifestItem]
