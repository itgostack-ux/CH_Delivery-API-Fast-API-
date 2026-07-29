from pydantic import BaseModel
from typing import Optional
from pydantic import BaseModel
from pydantic import BaseModel

class TripResponse(BaseModel):
    tripId: int
    tripNo: str
    driver: str

from pydantic import BaseModel

class AcceptTripRequest(BaseModel):
    tripId: str
    driverId: str

class ScanPickupQRRequest(BaseModel):
    tripId: str
    driverId: str
    pickupToken: str
    latitude: float
    longitude: float

class UploadPickupPhotoRequest(BaseModel):
    manifestId: str
    photo: str
    latitude: float
    longitude: float
    notes: str | None = None

class ConfirmDeliveryRequest(BaseModel):
    tripId: str
    manifestId: str
    driverId: str

    deliveryToken: str
    otp: str

    receiverName: str
    deliveryPhoto: str

    notes: str | None = None

    latitude: float
    longitude: float



class RequestDeliveryOTPRequest(BaseModel):
    manifestId: str


class ConfirmStartTripRequest(BaseModel):
    tripId: str
    driverId: str
    latitude: float
    longitude: float
from pydantic import BaseModel
from typing import Optional

class RejectTripRequest(BaseModel):
    tripId: str
    driverId: str
    reason: str
    remarks: Optional[str] = None