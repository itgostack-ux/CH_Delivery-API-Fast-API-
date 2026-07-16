from fastapi import APIRouter
from app.api.v1.trip.routers.trip import router as trip_router

router = APIRouter()

router.include_router(
    trip_router,
    prefix="/trip",
    tags=["Trip"]
)