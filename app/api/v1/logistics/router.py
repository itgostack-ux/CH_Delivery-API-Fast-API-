from fastapi import APIRouter

from .routers.logistics import router as logistics_router

router = APIRouter()

router.include_router(
    logistics_router,
    tags=["Logistics"]
)