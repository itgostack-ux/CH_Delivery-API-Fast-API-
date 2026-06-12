from fastapi import APIRouter

from ..services.manifest_service import ManifestService

router = APIRouter()


@router.get("/{driver_id}")
def get_manifests(driver_id: str):

    return ManifestService.get_manifests(
        driver_id
    )