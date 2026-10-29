from datetime import datetime

from pydantic import BaseModel, Field


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


class DeviceRegisterRequest(BaseModel):
    """App start / login: bind this handset to the driver (ERP driver_login)."""
    device_id: str = Field(min_length=4, max_length=140, description="Stable device identifier from the app (e.g. Android ID / installation id)")
    fcm_token: str | None = Field(None, max_length=4096, description="Firebase Cloud Messaging registration token")
    platform: str = Field("Android", pattern="^(Android|iOS|Web)$")
    app_version: str | None = Field(None, max_length=40)


class FcmTokenRequest(BaseModel):
    """Firebase rotated the token (onTokenRefresh): refresh it for this device."""
    device_id: str = Field(min_length=4, max_length=140)
    fcm_token: str = Field(min_length=20, max_length=4096)


class DriverDevice(BaseModel):
    name: str | None = None          # CH Driver Device record id
    device_id: str | None = None
    platform: str | None = None
    app_version: str | None = None
    is_active: bool = False
    has_fcm_token: bool = False
    registered_on: datetime | None = None
    last_seen: datetime | None = None


class DeviceResponse(BaseModel):
    success: bool = True
    message: str
    driver_id: str | None = None
    availability_status: str | None = None
    device: DriverDevice | None = None
    push_enabled: bool = False        # a non-empty FCM token is stored for this device


class DevicesResponse(BaseModel):
    success: bool = True
    driver_id: str | None = None
    count: int
    data: list[DriverDevice]


class DriverNotification(BaseModel):
    id: str                                   # Notification Log name (use for mark-as-read)
    title: str | None = None
    body: str | None = None
    kind: str | None = None                   # manifest_assigned | recall | rejection_overruled | alert ...
    document_type: str | None = None          # e.g. CH Logistics Trip / CH Transfer Manifest
    document_name: str | None = None          # e.g. BMTP26000001 / GFMF26001004
    read: bool = False
    created_at: datetime | None = None


class NotificationsResponse(BaseModel):
    success: bool = True
    unread_count: int
    count: int
    data: list[DriverNotification]


class NotificationReadResponse(BaseModel):
    success: bool = True
    message: str
    unread_count: int


class SignOutResponse(BaseModel):
    success: bool = True
    message: str
    availability_status: str
    devices_deactivated: int
