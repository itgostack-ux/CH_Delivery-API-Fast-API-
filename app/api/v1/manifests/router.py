from fastapi import APIRouter

from .routers.manifests import router as manifests_router

router = APIRouter(
    prefix="/manifests",
    tags=["Manifests"]
)

router.include_router(manifests_router)
