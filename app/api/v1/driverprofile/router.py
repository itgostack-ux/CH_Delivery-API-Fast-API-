from fastapi import APIRouter
from .routers.driverprofile import router as driverprofile_router

router = APIRouter(
    prefix="/driver-profile",
    tags=["Driver Profile"]
)

router.include_router(driverprofile_router)