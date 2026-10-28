from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class PendingManifest(BaseModel):
    """One shipment awaiting Accept & Pick Up / Reject Pickup (as ERPNext lists them)."""
    manifest_id: str
    shipment_id: str | None = None          # Stock Entry, e.g. GFTNMT26000183 (the QR on the package)
    delivery_challan: str | None = None     # e.g. GFTNDC26000183 (title of the ERPNext dialogs)
    manifest_date: date
    status: str
    transfer_status: str | None = None
    logistics_status: str | None = None
    trip: str | None = None
    stop_sequence: int | None = None
    source_store: str | None = None
    destination_store: str | None = None
    from_warehouse: str | None = None
    to_warehouse: str | None = None
    priority: str | None = None
    total_items: int
    total_qty: float
    box_count: int | None = None
    estimated_delivery_date: date | None = None
    box_labels: list[str] = []          # QR labels on the boxes, e.g. GFTNDC26000355-B01
    qr: str | None = None               # first box label = what to send as `qr` at pickup/deliver
    driver_accepted_at: datetime | None = None      # manifest-level (all legs accepted)
    pickup_datetime: datetime | None = None
    delivery_datetime: datetime | None = None
    receiver_name: str | None = None
    # per-leg (this shipment only) - what the ERP driver app uses for its tabs
    stage: str = "pickup_pending"                   # pickup_pending | in_transit | delivered | rejected
    leg_accepted: bool = False                      # Accept Shipment done for THIS leg
    leg_accepted_at: datetime | None = None
    pickup_captured_at: datetime | None = None
    pickup_scanned_qr: str | None = None
    delivery_captured_at: datetime | None = None
    delivery_receiver_name: str | None = None


class PendingManifestsResponse(BaseModel):
    success: bool = True
    count: int
    data: list[PendingManifest]


class RejectReasonsResponse(BaseModel):
    success: bool = True
    reasons: list[str]                      # everything ERPNext accepts
    pickup_reasons: list[str] = []          # valid while the manifest is Assigned / Pickup Started
    in_transit_reasons: list[str] = []      # valid while In Transit (failed delivery)


class Receiver(BaseModel):
    """A POS Executive of the destination store (from the ERP's delivery_receivers)."""
    id: str | None = None
    name: str | None = None
    has_email: bool = False
    has_mobile: bool = False


class ReceiversResponse(BaseModel):
    success: bool = True
    manifest_id: str
    shipment_id: str | None = None
    store: str | None = None
    receivers: list[Receiver]


class BoxesResponse(BaseModel):
    success: bool = True
    manifest_id: str
    shipment_id: str | None = None
    delivery_challan: str | None = None
    box_count: int
    box_labels: list[str]
    hint: str


class Location(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    note: str | None = None          # e.g. "Phone Has No GPS" when no fix was captured


class StoreLocation(BaseModel):
    store: str | None = None
    store_name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    maps_url: str | None = None


class DriverLocation(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None


class Geofence(BaseModel):
    store: StoreLocation
    driver: DriverLocation
    limit_m: int
    distance_m: float | None = None
    within_range: bool | None = None     # None = not checked (no GPS / store not geocoded)
    enforced: bool
    note: str | None = None


class ReachedResponse(Geofence):
    success: bool = True
    manifest_id: str
    shipment_id: str | None = None
    status: str
    can_deliver: bool


class PickupResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    shipment_id: str | None = None
    status: str
    leg_accepted_at: datetime | None = None          # this shipment's own pickup stamp
    manifest_fully_accepted: bool | None = None      # every shipment of the manifest picked up
    trip: str | None = None
    pickup_datetime: datetime | None = None
    location: Location
    photos: list[str]
    erp: Any = None            # raw result of the ERP method, for debugging


class SendOtpRequest(BaseModel):
    receiver: str = Field(description="Receiver id or name from GET /manifests/{id}/receivers (free text if the store has no roster)")
    stock_entries: str | None = Field(None, description="Optional: comma-separated shipment ids (GFTNMT...) going to the SAME store to cover with ONE OTP (ERP store drop). Leave empty for a per-shipment OTP.")


class SendOtpResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    receiver: str
    sent_to: list[str]
    email_status: str = "unknown"       # sent | not_queued | not_sent | error ...
    warning: str | None = None
    covers_stock_entries: list[str] = []
    resend_after_seconds: int


class DeliverResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    shipment_id: str | None = None
    status: str
    trip: str | None = None
    leg_delivered_at: datetime | None = None         # this shipment's own delivery stamp
    manifest_fully_delivered: bool = False           # every shipment of the manifest delivered
    delivery_datetime: datetime | None = None
    receiver_name: str | None = None
    location: Location
    geofence: Geofence | None = None
    actual_distance_km: float | None = None
    photos: list[str]
    erp: Any = None


class StoreDeliverResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    shipment_id: str | None = None
    delivered: list[str] = []                        # shipment ids delivered with the one OTP
    manifests: dict[str, str | None] = {}            # manifest -> status afterwards
    receiver_name: str | None = None
    location: Location
    geofence: Geofence | None = None
    photos: list[str]
    erp: Any = None


class ManifestActionResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    status: str
    trip: str | None = None
    driver_accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    rejected_during: str | None = None      # Pickup | In Transit
    rejection_photos: list[str] = []
    erp: Any = None
