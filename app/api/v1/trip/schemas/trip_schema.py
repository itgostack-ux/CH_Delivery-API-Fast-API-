from pydantic import BaseModel
from typing import Optional

class TripResponse(BaseModel):
    tripId: int
    tripNo: str
    driver: str




class AcceptStartTripRequest(BaseModel):
    tripId: str
    driverId: str
    latitude: float
    longitude: float
    photo: Optional[str] = None
    notes: Optional[str] = None