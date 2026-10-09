from fastapi import APIRouter, Depends

from app.core.security import require_roles
from ..schemas.driver_schema import DriverStatusResponse, SignOutResponse
from ..services.driver_service import DriverService

router = APIRouter()

driver_only = require_roles("Driver")


@router.get("/status", response_model=DriverStatusResponse, summary="Duty status strip: AVAILABLE / Break / In Transit / Offline")
def status(user: dict = Depends(driver_only)):

    return DriverService.status(user)


@router.post("/break", response_model=DriverStatusResponse, summary="Break: go off the clock (pickup/deliver blocked until resumed)")
def start_break(user: dict = Depends(driver_only)):

    return DriverService.start_break(user)


@router.post("/resume", response_model=DriverStatusResponse, summary="Resume: end the break")
def end_break(user: dict = Depends(driver_only)):

    return DriverService.end_break(user)


@router.post("/sign-out", response_model=SignOutResponse, summary="Sign Out: end of shift - driver goes Offline and the token is invalidated")
def sign_out(user: dict = Depends(driver_only)):

    return DriverService.sign_out(user)
