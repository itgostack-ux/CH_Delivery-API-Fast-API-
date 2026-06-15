from fastapi import APIRouter

from ..services.logistics_service import LogisticsService

router = APIRouter()


@router.get("/trip-dashboard/{driver_id}/{trip_date}")
def trip_dashboard_summary(
    driver_id: str,
    trip_date: str
):

    return LogisticsService.trip_dashboard_summary(
        driver_id,
        trip_date
    )


@router.get("/trips/{driver_id}/{from_date}/{to_date}")
def trip_summary(
    driver_id: str,
    from_date: str,
    to_date: str
):

    return LogisticsService.trip_summary(
        driver_id,
        from_date,
        to_date
    )

@router.get("/trip-details/{trip_id}")
def trip_details(trip_id: str):

    return LogisticsService.trip_details(
        trip_id
    )

@router.get("/manifests/{driver_id}/{manifest_date}")
def manifest_summary(
    driver_id: str,
    manifest_date: str
):

    return LogisticsService.manifest_summary(
        driver_id,
        manifest_date
    )

@router.get("/manifest-details/{manifest_id}")
def manifest_details(manifest_id: str):

    return LogisticsService.manifest_details(
        manifest_id
    )