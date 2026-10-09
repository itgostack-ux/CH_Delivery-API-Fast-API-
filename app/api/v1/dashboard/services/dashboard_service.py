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


def _order_block(rows):

    by_status = {r["status"] or "Unknown": int(r["n"]) for r in rows}

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "total_qty": float(sum(r["qty"] for r in rows)),
    }


class DashboardService:

    @staticmethod
    def resolve_scope(user):
        """Anyone linked to a Driver record sees their own work (this is the
        driver app's dashboard, even for a System Manager who also drives);
        managers without a Driver record see every driver."""

        drivers = DashboardRepository.get_drivers_for_user(user["sub"])

        if not drivers:
            if set(user.get("roles", [])) & MANAGER_ROLES:
                return {"driver_id": None, "driver_name": None, "driver_ids": None}

            raise HTTPException(
                status_code=403,
                detail="No Driver record is linked to this user"
            )

        # A user may own several Driver records; report the first, query all.
        return {
            "driver_id": drivers[0]["driver_id"],
            "driver_name": drivers[0]["driver_name"],
            "driver_ids": [d["driver_id"] for d in drivers],
        }

    @staticmethod
    def get_dashboard(user):

        today = date.today()
        scope = DashboardService.resolve_scope(user)
        d = scope["driver_ids"]

        today_manifests = DashboardRepository.manifests_on(today, d)
        orders = DashboardRepository.orders_for_manifests([m["manifest_id"] for m in today_manifests])

        for manifest in today_manifests:
            manifest["orders"] = orders.get(manifest["manifest_id"], [])
            for order in manifest["orders"]:
                labels = [x for x in (order.pop("box_labels", None) or "").split(",") if x]
                order["box_labels"] = labels
                order["qr"] = labels[0] if labels else None

        return {
            "scope": {
                "role": user.get("role"),
                "driver_id": scope["driver_id"],
                "driver_name": scope.get("driver_name"),
                "driver_ids": scope.get("driver_ids"),
                "date": today,
            },
            "today": {
                "manifests": _manifest_block(DashboardRepository.manifest_summary(d, today)),
                "orders": _order_block(DashboardRepository.order_summary(d, today)),
                "trips": _trip_block(DashboardRepository.trip_summary(d, today)),
            },
            "overall": {
                "manifests": _manifest_block(DashboardRepository.manifest_summary(d)),
                "orders": _order_block(DashboardRepository.order_summary(d)),
                "trips": _trip_block(DashboardRepository.trip_summary(d)),
            },
            "today_manifests": today_manifests,
        }
