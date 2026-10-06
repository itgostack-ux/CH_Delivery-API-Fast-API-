from datetime import date

from fastapi import HTTPException

from ..repositories.dashboard_repo import DashboardRepository

MANAGER_ROLES = {"System Manager", "Delivery Manager"}


def _manifest_block(rows):

    by_status = {r["status"] or "Unknown": int(r["n"]) for r in rows}

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "total_items": int(sum(r["items"] for r in rows)),
        "total_qty": float(sum(r["qty"] for r in rows)),
    }


def _trip_block(rows):

    by_status = {r["status"] or "Unknown": int(r["n"]) for r in rows}

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
    }


class DashboardService:

    @staticmethod
    def resolve_scope(user):
        """Drivers only ever see their own data; managers see every driver."""

        if set(user.get("roles", [])) & MANAGER_ROLES:
            return {"driver_id": None, "driver_name": None}

        driver = DashboardRepository.get_driver_for_user(user["sub"])

        if not driver:
            raise HTTPException(
                status_code=403,
                detail="No Driver record is linked to this user"
            )

        return driver

    @staticmethod
    def get_dashboard(user):

        today = date.today()
        scope = DashboardService.resolve_scope(user)
        d = scope["driver_id"]

        return {
            "scope": {
                "role": user.get("role"),
                "driver_id": d,
                "driver_name": scope.get("driver_name"),
                "date": today,
            },
            "today": {
                "manifests": _manifest_block(DashboardRepository.manifest_summary(d, today)),
                "trips": _trip_block(DashboardRepository.trip_summary(d, today)),
            },
            "overall": {
                "manifests": _manifest_block(DashboardRepository.manifest_summary(d)),
                "trips": _trip_block(DashboardRepository.trip_summary(d)),
            },
            "today_manifests": DashboardRepository.manifests_on(today, d),
        }
