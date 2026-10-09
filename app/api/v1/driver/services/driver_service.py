"""Driver duty status - the AVAILABLE / Break / Sign Out strip of the ERP driver app.

    ch_logistics.api.driver_api.get_status   -> status strip
    ch_logistics.api.driver_api.set_break    -> Break button
    ch_logistics.api.driver_api.end_break    -> Resume button
    Sign Out: the ERP drops the driver to Offline from its logout hook; the
    API does the same by updating the Driver record through the ERP REST API.
"""

from fastapi import HTTPException

from app.core.frappe_client import FrappeClient
from app.core.security import revoke_token
from app.api.v1.auth.repositories.auth_repo import AuthRepository

DRIVER_API = "ch_logistics.api.driver_api."


def _shape(status):

    if not status:
        raise HTTPException(status_code=404, detail="No Driver record is linked to this user")

    availability = status.get("availability_status") or "Offline"

    return {
        "driver_id": status.get("name"),
        "full_name": status.get("full_name"),
        "cell_number": status.get("cell_number"),
        "availability_status": availability,
        "on_break": availability == "Break",
        "current_trip": status.get("current_trip"),
        "last_active": status.get("last_active"),
    }


class DriverService:

    @staticmethod
    def status(user):

        return {"data": _shape(FrappeClient.call(DRIVER_API + "get_status", {}, as_user=user["sub"]))}

    @staticmethod
    def start_break(user):

        FrappeClient.call(DRIVER_API + "set_break", {}, as_user=user["sub"])
        data = _shape(FrappeClient.call(DRIVER_API + "get_status", {}, as_user=user["sub"]))

        return {"message": "On break", "data": data}

    @staticmethod
    def end_break(user):

        FrappeClient.call(DRIVER_API + "end_break", {}, as_user=user["sub"])
        data = _shape(FrappeClient.call(DRIVER_API + "get_status", {}, as_user=user["sub"]))

        return {"message": "Back to work", "data": data}

    @staticmethod
    def set_availability(email, availability):
        """Update every Driver record of the user (ERP validations apply)."""

        updated = 0

        for driver_id in AuthRepository.get_driver_ids_for_user(email):
            FrappeClient.update_doc("Driver", driver_id, {"availability_status": availability})
            updated += 1

        return updated

    @staticmethod
    def sign_out(user):
        """End of shift: token revoked, app devices deactivated, driver Offline."""

        revoke_token(user)
        devices = AuthRepository.deactivate_devices(user["sub"])

        try:
            DriverService.set_availability(user["sub"], "Offline")
            availability = "Offline"
        except HTTPException as e:
            availability = f"unchanged ({e.detail})"

        return {
            "message": "Signed out for the day. You are marked Offline and need to log in again to receive new manifests.",
            "availability_status": availability,
            "devices_deactivated": devices,
        }

    @staticmethod
    def on_login(email):
        """Mirror the ERP login hook: an Offline driver comes back as Available."""

        try:
            for driver_id in AuthRepository.get_driver_ids_for_user(email):
                current = FrappeClient.call(DRIVER_API + "get_status", {}, as_user=email) or {}
                if (current.get("availability_status") or "Offline") == "Offline":
                    FrappeClient.update_doc("Driver", driver_id, {"availability_status": "Available"})
        except HTTPException:
            pass    # never block a login because of the status strip
