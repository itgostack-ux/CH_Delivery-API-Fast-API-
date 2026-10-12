"""Pickup & delivery, delegated to the ERP's own driver-app methods.

The ERPNext "Delivery App" page calls these whitelisted methods; the API calls
exactly the same ones, as the same driver user, so behaviour is identical:

    ch_logistics.api.logistics_api.driver_accept_manifest_row   Accept & Pick Up
    ch_logistics.api.transfer_manifest_api.delivery_receivers    Receiver list
    ch_logistics.api.transfer_manifest_api.request_delivery_otp  Send OTP
    ch_logistics.api.transfer_manifest_api.driver_complete_delivery_row  Confirm & Deliver
"""

import json
import math

from fastapi import HTTPException

from app.core.config import settings
from app.core.frappe_client import FrappeClient
from ..repositories.delivery_repo import DeliveryRepository
from .manifest_service import ManifestService

LOGISTICS = "ch_logistics.api.logistics_api."
MANIFEST = "ch_logistics.api.transfer_manifest_api."


def _ensure_ok(result, failed_status=400):
    """ERP driver methods answer HTTP 200 even when the action failed and put
    the verdict in the payload ({"ok": false, "message": ...}). Turn that into
    an error so the app never sees "success" for a failed action."""

    if isinstance(result, dict) and result.get("ok") is False:
        message = result.get("message") or "ERPNext refused the action"
        status = 401 if result.get("otp_valid") is False else failed_status
        raise HTTPException(status_code=status, detail={"message": message, "erp": result})

    return result


def _clean_note(note):
    return None if not note or note.strip().lower() == "string" else note.strip()


def _distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres (haversine)."""

    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _split_qrs(value):
    """Comma-separated extra box labels; ignores Swagger's 'string' placeholder."""

    if not value:
        return []

    if isinstance(value, str):
        return [q.strip() for q in value.split(",") if q.strip() and q.strip().lower() != "string"]

    return list(value)


