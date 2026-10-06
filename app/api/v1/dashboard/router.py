from fastapi import APIRouter

from .routers.dashboard import router as dashboard_router

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

router.include_router(dashboard_router)
