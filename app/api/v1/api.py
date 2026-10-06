from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.dashboard.router import router as dashboard_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
