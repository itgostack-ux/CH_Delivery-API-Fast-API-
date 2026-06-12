from fastapi import APIRouter

from ..schemas.auth_schema import LoginRequest
from ..services.auth_service import AuthService

router = APIRouter()

@router.post("/login")
def login(data: LoginRequest):
    return AuthService.login(data)