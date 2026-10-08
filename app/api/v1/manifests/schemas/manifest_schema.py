from datetime import date, datetime

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


class PendingManifestsResponse(BaseModel):
    success: bool = True
    count: int
    data: list[PendingManifest]


class RejectReasonsResponse(BaseModel):
    success: bool = True
    reasons: list[str]


class Receiver(BaseModel):
    email: str
    full_name: str | None = None
    first_name: str | None = None
    mobile_no: str | None = None
    is_home_store: bool = False


class ReceiversResponse(BaseModel):
    success: bool = True
    manifest_id: str
    store: str | None = None
    receivers: list[Receiver]


class Location(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    note: str | None = None          # e.g. "Phone Has No GPS" when no fix was captured


class PickupResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    status: str
    trip: str | None = None
    trip_started: bool
    pickup_datetime: datetime | None = None
    location: Location
    photos: list[str]


class SendOtpRequest(BaseModel):
    receiver: str = Field(description="Receiver email or name, from GET /manifests/{id}/receivers")


class SendOtpResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    receiver: str
    sent_to: str
    otp_log: str
    expires_in_seconds: int


class DeliverResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    status: str
    trip: str | None = None
    trip_closed: bool
    delivery_datetime: datetime | None = None
    receiver_name: str | None = None
    location: Location
    photos: list[str]


class ManifestActionResponse(BaseModel):
    success: bool = True
    message: str
    manifest_id: str
    status: str
    trip: str | None = None
    driver_accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    rejection_photos: list[str] = []
