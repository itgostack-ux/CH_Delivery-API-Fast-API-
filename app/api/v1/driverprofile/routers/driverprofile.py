from fastapi import APIRouter

from ..services.driverprofile_service import DriverProfileService

router = APIRouter()

@router.get("/{email}")
def get_driver_profile(email: str):

    return DriverProfileService.get_profile(email)