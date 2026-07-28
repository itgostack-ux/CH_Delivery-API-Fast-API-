from fastapi import APIRouter
from ..schemas.trip_schema import UploadPickupPhotoRequest
from ..services.trip_service import TripService
from ..schemas.trip_schema import AcceptStartTripRequest
from ..schemas.trip_schema import ConfirmDeliveryRequest
from ..schemas.trip_schema import ConfirmDeliveryRequest
from ..schemas.trip_schema import RequestDeliveryOTPRequest
from ..schemas.trip_schema import (
    AcceptStartTripRequest,
    ScanPickupQRRequest
)
router = APIRouter()

service = TripService()


@router.get("/today-trip/{driver_id}")
def get_today_trip(driver_id: str):
    return service.get_today_trip(driver_id)


@router.get("/notifications/{email}")
def get_notifications(email: str):
    return service.get_notifications(email)


@router.post("/accept-start-trip")
def accept_start_trip(request: AcceptStartTripRequest):
    return service.accept_start_trip(request)

@router.put("/notification/read/{notification_name}")
def mark_notification_read(notification_name: str):
    return service.mark_notification_read(notification_name)

@router.get("/accept-details/{trip_id}")
def get_accept_trip_details(trip_id: str):
    return service.get_accept_trip_details(trip_id)

@router.post("/scan-pickup-qr")
def scan_pickup_qr(request: ScanPickupQRRequest):
    return service.scan_pickup_qr(request)

@router.post("/upload-pickup-photo")
def upload_pickup_photo(request: UploadPickupPhotoRequest):
    return service.upload_pickup_photo(request)

@router.post("/confirm-delivery")
def confirm_delivery(request: ConfirmDeliveryRequest):
    return service.confirm_delivery(request)

@router.post("/request-delivery-otp")
def request_delivery_otp(
    request: RequestDeliveryOTPRequest
):
    return service.request_delivery_otp(request)
