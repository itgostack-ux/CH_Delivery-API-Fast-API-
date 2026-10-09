from fastapi import APIRouter

from .routers.driver import router as driver_router

router = APIRouter(
    prefix="/driver",
    tags=["Driver Status"]
)

router.include_router(driver_router)
