from fastapi import APIRouter
from .routers.manifest import router as manifest_router

router = APIRouter(
    prefix="/manifests",
    tags=["Manifests"]
)

router.include_router(manifest_router)