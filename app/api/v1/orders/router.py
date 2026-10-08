from fastapi import APIRouter

from .routers.orders import router as orders_router

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)

router.include_router(orders_router)
