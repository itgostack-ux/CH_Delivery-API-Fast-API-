from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.core.security import require_roles
from ..schemas.manifest_schema import (
    BoxesResponse,
    DeliverResponse,
    ManifestActionResponse,  # noqa: F401 (reject response)
    PendingManifestsResponse,
    PickupAllResponse,
    PickupResponse,
    ReachedResponse,
    ReceiversResponse,
    RejectReasonsResponse,
    SendOtpRequest,
    SendOtpResponse,
    StoreDeliverResponse,
)
from ..services.delivery_service import DeliveryService
from ..services.manifest_service import ManifestService

router = APIRouter()

driver_only = require_roles("Driver")


# Driver flow, same as the ERPNext driver screens:
#   pending  ->  pickup (Accept & Pick Up)  ->  receivers -> delivery-otp (Send OTP) -> deliver
#            \-> reject (Reject Pickup)
# {manifest_id} accepts the manifest id, the shipment id (GFTNMT...) or the
# delivery challan (GFTNDC...) - whichever the app has on screen.


@router.get("/pending", response_model=PendingManifestsResponse, summary="Shipments assigned to me, awaiting Accept & Pick Up / Reject Pickup")
def pending(user: dict = Depends(driver_only)):

    return ManifestService.pending(user)


@router.get("/delivery-pending", response_model=PendingManifestsResponse, summary="Delivery Pending tab: shipments I have picked up and still need to deliver")
def delivery_pending(user: dict = Depends(driver_only)):

    return ManifestService.delivery_pending(user)


@router.get("/delivered", response_model=PendingManifestsResponse, summary="Delivered orders: my completed deliveries, one row per shipment (days=0 for the full history, paged)")
def delivered(
    days: int = Query(30, ge=0, le=3650, description="History window in days; 0 = all time"),
    limit: int = Query(200, ge=1, le=1000, description="Page size"),
    offset: int = Query(0, ge=0, description="Rows to skip (page 2 = offset=limit)"),
    user: dict = Depends(driver_only),
):
    """`total` is the number of delivered shipments in the window, so the app
    can show it as the driver's delivery count and page through the list."""

    return ManifestService.delivered(user, days, limit, offset)


@router.get("/reject-reasons", response_model=RejectReasonsResponse, summary="Allowed rejection reasons (public)")
def reject_reasons():

    return ManifestService.reject_reasons()


@router.post(
    "/{manifest_id}/reject",
    response_model=ManifestActionResponse,
    summary="Reject Pickup / Failed Delivery: reason + 2 different proof photos (+ notes, GPS) - ERP rules",
)
def reject(
    manifest_id: str,
    reason: str = Form(..., description="Pickup: Material Not Ready | Wrong Package | Store Closed | Damaged Package | Other. In transit: Customer Not Available | Address Not Found | Receiver Refused | Damaged in Transit | Vehicle Breakdown | Other"),
    photo1: UploadFile = File(..., description="Proof Photo 1 (JPEG/PNG/WEBP, max 10 MB)"),
    photo2: UploadFile = File(..., description="Proof Photo 2 - must be a different photo"),
    notes: str | None = Form(None, max_length=1000),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    user: dict = Depends(driver_only),
):

    return ManifestService.reject(user, manifest_id, reason, notes, photo1, photo2, latitude, longitude)


# ----------------------------------------------------------------------
# Pickup & delivery (mirrors ERPNext "Accept & Pick Up" / "Deliver" dialogs)
# ----------------------------------------------------------------------

