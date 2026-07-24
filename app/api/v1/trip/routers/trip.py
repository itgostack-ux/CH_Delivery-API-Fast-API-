from fastapi import APIRouter

from ..services.trip_service import TripService
from ..schemas.trip_schema import AcceptStartTripRequest

router = APIRouter()

service = TripService()


@router.get("/today-trip/{driver_id}")
def get_today_trip(driver_id: str):
    return service.get_today_trip(driver_id)


@router.post("/accept-start-trip")
def accept_start_trip(request: AcceptStartTripRequest):
    return service.accept_start_trip(request)