from fastapi import APIRouter, Depends, Request

from app.core.security import get_current_user, require_roles
from ..schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
)
from ..services.auth_service import AuthService

router = APIRouter()


@router.post("/login", response_model=LoginResponse, summary="Login with email & password")
def login(data: LoginRequest):

    return AuthService.login(data.email, data.password)


@router.post("/otp/request", response_model=OtpRequestResponse, summary="Send a login OTP to the user's email")
def request_otp(data: OtpRequest, request: Request):

    return AuthService.request_otp(
        data.email,
        ip_address=request.client.host if request.client else None
    )


@router.post("/otp/verify", response_model=LoginResponse, summary="Login with email & OTP")
def verify_otp(data: OtpVerifyRequest):

    return AuthService.verify_otp(data.email, data.otp)


@router.get("/me", summary="Current user from token")
def me(user: dict = Depends(get_current_user)):

    return {
        "success": True,
        "user": user
    }


@router.get("/admin-check", summary="Example: System Manager only")
def admin_check(user: dict = Depends(require_roles("System Manager"))):

    return {
        "success": True,
        "message": f"Hello {user['name']}, you are a System Manager"
    }
