from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.profile.router import router as profile_router
from app.api.v1.dashboard.router import router as dashboard_router
from app.api.v1.driver.router import router as driver_router
from app.api.v1.manifests.router import router as manifests_router
from app.api.v1.orders.router import router as orders_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(profile_router)
api_router.include_router(driver_router)
api_router.include_router(dashboard_router)
api_router.include_router(manifests_router)
api_router.include_router(orders_router)
