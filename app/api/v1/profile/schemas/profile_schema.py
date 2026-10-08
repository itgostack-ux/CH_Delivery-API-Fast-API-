from datetime import date, datetime

from pydantic import BaseModel


class UserProfile(BaseModel):
    name: str
    email: str
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile_no: str | None = None
    phone: str | None = None
    user_image: str | None = None
    enabled: bool
    user_type: str | None = None
    last_login: datetime | None = None


class DriverProfile(BaseModel):
    """ERPNext Driver record (e.g. HR-DRI-2026-00008) linked to the user."""
    driver_id: str
    full_name: str | None = None
    status: str | None = None
    availability_status: str | None = None
    employee: str | None = None
    transporter: str | None = None
    cell_number: str | None = None
    address: str | None = None
    license_number: str | None = None
    issuing_date: date | None = None
    expiry_date: date | None = None
    partner_type: str | None = None
    courier_partner: str | None = None
    default_vehicle: str | None = None
    rating: float = 0
    total_deliveries: int = 0
    max_stops_per_trip: int | None = None
    current_trip: str | None = None
    last_active: datetime | None = None
    current_lat: float | None = None
    current_lng: float | None = None
    last_geo_at: datetime | None = None


class DeliveryStats(BaseModel):
    manifests_total: int = 0
    manifests_delivered: int = 0
    manifests_rejected: int = 0
    manifests_pending: int = 0
    orders_delivered: int = 0


class ProfileResponse(BaseModel):
    success: bool = True
    user: UserProfile
    roles: list[str]
    primary_role: str | None = None
    is_driver: bool
    driver: DriverProfile | None = None      # primary Driver record (first), for convenience
    drivers: list[DriverProfile]             # all Driver records linked to the user
    stats: DeliveryStats
