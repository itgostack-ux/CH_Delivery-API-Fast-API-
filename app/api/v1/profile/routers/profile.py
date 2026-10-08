from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from ..schemas.profile_schema import ProfileResponse
from ..services.profile_service import ProfileService

router = APIRouter()


@router.get("/me", response_model=ProfileResponse, summary="Profile of the logged-in user (user, roles, driver records, delivery stats)")
def me(user: dict = Depends(get_current_user)):

    return ProfileService.me(user)
