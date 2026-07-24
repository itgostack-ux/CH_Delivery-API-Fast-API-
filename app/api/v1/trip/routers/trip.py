from fastapi import APIRouter

from ..services.trip_service import TripService
from ..schemas.trip_schema import AcceptStartTripRequest

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