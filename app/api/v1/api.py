from fastapi import APIRouter
from app.api.v1.logout.router import router as logout_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.driverprofile.router import router as driverprofile_router
from app.api.v1.manifests.router import router as manifest_router


api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(driverprofile_router)
api_router.include_router(logout_router)


api_router.include_router(manifest_router)