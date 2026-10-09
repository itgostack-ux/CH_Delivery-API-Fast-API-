from datetime import datetime

from pydantic import BaseModel


class DriverStatus(BaseModel):
    driver_id: str
    full_name: str | None = None
    cell_number: str | None = None
    availability_status: str          # Available | Break | In Transit | Offline ...
    on_break: bool
    current_trip: str | None = None
    last_active: datetime | None = None


class DriverStatusResponse(BaseModel):
    success: bool = True
    message: str | None = None
    data: DriverStatus


class SignOutResponse(BaseModel):
    success: bool = True
    message: str
    availability_status: str
    devices_deactivated: int
