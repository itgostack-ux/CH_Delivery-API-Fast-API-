"""Pickup & delivery, delegated to the ERP's own driver-app methods.

Mirrors ch_logistics @ logistics-testing (259b8b8). The ERPNext "Delivery
App" page calls these whitelisted methods; the API calls exactly the same
ones, as the same driver user, so behaviour is identical:

    logistics_api.driver_accept_manifest_row            Accept Shipment (= pickup of ONE leg)
    transfer_manifest_api.delivery_receivers            Receiver list
    transfer_manifest_api.request_delivery_otp          Send OTP (per leg, or one code per store)
    transfer_manifest_api.driver_complete_delivery_row  Deliver ONE leg
    transfer_manifest_api.driver_complete_store_delivery Deliver every picked-up order at a store with one OTP

Everything is per shipment leg: a leg can be delivered while its manifest is
still "Assigned" because a sibling leg has not been accepted yet. The ERP
validates box-label scans strictly (shipment numbers are refused), checks its
own geofence (CH Logistics Settings: enforce_geofence / geofence_radius_m,
accuracy-widened, overridable with geofence_override_reason) and refuses
action while the driver is on break.
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


# ERP error texts (ch_transfer_manifest.py / transfer_manifest_api.py) -> codes the app can act on
_ERP_ERROR_CODES = (
    ("Location Too Imprecise", 409, "GPS_IMPRECISE"),
    ("too imprecise", 409, "GPS_IMPRECISE"),
    ("needs dispatch to override", 409, "GEOFENCE_DISPATCH_ONLY"),
    ("must be within", 409, "GEOFENCE_OUT_OF_RANGE"),
    ("Wrong Location", 409, "GEOFENCE_OUT_OF_RANGE"),
    ("Location Required", 422, "LOCATION_REQUIRED"),
    ("latitude & longitude) is mandatory", 422, "LOCATION_REQUIRED"),
    ("GPS returned 0, 0", 422, "LOCATION_REQUIRED"),
    ("Scan the box label", 422, "SCAN_REQUIRED"),
    ("is not a box of", 422, "SCAN_REQUIRED"),
    ("No scanned label matches", 422, "SCAN_REQUIRED"),
    ("Scan Required", 422, "SCAN_REQUIRED"),
    ("Label Out Of Date", 409, "LABEL_OUT_OF_DATE"),
    ("An OTP was just sent", 429, "OTP_WAIT"),
    ("Please Wait", 429, "OTP_WAIT"),
    ("on Break", 409, "ON_BREAK"),
    ("already accepted", 409, "ALREADY_ACCEPTED"),
    ("already delivered", 409, "ALREADY_DELIVERED"),
    ("must be picked up (accepted) before", 409, "NOT_PICKED_UP"),
    ("Accept this shipment before", 409, "NOT_PICKED_UP"),
    ("being updated by another user", 409, "LOCKED"),
)


def _erp_error(exc):
    """Re-raise an ERP HTTPException with a stable `code` the app can switch on."""

    text = str(exc.detail)
    for needle, status, code in _ERP_ERROR_CODES:
        if needle.lower() in text.lower():
            raise HTTPException(status_code=status, detail={"code": code, "message": text})
    raise exc


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
    def _leg(manifest, stock_entry=None):
        """The CH Transfer Manifest Item row of the addressed shipment."""

        se = stock_entry or manifest["stock_entry"]
        return next((i for i in manifest["items"] if i["stock_entry"] == se), None)

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

        # Which shipment (leg) was addressed: the path id may be the stock
        # entry (GFTNMT...), its challan (GFTNDC...) or a box label; a plain
        # manifest id leaves it open, and the caller then picks the leg from
        # the scanned box label (see _select_leg).
        legs = [i["stock_entry"] for i in manifest["items"] if i["stock_entry"]]
        lookup = DeliveryRepository.leg_lookup(manifest_id) if legs else {}
        wanted = lookup.get(any_id.strip().lower())
        manifest["stock_entry"] = wanted or (legs[0] if legs else None)
        manifest["leg_explicit"] = wanted is not None
        manifest["legs"] = legs
        manifest["leg_lookup"] = lookup

        return manifest

    @staticmethod
    def _select_leg(manifest, scans=None, want=None):
        """Pin manifest["stock_entry"] to the right leg when the path id was
        only the manifest.

        scans: box labels the driver scanned -> the leg they belong to (any
               label of another shipment is refused, like the ERP's strict
               box scan).
        want:  a predicate on the leg row, used when there is nothing to
               scan (OTP): e.g. "accepted and not yet delivered"."""

        if manifest.get("leg_explicit") or len(manifest.get("legs") or []) <= 1:
            return manifest["stock_entry"]

        lookup = manifest.get("leg_lookup") or {}

        if scans:
            found = {lookup.get(str(s).strip().lower()) for s in scans if str(s).strip()}
            found.discard(None)
            unknown = [s for s in scans if str(s).strip() and str(s).strip().lower() not in lookup]
            if unknown or len(found) != 1:
                raise HTTPException(status_code=422, detail={
                    "code": "SCAN_REQUIRED",
                    "message": (f"{', '.join(unknown)} is not a box of manifest {manifest['manifest_id']}" if unknown
                                else "Scanned labels belong to different shipments; send one shipment per call, or use the shipment id in the URL"),
                    "shipments": {i["stock_entry"]: [c for c, se in lookup.items() if se == i["stock_entry"] and "-b" in c] for i in manifest["items"]},
                })
            manifest["stock_entry"] = found.pop()
            return manifest["stock_entry"]

        if want:
            for item in manifest["items"]:
                if want(item):
                    manifest["stock_entry"] = item["stock_entry"]
                    return manifest["stock_entry"]

        return manifest["stock_entry"]

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
        leg = DeliveryService._leg(manifest) or {}
        # Same resolution order as the ERP: the leg's own to_warehouse first.
        store = DeliveryRepository.get_store_location(
            manifest["destination_store"], leg.get("to_warehouse") or manifest.get("destination_warehouse")) or {}
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
    def pickup(user, any_id, qr, photos, lat, lng, accuracy, location_note, additional_qrs=None,
               override_empty_stops=False, geofence_override_reason=None):

        additional_qrs = _split_qrs(additional_qrs)
        location_note = _clean_note(location_note)
        geofence_override_reason = _clean_note(geofence_override_reason)

        manifest = DeliveryService._owned(user, any_id)
        DeliveryService._select_leg(manifest, [qr] + list(additional_qrs or []))
        mid, se = manifest["manifest_id"], manifest["stock_entry"]
        leg = DeliveryService._leg(manifest) or {}

        if manifest["status"] != "Assigned":
            raise HTTPException(status_code=409, detail=f"Pickup not allowed in status '{manifest['status']}'")

        if leg.get("driver_accepted_at"):
            raise HTTPException(status_code=409, detail={"code": "ALREADY_ACCEPTED", "message": f"Shipment {se} is already accepted (picked up)"})

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
            "geofence_override_reason": geofence_override_reason,
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
            _erp_error(e)

        updated = DeliveryRepository.get_manifest(mid)
        updated_leg = DeliveryService._leg(updated, se) or {}

        return {
            "message": ("Shipment accepted and picked up; manifest now In Transit"
                        if updated["status"] == "In Transit" else
                        "Shipment accepted and picked up; other shipments of this manifest still await acceptance"),
            "manifest_id": mid,
            "shipment_id": se,
            "status": updated["status"],
            "leg_accepted_at": updated_leg.get("driver_accepted_at"),
            "manifest_fully_accepted": bool((result or {}).get("manifest_fully_accepted")) if isinstance(result, dict) else None,
            "trip": updated["trip"],
            "pickup_datetime": updated["pickup_datetime"],
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "photos": urls,
            "erp": result,
        }

    # ------------------------------------------------------------------
    # Accept & Pick Up every shipment of the manifest in one go
    # ------------------------------------------------------------------

    @staticmethod
    def pickup_all(user, any_id, qrs, photos, lat, lng, accuracy, location_note,
                   override_empty_stops=False, geofence_override_reason=None):
        """Scan all the boxes on the trolley, one photo, one GPS fix: every
        shipment of the manifest whose boxes were scanned is accepted.

        The ERP accepts one shipment per call (driver_accept_manifest_row) and
        insists that EVERY box of a shipment is scanned, so the labels are
        grouped per shipment here and sent one shipment at a time; the photo
        is uploaded once and reused. Each shipment gets its own verdict so a
        single bad scan does not hide the others."""

        scans = _split_qrs(qrs)
        location_note = _clean_note(location_note)
        geofence_override_reason = _clean_note(geofence_override_reason)

        if not scans:
            raise HTTPException(status_code=422, detail={"code": "SCAN_REQUIRED", "message": "Scan the box labels (qrs, comma-separated)"})

        manifest = DeliveryService._owned(user, any_id)
        mid = manifest["manifest_id"]

        if manifest["status"] != "Assigned":
            raise HTTPException(status_code=409, detail=f"Pickup not allowed in status '{manifest['status']}'")
        if not manifest["trip"]:
            raise HTTPException(status_code=409, detail="Manifest is not attached to a trip yet")

        lookup = manifest.get("leg_lookup") or {}
        unknown = [s for s in scans if s.lower() not in lookup]
        if unknown:
            raise HTTPException(status_code=422, detail={
                "code": "SCAN_REQUIRED",
                "message": f"{', '.join(unknown)} is not a box of manifest {mid}",
                "box_labels": {i["stock_entry"]: sorted(c for c, se in lookup.items() if se == i["stock_entry"] and "-b" in c)
                               for i in manifest["items"]},
            })

        # labels per shipment, in scan order
        per_leg = {}
        for s in scans:
            per_leg.setdefault(lookup[s.lower()], []).append(s)

        urls = DeliveryService._upload_photos(user, mid, photos, "pickup")

        results, accepted, trip_started = [], [], False
        for item in manifest["items"]:
            se = item["stock_entry"]
            labels = per_leg.get(se)
            if not labels:
                results.append({"shipment_id": se, "status": "not_scanned", "message": "No box of this shipment was scanned"})
                continue
            if item.get("driver_accepted_at"):
                results.append({"shipment_id": se, "status": "already_accepted", "message": "Accepted earlier", "accepted_at": item["driver_accepted_at"]})
                continue

            args = {
                "trip": manifest["trip"],
                "manifest": mid,
                "stock_entry": se,
                "pickup_photo": urls[0],
                "pickup_photos": json.dumps(urls),
                "scanned_qr": labels[0],
                "additional_scanned_qrs": json.dumps(labels[1:]),
                "lat": lat,
                "lng": lng,
                "gps_accuracy_m": accuracy,
                "no_location_reason": location_note if lat is None or lng is None else None,
                "geofence_override_reason": geofence_override_reason,
                "override_empty_stops": 1 if (override_empty_stops or trip_started) else 0,
            }
            try:
                erp = _ensure_ok(FrappeClient.call(LOGISTICS + "driver_accept_manifest_row", args, as_user=user["sub"]))
                trip_started = trip_started or bool((erp or {}).get("trip_started")) if isinstance(erp, dict) else trip_started
                accepted.append(se)
                results.append({"shipment_id": se, "status": "accepted", "scanned": labels, "erp": erp})
            except HTTPException as e:
                detail = e.detail
                if "have no shipments assigned" in str(detail) and not override_empty_stops:
                    raise HTTPException(status_code=409, detail={
                        "code": "EMPTY_STOPS",
                        "message": str(detail),
                        "action": "Ask the driver to confirm, then resend with override_empty_stops=true",
                        "results": results,
                    })
                try:
                    _erp_error(e)
                except HTTPException as mapped:
                    detail = mapped.detail
                results.append({"shipment_id": se, "status": "failed", "scanned": labels,
                                "code": detail.get("code") if isinstance(detail, dict) else None,
                                "message": detail.get("message") if isinstance(detail, dict) else str(detail)})

        updated = DeliveryRepository.get_manifest(mid)
        failed = [r for r in results if r["status"] == "failed"]

        if not accepted and failed:
            raise HTTPException(status_code=409, detail={
                "code": failed[0].get("code") or "PICKUP_FAILED",
                "message": failed[0]["message"],
                "results": results,
            })

        remaining = [i["stock_entry"] for i in updated["items"] if not i.get("driver_accepted_at")]

        return {
            "message": (f"Accepted {len(accepted)} shipment(s); manifest now In Transit" if updated["status"] == "In Transit"
                        else f"Accepted {len(accepted)} shipment(s); {len(remaining)} still waiting for pickup"),
            "manifest_id": mid,
            "status": updated["status"],
            "trip": updated["trip"],
            "accepted": accepted,
            "remaining": remaining,
            "manifest_fully_accepted": updated["status"] == "In Transit",
            "pickup_datetime": updated["pickup_datetime"],
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "photos": urls,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Send OTP
    # ------------------------------------------------------------------

    @staticmethod
    def send_delivery_otp(user, any_id, receiver, stock_entries=None):

        manifest = DeliveryService._owned(user, any_id)
        stock_entries = _split_qrs(stock_entries)
        # No scan at this step: with only a manifest id, take the first leg
        # that is on the vehicle and not yet delivered (or the first ticked one).
        DeliveryService._select_leg(
            manifest, scans=stock_entries[:1] if stock_entries else None,
            want=lambda i: i.get("driver_accepted_at") and not i.get("delivery_captured_at"))
        mid = manifest["manifest_id"]
        leg = DeliveryService._leg(manifest) or {}

        # Per leg, like the ERP: the shipment must be on the vehicle (accepted)
        # and not yet delivered; the manifest may still be "Assigned".
        if manifest["status"] not in ("Assigned", "In Transit"):
            raise HTTPException(status_code=409, detail=f"Delivery OTP only for picked-up shipments (manifest status '{manifest['status']}')")
        if manifest["status"] == "Assigned" and not leg.get("driver_accepted_at"):
            raise HTTPException(status_code=409, detail={"code": "NOT_PICKED_UP", "message": "Accept (pick up) this shipment before asking for its delivery OTP"})
        if leg.get("delivery_captured_at"):
            raise HTTPException(status_code=409, detail={"code": "ALREADY_DELIVERED", "message": "This shipment is already delivered"})

        # `receiver` may be the executive's id or display name from /receivers;
        # an unknown value is sent as free text (store with no roster), like the ERP.
        rows = FrappeClient.call(MANIFEST + "delivery_receivers",
                                 {"manifest": mid, "stock_entry": manifest["stock_entry"]}, as_user=user["sub"]) or []
        match = next((r for r in rows if receiver.strip().lower() in
                      {str(r.get("name", "")).lower(), str(r.get("executive_name", "")).lower()}), None)

        if rows and not match:
            raise HTTPException(status_code=422, detail="Choose a receiver from GET /receivers for this store")

        otp_args = {"manifest": mid, "receiver": match["name"] if match else None, "stock_entry": manifest["stock_entry"]}
        if len(stock_entries) > 1:
            # One code for every ticked order going to the same store (ERP _same_store_group)
            otp_args["stock_entries"] = json.dumps(stock_entries)

        try:
            info = FrappeClient.call(MANIFEST + "request_delivery_otp", otp_args, as_user=user["sub"]) or {}
        except HTTPException as e:
            _erp_error(e)

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
            "covers_stock_entries": stock_entries if len(stock_entries) > 1 else [manifest["stock_entry"]],
            "resend_after_seconds": info.get("resend_after_seconds", 120),
        }

    # ------------------------------------------------------------------
    # Confirm & Deliver
    # ------------------------------------------------------------------

    @staticmethod
    def _deliverable(manifest):
        """ERP rule (driver_complete_delivery_row): manifest Assigned or In
        Transit, this leg accepted and not yet delivered."""

        leg = DeliveryService._leg(manifest) or {}
        se = manifest["stock_entry"]

        if manifest["status"] not in ("Assigned", "In Transit"):
            raise HTTPException(status_code=409, detail=f"Delivery not allowed in manifest status '{manifest['status']}'")
        if leg.get("delivery_captured_at"):
            raise HTTPException(status_code=409, detail={"code": "ALREADY_DELIVERED", "message": f"Shipment {se} is already delivered"})
        if not leg.get("driver_accepted_at") and manifest["status"] != "In Transit":
            raise HTTPException(status_code=409, detail={"code": "NOT_PICKED_UP", "message": f"Shipment {se} must be accepted (picked up) before it can be delivered"})
        return leg

    @staticmethod
    def deliver(user, any_id, qr, receiver_name, otp, photos, lat, lng, accuracy, location_note, additional_qrs=None,
                actual_distance_km=None, geofence_override_reason=None):

        additional_qrs = _split_qrs(additional_qrs)
        location_note = _clean_note(location_note)
        geofence_override_reason = _clean_note(geofence_override_reason)

        if actual_distance_km is not None and actual_distance_km < 0:
            raise HTTPException(status_code=422, detail="actual_distance_km cannot be negative")

        manifest = DeliveryService._owned(user, any_id)
        DeliveryService._select_leg(manifest, [qr] + list(additional_qrs or []))
        mid, se = manifest["manifest_id"], manifest["stock_entry"]
        DeliveryService._deliverable(manifest)

        # Driver must physically be at the drop point (within DELIVERY_GEOFENCE_M).
        # The ERP re-checks with its own fence (geofence_radius_m, accuracy-widened);
        # a geofence_override_reason skips both, and the ERP records it on the manifest.
        if geofence_override_reason:
            geofence = DeliveryService._geofence(manifest, lat, lng, accuracy)
            geofence["note"] = f"Geofence overridden: {geofence_override_reason}"
        else:
            geofence = DeliveryService._require_at_store(manifest, lat, lng, accuracy)

        urls = DeliveryService._upload_photos(user, mid, photos, "delivery")

        try:
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
                "geofence_override_reason": geofence_override_reason,
            }, as_user=user["sub"]))
        except HTTPException as e:
            _erp_error(e)

        updated = DeliveryRepository.get_manifest(mid)
        updated_leg = DeliveryService._leg(updated, se) or {}

        if not updated_leg.get("delivery_captured_at"):
            raise HTTPException(status_code=409, detail={"message": f"ERPNext did not record the delivery of {se} (manifest status '{updated['status']}')", "erp": result})

        distance = DeliveryService._record_distance(user, mid, se, updated["trip"], actual_distance_km)
        fully = updated["status"] == "Delivered"

        return {
            "message": "Delivered" if fully else "Shipment delivered; other shipments of this manifest are still open",
            "manifest_id": mid,
            "shipment_id": se,
            "status": updated["status"],
            "leg_delivered_at": updated_leg.get("delivery_captured_at"),
            "manifest_fully_delivered": fully,
            "trip": updated["trip"],
            "delivery_datetime": updated["delivery_datetime"],
            "receiver_name": updated["receiver_name"] or receiver_name,
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "geofence": geofence,
            "actual_distance_km": distance,
            "photos": urls,
            "erp": result,
        }

    # ------------------------------------------------------------------
    # Deliver every picked-up order at one store with a single OTP
    # (ERP driver page "Drop" flow -> driver_complete_store_delivery)
    # ------------------------------------------------------------------

    @staticmethod
    def deliver_store(user, any_id, qrs, receiver_name, otp, photos, lat, lng, accuracy, location_note,
                      stock_entries=None, geofence_override_reason=None):

        scans = _split_qrs(qrs)
        stock_entries = _split_qrs(stock_entries)
        location_note = _clean_note(location_note)
        geofence_override_reason = _clean_note(geofence_override_reason)

        if not scans:
            raise HTTPException(status_code=422, detail={"code": "SCAN_REQUIRED", "message": "Scan the box label of every order being dropped (qrs, comma-separated)"})

        manifest = DeliveryService._owned(user, any_id)
        # The lead leg is any scanned box of THIS manifest (the ERP groups the
        # rest of the store's orders itself); other manifests' labels are fine here.
        own = [s for s in scans if str(s).strip().lower() in (manifest.get("leg_lookup") or {})]
        DeliveryService._select_leg(manifest, own[:1] if own else None,
                                    want=lambda i: i.get("driver_accepted_at") and not i.get("delivery_captured_at"))
        mid, se = manifest["manifest_id"], manifest["stock_entry"]
        DeliveryService._deliverable(manifest)

        if geofence_override_reason:
            geofence = DeliveryService._geofence(manifest, lat, lng, accuracy)
            geofence["note"] = f"Geofence overridden: {geofence_override_reason}"
        else:
            geofence = DeliveryService._require_at_store(manifest, lat, lng, accuracy)

        urls = DeliveryService._upload_photos(user, mid, photos, "delivery")

        args = {
            "manifest": mid,
            "stock_entry": se,
            "receiver_name": receiver_name.strip(),
            "otp": otp,
            "scanned_qrs": json.dumps(scans),
            "delivery_photo": urls[0],
            "delivery_photos": json.dumps(urls),
            "lat": lat,
            "lng": lng,
            "gps_accuracy_m": accuracy,
            "no_location_reason": location_note if lat is None or lng is None else None,
            "geofence_override_reason": geofence_override_reason,
        }
        if stock_entries:
            args["stock_entries"] = json.dumps(stock_entries)

        try:
            result = _ensure_ok(FrappeClient.call(MANIFEST + "driver_complete_store_delivery", args, as_user=user["sub"]))
        except HTTPException as e:
            _erp_error(e)

        delivered = list((result or {}).get("delivered") or []) if isinstance(result, dict) else []
        manifests = list((result or {}).get("manifests") or [mid]) if isinstance(result, dict) else [mid]
        statuses = {m: (DeliveryRepository.get_manifest(m) or {}).get("status") for m in manifests}

        return {
            "message": f"Delivered {len(delivered)} order(s) at {manifest['destination_store'] or 'the store'}",
            "manifest_id": mid,
            "shipment_id": se,
            "delivered": delivered,
            "manifests": statuses,
            "receiver_name": receiver_name,
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "geofence": geofence,
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