class DeliveryService:

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _owned(user, any_id):
        """Resolve manifest id / shipment id (GFTNMT...) / challan (GFTNDC...)
        and make sure it is assigned to one of this user's Driver records."""

        manifest_id = ManifestService.resolve(any_id)
        driver_ids = ManifestService._driver_ids_for(user)
        manifest = DeliveryRepository.get_manifest(manifest_id)

        if not manifest or manifest["docstatus"] == 2:
            raise HTTPException(status_code=404, detail="Manifest not found")

        if not manifest["driver"]:
            raise HTTPException(status_code=409, detail=f"Manifest is not assigned to any driver yet (status '{manifest['status']}')")

        if manifest["driver"] not in driver_ids:
            raise HTTPException(status_code=403, detail="This manifest is not assigned to you")

        # which shipment (leg) was addressed - the one named, else the first
        legs = [i["stock_entry"] for i in manifest["items"] if i["stock_entry"]]
        wanted = any_id.strip()
        manifest["stock_entry"] = wanted if wanted in legs else (legs[0] if legs else None)
        manifest["legs"] = legs

        return manifest

    @staticmethod
    def _upload_photos(user, manifest_id, uploads, stage):
        """Validate + upload photos to ERPNext as the driver; returns file URLs."""

        photos = [p for p in (ManifestService._read_photo(u, f"Photo {i + 1}") for i, u in enumerate(uploads or [])) if p]

        if not photos:
            raise HTTPException(status_code=422, detail=f"Take at least one photo of the {'goods' if stage == 'pickup' else 'delivery'}")

        urls = []

        for index, (filename, content, content_type) in enumerate(photos, start=1):
            uploaded = FrappeClient.upload_file(
                filename=f"{stage}_{manifest_id}_{index}_{filename}",
                content=content, content_type=content_type,
                doctype="CH Transfer Manifest", docname=manifest_id,
                as_user=user["sub"],
            )
            urls.append(uploaded["file_url"])

        return urls

    # ------------------------------------------------------------------
    # Drop-location geofence
    # ------------------------------------------------------------------

    @staticmethod
    def _geofence(manifest, lat, lng, accuracy=None):
        """Where the driver is vs. where the destination store is.

        Returns a dict for the response; the caller decides whether to block."""

        limit = settings.DELIVERY_GEOFENCE_M
        store = DeliveryRepository.get_store_location(manifest["destination_store"]) or {}
        store_loc = {
            "store": manifest["destination_store"],
            "store_name": store.get("store_name"),
            "address": store.get("address"),
            "latitude": store.get("latitude"),
            "longitude": store.get("longitude"),
            "maps_url": store.get("google_maps_url"),
        }

        info = {
            "store": store_loc,
            "driver": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy},
            "limit_m": limit,
            "distance_m": None,
            "within_range": None,
            "enforced": bool(limit) and store_loc["latitude"] is not None and store_loc["longitude"] is not None,
            "note": None,
        }

        if not limit:
            info["note"] = "Geofence disabled (DELIVERY_GEOFENCE_M=0)"
            return info

        if not info["enforced"]:
            info["note"] = f"Store {manifest['destination_store']} has no latitude/longitude in ERPNext (CH Store) - location not checked"
            return info

        if lat is None or lng is None:
            info["note"] = "GPS location required"
            return info

        info["distance_m"] = round(_distance_m(lat, lng, store_loc["latitude"], store_loc["longitude"]), 1)
        info["within_range"] = info["distance_m"] <= limit
        info["note"] = ("Reached the store" if info["within_range"]
                        else f"{info['distance_m']:.0f} m from the store, limit is {limit} m")
        return info

    @staticmethod
    def _require_at_store(manifest, lat, lng, accuracy=None):
        """Block the action unless the driver is within the geofence."""

        info = DeliveryService._geofence(manifest, lat, lng, accuracy)

        if not info["enforced"]:
            return info

        if lat is None or lng is None:
            raise HTTPException(status_code=422, detail={
                "code": "LOCATION_REQUIRED",
                "message": f"Send latitude/longitude: delivery is only allowed within {info['limit_m']} m of {manifest['destination_store']}",
                "geofence": info,
            })

        if not info["within_range"]:
            raise HTTPException(status_code=409, detail={
                "code": "OUT_OF_RANGE",
                "message": f"You are {info['distance_m']:.0f} m from {manifest['destination_store']}; move within {info['limit_m']} m of the store to deliver",
                "geofence": info,
            })

        return info

    @staticmethod
    def reached(user, any_id, lat, lng, accuracy=None):
        """Pre-check for the app: has the driver reached the drop location?
        Never raises for distance - returns within_range true/false."""

        manifest = DeliveryService._owned(user, any_id)
        info = DeliveryService._geofence(manifest, lat, lng, accuracy)

        return {
            "manifest_id": manifest["manifest_id"],
            "shipment_id": manifest["stock_entry"],
            "status": manifest["status"],
            "can_deliver": manifest["status"] == "In Transit" and (info["within_range"] is True or not info["enforced"]),
            **info,
        }

    # ------------------------------------------------------------------
    # Box labels (the QR codes printed on the boxes)
    # ------------------------------------------------------------------

    @staticmethod
    def boxes(user, any_id):
        """Labels the driver must scan at pickup and delivery, e.g. GFTNDC26000355-B01.
        Same ERP method the Delivery App uses (get_stock_entry_box_labels)."""

        manifest = DeliveryService._owned(user, any_id)
        labels = FrappeClient.call(LOGISTICS + "get_stock_entry_box_labels",
                                   {"stock_entry": manifest["stock_entry"]}, as_user=user["sub"]) or []

        return {
            "manifest_id": manifest["manifest_id"],
            "shipment_id": manifest["stock_entry"],
            "delivery_challan": labels[0].rsplit("-B", 1)[0] if labels else None,
            "box_count": len(labels),
            "box_labels": labels,
            "hint": "Scan every label; send the first as `qr` and the rest as `additional_qrs` (comma-separated).",
        }

    # ------------------------------------------------------------------
    # Receivers
    # ------------------------------------------------------------------

    @staticmethod
    def receivers(user, any_id):

        manifest = DeliveryService._owned(user, any_id)

        rows = FrappeClient.call(MANIFEST + "delivery_receivers",
                                 {"manifest": manifest["manifest_id"], "stock_entry": manifest["stock_entry"]},
                                 as_user=user["sub"]) or []

        return {
            "manifest_id": manifest["manifest_id"],
            "shipment_id": manifest["stock_entry"],
            "store": manifest["destination_store"],
            "receivers": [
                {"id": r.get("name"), "name": r.get("executive_name"),
                 "has_email": bool(r.get("has_email")), "has_mobile": bool(r.get("has_mobile"))}
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # Accept & Pick Up
    # ------------------------------------------------------------------

    @staticmethod
    def pickup(user, any_id, qr, photos, lat, lng, accuracy, location_note, additional_qrs=None, override_empty_stops=False):

        additional_qrs = _split_qrs(additional_qrs)
        location_note = _clean_note(location_note)

        manifest = DeliveryService._owned(user, any_id)
        mid, se = manifest["manifest_id"], manifest["stock_entry"]

        if manifest["status"] != "Assigned":
            raise HTTPException(status_code=409, detail=f"Pickup not allowed in status '{manifest['status']}'")

        if not manifest["trip"]:
            raise HTTPException(status_code=409, detail="Manifest is not attached to a trip yet")

        urls = DeliveryService._upload_photos(user, mid, photos, "pickup")

        args = {
            "trip": manifest["trip"],
            "manifest": mid,
            "stock_entry": se,
            "pickup_photo": urls[0],
            "pickup_photos": json.dumps(urls),
            "scanned_qr": qr.strip(),
            "additional_scanned_qrs": json.dumps(additional_qrs or []),
            "lat": lat,
            "lng": lng,
            "gps_accuracy_m": accuracy,
            "no_location_reason": location_note if lat is None or lng is None else None,
            "override_empty_stops": 1 if override_empty_stops else 0,
        }

        try:
            result = _ensure_ok(FrappeClient.call(LOGISTICS + "driver_accept_manifest_row", args, as_user=user["sub"]))
        except HTTPException as e:
            # Same pre-flight as the ERP driver app: it warns about empty stops
            # and lets the driver continue; the app should confirm and resend.
            if "have no shipments assigned" in str(e.detail) and not override_empty_stops:
                raise HTTPException(status_code=409, detail={
                    "code": "EMPTY_STOPS",
                    "message": str(e.detail),
                    "action": "Ask the driver to confirm, then resend with override_empty_stops=true",
                })
            raise

        updated = DeliveryRepository.get_manifest(mid)

        return {
            "message": "Shipment accepted and picked up",
            "manifest_id": mid,
            "shipment_id": se,
            "status": updated["status"],
            "trip": updated["trip"],
            "pickup_datetime": updated["pickup_datetime"],
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "photos": urls,
            "erp": result,
        }

    # ------------------------------------------------------------------
    # Send OTP
    # ------------------------------------------------------------------

    @staticmethod
    def send_delivery_otp(user, any_id, receiver):

        manifest = DeliveryService._owned(user, any_id)
        mid = manifest["manifest_id"]

        if manifest["status"] != "In Transit":
            raise HTTPException(status_code=409, detail=f"Delivery OTP only for 'In Transit' shipments (current: '{manifest['status']}')")

        # `receiver` may be the executive's id or display name from /receivers;
        # an unknown value is sent as free text (store with no roster), like the ERP.
        rows = FrappeClient.call(MANIFEST + "delivery_receivers",
                                 {"manifest": mid, "stock_entry": manifest["stock_entry"]}, as_user=user["sub"]) or []
        match = next((r for r in rows if receiver.strip().lower() in
                      {str(r.get("name", "")).lower(), str(r.get("executive_name", "")).lower()}), None)

        if rows and not match:
            raise HTTPException(status_code=422, detail="Choose a receiver from GET /receivers for this store")

        info = FrappeClient.call(MANIFEST + "request_delivery_otp",
                                 {"manifest": mid, "receiver": match["name"] if match else None},
                                 as_user=user["sub"]) or {}

        sent_to = list(info.get("masked_emails") or []) + list(info.get("masked_mobiles") or [])

        # The ERP reports "sent" as soon as it hands the mail to its queue; check
        # whether the mail really left, so the app can warn the driver.
        queued = DeliveryRepository.otp_email_status(mid)
        if queued is None:
            email_status = "not_queued"
            warning = "ERPNext did not queue the OTP email (its outgoing email account is failing). The receiver can read the OTP in their ERPNext notifications."
        elif queued["status"] == "Sent":
            email_status, warning = "sent", None
        else:
            email_status = queued["status"].lower().replace(" ", "_")
            warning = f"OTP email is '{queued['status']}' in ERPNext: {queued['error'] or 'outgoing email problem'}"

        return {
            "message": (f"OTP sent to {', '.join(sent_to)}" if sent_to else "OTP generated, but no contact was reachable - ask the receiver")
                       + (f". WARNING: {warning}" if warning else ""),
            "manifest_id": mid,
            "receiver": match["executive_name"] if match else receiver,
            "sent_to": sent_to,
            "email_status": email_status,
            "warning": warning,
            "resend_after_seconds": info.get("resend_after_seconds", 120),
        }

    # ------------------------------------------------------------------
    # Confirm & Deliver
    # ------------------------------------------------------------------

    @staticmethod
    def deliver(user, any_id, qr, receiver_name, otp, photos, lat, lng, accuracy, location_note, additional_qrs=None, actual_distance_km=None):

        additional_qrs = _split_qrs(additional_qrs)
        location_note = _clean_note(location_note)

        if actual_distance_km is not None and actual_distance_km < 0:
            raise HTTPException(status_code=422, detail="actual_distance_km cannot be negative")

        manifest = DeliveryService._owned(user, any_id)
        mid, se = manifest["manifest_id"], manifest["stock_entry"]

        if manifest["status"] != "In Transit":
            raise HTTPException(status_code=409, detail=f"Delivery not allowed in status '{manifest['status']}'")

        # Driver must physically be at the destination store (within DELIVERY_GEOFENCE_M)
        geofence = DeliveryService._require_at_store(manifest, lat, lng, accuracy)

        urls = DeliveryService._upload_photos(user, mid, photos, "delivery")

        result = _ensure_ok(FrappeClient.call(MANIFEST + "driver_complete_delivery_row", {
            "manifest": mid,
            "stock_entry": se,
            "delivery_photo": urls[0],
            "delivery_photos": json.dumps(urls),
            "receiver_name": receiver_name.strip(),
            "scanned_qr": qr.strip(),
            "additional_scanned_qrs": json.dumps(additional_qrs or []),
            "otp": otp,
            "lat": lat,
            "lng": lng,
            "gps_accuracy_m": accuracy,
            "no_location_reason": location_note if lat is None or lng is None else None,
            "actual_distance_km": actual_distance_km,     # kept by the ERP only if its signature declares it
        }, as_user=user["sub"]))

        updated = DeliveryRepository.get_manifest(mid)

        if updated["status"] != "Delivered":
            raise HTTPException(status_code=409, detail={"message": f"ERPNext did not mark the shipment delivered (status '{updated['status']}')", "erp": result})

        distance = DeliveryService._record_distance(user, mid, se, updated["trip"], actual_distance_km)

        return {
            "message": "Delivered",
            "manifest_id": mid,
            "shipment_id": se,
            "status": updated["status"],
            "trip": updated["trip"],
            "delivery_datetime": updated["delivery_datetime"],
            "receiver_name": updated["receiver_name"] or receiver_name,
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "geofence": geofence,
            "actual_distance_km": distance,
            "photos": urls,
            "erp": result,
        }

    @staticmethod
    def _record_distance(user, manifest_id, stock_entry, trip, km):
        """Optional odometer reading from the driver: stored on the shipment row
        (CH Transfer Manifest Item.distance_km) and added to the trip's
        total_distance_actual_km. Never fails the delivery."""

        if km is None:
            return None

        try:
            row = DeliveryRepository.get_item_row_name(manifest_id, stock_entry)
            if row:
                FrappeClient.set_value("CH Transfer Manifest Item", row, "distance_km", km)

            if trip:
                current = FrappeClient.call("frappe.client.get_value",
                                            {"doctype": "CH Logistics Trip", "filters": trip,
                                             "fieldname": "total_distance_actual_km"}) or {}
                total = float(current.get("total_distance_actual_km") or 0) + float(km)
                FrappeClient.set_value("CH Logistics Trip", trip, "total_distance_actual_km", round(total, 3))

            return float(km)

        except HTTPException:
            return float(km)      # delivery already succeeded; distance is best-effort
