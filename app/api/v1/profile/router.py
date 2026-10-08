from fastapi import APIRouter

from .routers.profile import router as profile_router

router = APIRouter(
    prefix="/profile",
    tags=["Profile"]
)

router.include_router(profile_router)
