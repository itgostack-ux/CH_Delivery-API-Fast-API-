from fastapi import APIRouter
from .routers.logout import router as logout_router

router = APIRouter(
    prefix="/logout",
    tags=["Logout"]
)

router.include_router(
    logout_router,
    prefix="/v1"
)