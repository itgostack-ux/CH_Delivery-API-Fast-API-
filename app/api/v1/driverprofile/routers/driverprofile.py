from fastapi import APIRouter

from ..services.driverprofile_service import DriverProfileService
from ..schemas.driverprofile_schema import DriverDeviceRequest

router = APIRouter()


@router.get("/{email}")
def get_driver_profile(email: str):
    return DriverProfileService.get_profile(email)


@router.post("/device/register")
def register_device(request: DriverDeviceRequest):
    return DriverProfileService.register_device(request)