from fastapi import APIRouter, Depends, Query

from app.core.security import require_roles
from ..schemas.driver_schema import (
    DeviceRegisterRequest,
    DeviceResponse,
    DevicesResponse,
    DriverStatusResponse,
    FcmTokenRequest,
    NotificationReadResponse,
    NotificationsResponse,
    SignOutResponse,
)
from ..services.driver_service import DriverService

router = APIRouter()

driver_only = require_roles("Driver")


@router.get("/status", response_model=DriverStatusResponse, summary="Duty status strip: AVAILABLE / Break / In Transit / Offline")
def status(user: dict = Depends(driver_only)):

    return DriverService.status(user)


@router.post("/break", response_model=DriverStatusResponse, summary="Break: go off the clock (pickup/deliver blocked until resumed)")
def start_break(user: dict = Depends(driver_only)):

    return DriverService.start_break(user)


@router.post("/resume", response_model=DriverStatusResponse, summary="Resume: end the break")
def end_break(user: dict = Depends(driver_only)):

    return DriverService.end_break(user)


@router.post("/device", response_model=DeviceResponse, summary="Register this handset + FCM token (CH Driver Device) - call after login and on every app start")
def register_device(data: DeviceRegisterRequest, user: dict = Depends(driver_only)):
    """ERP driver_login: one CH Driver Device row per device_id (re-registering
    updates it), FCM token stored for push notifications, driver set Available.
    If CH Logistics Settings 'Enforce Single Device' is on, other handsets of
    the driver are deactivated."""

    return DriverService.register_device(user, data)


@router.put("/device/fcm-token", response_model=DeviceResponse, summary="Refresh the FCM token of this handset (Firebase onTokenRefresh)")
def update_fcm_token(data: FcmTokenRequest, user: dict = Depends(driver_only)):

    return DriverService.update_fcm_token(user, data)


@router.get("/devices", response_model=DevicesResponse, summary="Handsets bound to me (CH Driver Device)")
def devices(user: dict = Depends(driver_only)):

    return DriverService.devices(user)


@router.delete("/device/{device_id}", response_model=DeviceResponse, summary="Deactivate one handset and clear its FCM token (driver goes Offline, like ERP logout)")
def remove_device(device_id: str, user: dict = Depends(driver_only)):

    return DriverService.remove_device(user, device_id)


@router.get("/notifications", response_model=NotificationsResponse, summary="Notifications sent to me (every push also lands here), with unread count")
def notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    days: int = Query(30, ge=1, le=365, description="History window"),
    user: dict = Depends(driver_only),
):

    return DriverService.notifications(user, limit, unread_only, days)


@router.post("/notifications/read-all", response_model=NotificationReadResponse, summary="Mark all my notifications read")
def notifications_read_all(user: dict = Depends(driver_only)):

    return DriverService.mark_read(user)


@router.post("/notifications/{notification_id}/read", response_model=NotificationReadResponse, summary="Mark one notification read")
def notification_read(notification_id: str, user: dict = Depends(driver_only)):

    return DriverService.mark_read(user, notification_id)


@router.post("/sign-out", response_model=SignOutResponse, summary="Sign Out: end of shift - driver goes Offline and the token is invalidated")
def sign_out(user: dict = Depends(driver_only)):

    return DriverService.sign_out(user)