@router.post(
    "/{manifest_id}/pickup",
    response_model=PickupResponse,
    summary="Accept & Pick Up: scan manifest QR + at least one photo of the goods (+ GPS)",
)
def pickup(
    manifest_id: str,
    qr: str = Form(..., description="Scanned box label from GET /boxes (e.g. GFTNDC26000355-B01)"),
    additional_qrs: str | None = Form(None, description="Other box labels, comma-separated (multi-box shipments)"),
    photo1: UploadFile = File(..., description="Photo of the goods (required)"),
    photo2: UploadFile | None = File(None, description="Optional extra photo"),
    photo3: UploadFile | None = File(None, description="Optional extra photo"),
    latitude: float | None = Form(None, description="GPS latitude, e.g. 13.0885"),
    longitude: float | None = Form(None, description="GPS longitude, e.g. 80.2435"),
    gps_accuracy_m: float | None = Form(None, description="GPS accuracy in metres, e.g. 7.2"),
    location_note: str | None = Form(None, description="Only when no GPS: e.g. 'Phone Has No GPS'"),
    override_empty_stops: bool = Form(False, description="Set true after the driver confirms starting a trip that has empty stops (ERP asks the same)"),
    geofence_override_reason: str | None = Form(None, max_length=300, description="Only after a GEOFENCE_OUT_OF_RANGE / GPS_IMPRECISE answer: the driver's reason for confirming they are at the pickup point (recorded on the manifest)"),
    user: dict = Depends(driver_only),
):

    return DeliveryService.pickup(user, manifest_id, qr, [photo1, photo2, photo3], latitude, longitude, gps_accuracy_m, location_note, additional_qrs, override_empty_stops, geofence_override_reason)


@router.post(
    "/{manifest_id}/pickup-all",
    response_model=PickupAllResponse,
    summary="Accept & Pick Up several shipments of one manifest at once: scan all their box labels, one photo, one GPS fix",
)
def pickup_all(
    manifest_id: str,
    qrs: str = Form(..., description="All scanned box labels, comma-separated, e.g. GFTNDC26002073-B01,GFTNDC26002084-B01 (every box of each shipment you want to accept)"),
    photo1: UploadFile = File(..., description="Photo of the goods (required, reused for every shipment)"),
    photo2: UploadFile | None = File(None),
    photo3: UploadFile | None = File(None),
    latitude: float | None = Form(None, description="GPS latitude"),
    longitude: float | None = Form(None, description="GPS longitude"),
    gps_accuracy_m: float | None = Form(None),
    location_note: str | None = Form(None, description="Only when no GPS (CH Logistics Settings must allow it)"),
    override_empty_stops: bool = Form(False, description="Set true after the driver confirms starting a trip that has empty stops"),
    geofence_override_reason: str | None = Form(None, max_length=300),
    user: dict = Depends(driver_only),
):
    """Each shipment is still accepted separately in ERPNext (its rule), so the
    response lists a verdict per shipment: accepted, already_accepted,
    not_scanned or failed. Shipments whose boxes were not all scanned fail
    with SCAN_REQUIRED while the others go through."""

    return DeliveryService.pickup_all(user, manifest_id, qrs, [photo1, photo2, photo3], latitude, longitude, gps_accuracy_m, location_note, override_empty_stops, geofence_override_reason)


@router.get(
    "/{manifest_id}/boxes",
    response_model=BoxesResponse,
    summary="Box labels to scan for this shipment (e.g. GFTNDC26000355-B01)",
)
def boxes(manifest_id: str, user: dict = Depends(driver_only)):

    return DeliveryService.boxes(user, manifest_id)


@router.get(
    "/{manifest_id}/receivers",
    response_model=ReceiversResponse,
    summary="Who can sign for this delivery (users of the destination store)",
)
def receivers(manifest_id: str, user: dict = Depends(driver_only)):

    return DeliveryService.receivers(user, manifest_id)


@router.get(
    "/{manifest_id}/reached",
    response_model=ReachedResponse,
    summary="Has the driver reached the drop location? Distance to the destination store vs the 50 m limit",
)
def reached(
    manifest_id: str,
    latitude: float = Query(..., description="Driver GPS latitude, e.g. 13.0843"),
    longitude: float = Query(..., description="Driver GPS longitude, e.g. 80.2623"),
    gps_accuracy_m: float | None = Query(None, description="GPS accuracy in metres"),
    user: dict = Depends(driver_only),
):
    """Call this when the driver taps Deliver: enable the Confirm & Deliver button
    only when `within_range` is true. POST /deliver enforces the same rule."""

    return DeliveryService.reached(user, manifest_id, latitude, longitude, gps_accuracy_m)


