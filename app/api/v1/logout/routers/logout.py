from fastapi import APIRouter

from ..services.logout_service import LogoutService

router = APIRouter()


@router.post("/{email}")
def logout(email: str):

    return LogoutService.logout(email)