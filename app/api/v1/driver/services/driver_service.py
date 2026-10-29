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


def _device(row):
    """CH Driver Device row (from the ERP or the DB) -> API shape; the token
    itself is never echoed back."""

    row = row or {}
    return {
        "name": row.get("name"),
        "device_id": row.get("device_id"),
        "platform": row.get("platform"),
        "app_version": row.get("app_version"),
        "is_active": bool(row.get("is_active")),
        "has_fcm_token": bool(row.get("fcm_token")) or bool(row.get("has_fcm_token")),
        "registered_on": row.get("registered_on"),
        "last_seen": row.get("last_seen"),
    }


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

    # ------------------------------------------------------------------
    # Devices & push tokens (tabCH Driver Device, via the ERP's own methods)
    # ------------------------------------------------------------------

    @staticmethod
    def register_device(user, data):
        """ERP driver_login: creates/updates the CH Driver Device row for this
        device_id (one row per handset, re-registration updates it), stores the
        FCM token, honours CH Logistics Settings.enforce_single_device (older
        handsets are deactivated) and sets the driver Available."""

        result = FrappeClient.call(DRIVER_API + "driver_login", {
            "device_id": data.device_id,
            "platform": data.platform,
            "fcm_token": data.fcm_token,
            "app_version": data.app_version,
        }, as_user=user["sub"]) or {}

        device = result.get("device") if isinstance(result, dict) else None
        if not isinstance(device, dict):
            device = AuthRepository.get_device(user["sub"], data.device_id) or {"device_id": data.device_id, "is_active": 1, "fcm_token": data.fcm_token}

        return {
            "message": "Device registered" + ("; push notifications enabled" if data.fcm_token else "; no FCM token yet"),
            "driver_id": result.get("driver") if isinstance(result, dict) else None,
            "availability_status": result.get("status") if isinstance(result, dict) else None,
            "device": _device(device),
            "push_enabled": bool(data.fcm_token),
        }

    @staticmethod
    def update_fcm_token(user, data):
        """ERP update_fcm_token: refresh the token of an existing device."""

        FrappeClient.call(DRIVER_API + "update_fcm_token",
                          {"device_id": data.device_id, "fcm_token": data.fcm_token}, as_user=user["sub"])

        device = AuthRepository.get_device(user["sub"], data.device_id)
        if device and not device.get("fcm_token"):
            device["fcm_token"] = data.fcm_token

        return {
            "message": "FCM token updated",
            "driver_id": (device or {}).get("driver"),
            "availability_status": None,
            "device": _device(device or {"device_id": data.device_id, "is_active": 1, "fcm_token": data.fcm_token}),
            "push_enabled": True,
        }

    @staticmethod
    def devices(user):
        """ERP get_active_devices: every handset bound to the driver."""

        rows = FrappeClient.call(DRIVER_API + "get_active_devices", {}, as_user=user["sub"]) or []
        tokens = {d["device_id"]: bool(d.get("fcm_token")) for d in AuthRepository.get_devices(user["sub"])}
        data = []
        for r in rows:
            d = _device(r)
            d["has_fcm_token"] = tokens.get(r.get("device_id"), False)
            data.append(d)

        return {"driver_id": next((d.get("driver") for d in AuthRepository.get_devices(user["sub"])), None),
                "count": len(data), "data": data}

    @staticmethod
    def remove_device(user, device_id):
        """ERP driver_logout(device_id): clears the token and deactivates that
        handset. Note: the ERP also sets the driver Offline, exactly like Sign
        Out on the ERP driver page."""

        result = FrappeClient.call(DRIVER_API + "driver_logout", {"device_id": device_id}, as_user=user["sub"]) or {}

        return {
            "message": f"Device {device_id} deactivated; driver set Offline",
            "driver_id": result.get("driver") if isinstance(result, dict) else None,
            "availability_status": result.get("status") if isinstance(result, dict) else "Offline",
            "device": _device({"device_id": device_id, "is_active": 0}),
            "push_enabled": False,
        }

    # ------------------------------------------------------------------
    # Notifications sent to the driver (tabNotification Log)
    # ------------------------------------------------------------------

    @staticmethod
    def _notification(row):
        import re
        body = re.sub(r"<[^>]+>", "", row.get("body") or "").strip()
        title = row.get("title") or ""
        kind = "alert"
        if "assigned" in title.lower():
            kind = "manifest_assigned"
        elif "recall" in title.lower():
            kind = "recall"
        elif "sent back" in title.lower() or "rejection" in title.lower():
            kind = "rejection_overruled"
        return {
            "id": row["name"], "title": title, "body": body, "kind": kind,
            "document_type": row.get("document_type"), "document_name": row.get("document_name"),
            "read": bool(row.get("read")), "created_at": row.get("creation"),
        }

    @staticmethod
    def notifications(user, limit=50, unread_only=False, since_days=30):

        rows, unread = AuthRepository.get_notifications(user["sub"], limit, unread_only, since_days)
        data = [DriverService._notification(r) for r in rows]
        return {"unread_count": unread, "count": len(data), "data": data}

    @staticmethod
    def mark_read(user, notification_id=None):
        """Frappe's own mark-as-read (notification_log.mark_as_read /
        mark_all_as_read), run as the driver so only their rows change."""

        if notification_id:
            FrappeClient.call("frappe.desk.doctype.notification_log.notification_log.mark_as_read",
                              {"docname": notification_id}, as_user=user["sub"])
            message = f"Notification {notification_id} marked read"
        else:
            FrappeClient.call("frappe.desk.doctype.notification_log.notification_log.mark_all_as_read",
                              {}, as_user=user["sub"])
            message = "All notifications marked read"

        _, unread = AuthRepository.get_notifications(user["sub"], 1)
        return {"message": message, "unread_count": unread}

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
