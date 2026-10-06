from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from ..schemas.dashboard_schema import DashboardResponse
from ..services.dashboard_service import DashboardService

router = APIRouter()


@router.get(
    "/summary",
    response_model=DashboardResponse,
    summary="Manifest & trip counts for the logged-in user (driver: own data; manager: all drivers)"
)
def get_dashboard(user: dict = Depends(get_current_user)):

    return DashboardService.get_dashboard(user)