@router.post(
    "/{manifest_id}/delivery-otp",
    response_model=SendOtpResponse,
    summary="Send OTP to the chosen receiver (ERP request_delivery_otp)",
)
def send_delivery_otp(manifest_id: str, data: SendOtpRequest, user: dict = Depends(driver_only)):

    return DeliveryService.send_delivery_otp(user, manifest_id, data.receiver, data.stock_entries)


@router.post(
    "/{manifest_id}/deliver",
    response_model=DeliverResponse,
    summary="Confirm & Deliver: scan manifest QR + receiver + delivery OTP + at least one photo (+ GPS)",
)
def deliver(
    manifest_id: str,
    qr: str = Form(..., description="Scanned box label from GET /boxes (e.g. GFTNDC26000355-B01)"),
    additional_qrs: str | None = Form(None, description="Other box labels, comma-separated (multi-box shipments)"),
    receiver_name: str = Form(..., description="Receiver name exactly as returned by GET /receivers"),
    otp: str = Form(..., min_length=4, max_length=8, description="Delivery OTP the receiver got"),
    photo1: UploadFile = File(..., description="Photo of the delivery (required)"),
    photo2: UploadFile | None = File(None, description="Optional extra photo"),
    photo3: UploadFile | None = File(None, description="Optional extra photo"),
    latitude: float | None = Form(None, description="GPS latitude, e.g. 12.9594 - required when the store is geocoded (must be within 50 m)"),
    longitude: float | None = Form(None, description="GPS longitude, e.g. 80.2559"),
    gps_accuracy_m: float | None = Form(None, description="GPS accuracy in metres"),
    location_note: str | None = Form(None, description="Only when no GPS and the store has no geocode: e.g. 'Location Permission Blocked on Device'"),
    actual_distance_km: float | None = Form(None, ge=0, description="Actual Distance (km) driven for this delivery - optional"),
    geofence_override_reason: str | None = Form(None, max_length=300, description="Only after a GEOFENCE_OUT_OF_RANGE / GPS_IMPRECISE answer: the driver's reason for confirming they are at the store (recorded on the manifest; a far miss still needs dispatch)"),
    user: dict = Depends(driver_only),
):

    return DeliveryService.deliver(user, manifest_id, qr, receiver_name, otp, [photo1, photo2, photo3], latitude, longitude, gps_accuracy_m, location_note, additional_qrs, actual_distance_km, geofence_override_reason)


@router.post(
    "/{manifest_id}/deliver-store",
    response_model=StoreDeliverResponse,
    summary="Store drop: deliver every picked-up order going to this store with ONE OTP (ERP driver_complete_store_delivery)",
)
def deliver_store(
    manifest_id: str,
    qrs: str = Form(..., description="Box labels of ALL orders being dropped, comma-separated (one or more per order, from GET /boxes)"),
    receiver_name: str = Form(..., description="Receiver name exactly as returned by GET /receivers"),
    otp: str = Form(..., min_length=4, max_length=8, description="The single OTP sent via POST /delivery-otp with stock_entries"),
    stock_entries: str | None = Form(None, description="Optional: comma-separated shipment ids to deliver (default: every picked-up order of this driver going to the same store)"),
    photo1: UploadFile = File(..., description="Photo of the delivery (required)"),
    photo2: UploadFile | None = File(None),
    photo3: UploadFile | None = File(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy_m: float | None = Form(None),
    location_note: str | None = Form(None, description="Only when no GPS: reason (CH Logistics Settings must allow it)"),
    geofence_override_reason: str | None = Form(None, max_length=300),
    user: dict = Depends(driver_only),
):
    """One code, many orders: the ERP verifies the OTP once per manifest in the
    group and then records each order with its own scan, photo and GPS."""

    return DeliveryService.deliver_store(user, manifest_id, qrs, receiver_name, otp, [photo1, photo2, photo3], latitude, longitude, gps_accuracy_m, location_note, stock_entries, geofence_override_reason)
