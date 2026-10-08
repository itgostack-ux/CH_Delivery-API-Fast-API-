from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.core.security import require_roles
from ..schemas.manifest_schema import (
    DeliverResponse,
    ManifestActionResponse,  # noqa: F401 (reject response)
    PendingManifestsResponse,
    PickupResponse,
    ReceiversResponse,
    RejectReasonsResponse,
    SendOtpRequest,
    SendOtpResponse,
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


@router.get("/reject-reasons", response_model=RejectReasonsResponse, summary="Allowed rejection reasons (public)")
def reject_reasons():

    return ManifestService.reject_reasons()


@router.post(
    "/{manifest_id}/reject",
    response_model=ManifestActionResponse,
    summary="Reject Pickup: reason (+ optional notes and proof photos)",
)
def reject(
    manifest_id: str,
    reason: str = Form(..., description="One of GET /manifests/reject-reasons"),
    notes: str | None = Form(None, max_length=1000),
    photo1: UploadFile | None = File(None, description="Optional proof photo 1 (JPEG/PNG/WEBP, max 10 MB)"),
    photo2: UploadFile | None = File(None, description="Optional proof photo 2 (JPEG/PNG/WEBP, max 10 MB)"),
    user: dict = Depends(driver_only),
):

    return ManifestService.reject(user, manifest_id, reason, notes, photo1, photo2)


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
    qr: str = Form(..., description="Scanned QR (shipment id, e.g. GFTNMT26000183)"),
    photos: list[UploadFile] = File(..., description="At least one photo of the goods"),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy_m: float | None = Form(None),
    location_note: str | None = Form(None, description="Why no location, e.g. 'Phone Has No GPS'"),
    user: dict = Depends(driver_only),
):

    return DeliveryService.pickup(user, manifest_id, qr, photos, latitude, longitude, gps_accuracy_m, location_note)


@router.get(
    "/{manifest_id}/receivers",
    response_model=ReceiversResponse,
    summary="Who can sign for this delivery (users of the destination store)",
)
def receivers(manifest_id: str, user: dict = Depends(driver_only)):

    return DeliveryService.receivers(user, manifest_id)


@router.post(
    "/{manifest_id}/delivery-otp",
    response_model=SendOtpResponse,
    summary="Send OTP: emails a delivery OTP to the chosen receiver",
)
def send_delivery_otp(manifest_id: str, data: SendOtpRequest, request: Request, user: dict = Depends(driver_only)):

    return DeliveryService.send_delivery_otp(
        user, manifest_id, data.receiver,
        ip_address=request.client.host if request.client else None,
    )


@router.post(
    "/{manifest_id}/deliver",
    response_model=DeliverResponse,
    summary="Confirm & Deliver: scan manifest QR + receiver + delivery OTP + at least one photo (+ GPS)",
)
def deliver(
    manifest_id: str,
    qr: str = Form(..., description="Scanned QR (shipment id, e.g. GFTNMT26000183)"),
    receiver_name: str = Form(..., description="Who is signing for it at the store"),
    otp: str = Form(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="Delivery OTP from the receiver"),
    photos: list[UploadFile] = File(..., description="At least one photo of the goods"),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy_m: float | None = Form(None),
    location_note: str | None = Form(None, description="Why no location, e.g. 'Location Permission Blocked on Device'"),
    user: dict = Depends(driver_only),
):

    return DeliveryService.deliver(user, manifest_id, qr, receiver_name, otp, photos, latitude, longitude, gps_accuracy_m, location_note)
