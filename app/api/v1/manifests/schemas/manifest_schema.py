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
    driver_accepted_at: datetime | None = None
    pickup_datetime: datetime | None = None
    delivery_datetime: datetime | None = None
    receiver_name: str | None = None


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


class PickupResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    shipment_id: str | None = None
    status: str
    trip: str | None = None
    pickup_datetime: datetime | None = None
    location: Location
    photos: list[str]
    erp: Any = None            # raw result of the ERP method, for debugging


class SendOtpRequest(BaseModel):
    receiver: str = Field(description="Receiver id or name from GET /manifests/{id}/receivers (free text if the store has no roster)")


class SendOtpResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    receiver: str
    sent_to: list[str]
    email_status: str = "unknown"       # sent | not_queued | not_sent | error ...
    warning: str | None = None
    resend_after_seconds: int


class DeliverResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    shipment_id: str | None = None
    status: str
    trip: str | None = None
    delivery_datetime: datetime | None = None
    receiver_name: str | None = None
    location: Location
    actual_distance_km: float | None = None
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
