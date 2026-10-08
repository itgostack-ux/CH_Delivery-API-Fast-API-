import hashlib
import hmac
import secrets
from datetime import datetime

from fastapi import HTTPException

from app.core.config import settings
from app.core.email import EmailService
from app.core.frappe_client import FrappeClient
from ..repositories.delivery_repo import DeliveryRepository
from ..repositories.manifest_repo import ManifestRepository
from .manifest_service import ManifestService

OTP_EXPIRES_MINUTES = 10


def _digest(manifest_id, otp):
    """Same shape ERPNext stores: 'hmac-sha256$<hex>'."""
    mac = hmac.new(settings.JWT_SECRET.encode(), f"{manifest_id}:{otp}".encode(), hashlib.sha256)
    return "hmac-sha256$" + mac.hexdigest()


def _mask_email(email):
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


class DeliveryService:

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _owned(user, any_id):
        """`any_id` may be the manifest id, the shipment id (GFTNMT...) or the
        delivery challan (GFTNDC...), exactly as the ERPNext dialogs show them."""

        manifest_id = ManifestService.resolve(any_id)
        driver_ids = ManifestService._driver_ids_for(user)
        manifest = DeliveryRepository.get_manifest(manifest_id)

        if not manifest or manifest["docstatus"] == 2:
            raise HTTPException(status_code=404, detail="Manifest not found")

        if not manifest["driver"]:
            raise HTTPException(status_code=409, detail=f"Manifest is not assigned to any driver yet (status '{manifest['status']}')")

        if manifest["driver"] not in driver_ids:
            raise HTTPException(status_code=403, detail="This manifest is not assigned to you")

        return manifest

    @staticmethod
    def _check_qr(manifest, qr):
        """The QR on the package carries the shipment id (Stock Entry); also
        accept the manifest id or its QR payload."""

        accepted = {manifest["manifest_id"], manifest["qr_payload"], manifest["tracking_token"]}
        accepted |= {i["stock_entry"] for i in manifest["items"]}
        accepted.discard(None)

        if (qr or "").strip() not in accepted:
            raise HTTPException(status_code=422, detail="Scanned QR does not belong to this manifest")

    @staticmethod
    def _read_photos(uploads):

        photos = [p for p in (ManifestService._read_photo(u, f"Photo {i + 1}") for i, u in enumerate(uploads or [])) if p]

        if not photos:
            raise HTTPException(status_code=422, detail="At least one photo of the goods is required")

        if not (settings.FRAPPE_API_KEY and settings.FRAPPE_API_SECRET):
            raise HTTPException(
                status_code=503,
                detail="Photo upload needs FRAPPE_API_KEY / FRAPPE_API_SECRET in app/.env "
                       "(ERPNext: User > API Access > Generate Keys)"
            )

        return photos

    @staticmethod
    def _upload_photos(manifest_id, photos, stage):
        """Upload to ERPNext; the first photo fills the manifest's <stage>_photo field."""

        urls = []

        for index, (filename, content, content_type) in enumerate(photos, start=1):
            try:
                uploaded = FrappeClient.upload_file(
                    filename=f"{stage}_{manifest_id}_{index}_{filename}",
                    content=content,
                    content_type=content_type,
                    doctype="CH Transfer Manifest",
                    docname=manifest_id,
                    fieldname=f"{stage}_photo" if index == 1 else None,
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Photo {index} upload failed: {e}")

            urls.append(uploaded["file_url"])

        return urls

    # ------------------------------------------------------------------
    # Receivers
    # ------------------------------------------------------------------

    @staticmethod
    def receivers(user, any_id):

        manifest = DeliveryService._owned(user, any_id)
        manifest_id = manifest["manifest_id"]
        rows = DeliveryRepository.get_receivers(manifest["destination_store"])

        return {
            "manifest_id": manifest_id,
            "store": manifest["destination_store"],
            "receivers": [
                {"email": r["email"], "full_name": r["full_name"], "first_name": r["first_name"],
                 "mobile_no": r["mobile_no"], "is_home_store": bool(r["is_home_store"])}
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # Pickup
    # ------------------------------------------------------------------

    @staticmethod
    def pickup(user, any_id, qr, photos, lat, lng, accuracy, location_note):

        manifest = DeliveryService._owned(user, any_id)
        manifest_id = manifest["manifest_id"]

        if manifest["status"] != "Assigned":
            raise HTTPException(status_code=409, detail=f"Pickup not allowed in status '{manifest['status']}'")

        DeliveryService._check_qr(manifest, qr)
        photo_data = DeliveryService._read_photos(photos)
        urls = DeliveryService._upload_photos(manifest_id, photo_data, "pickup")

        result = DeliveryRepository.pickup(manifest, user["sub"], qr.strip(), urls[0], lat, lng, accuracy)

        if not result:
            raise HTTPException(status_code=409, detail="Manifest changed, please refresh")

        updated = DeliveryRepository.get_manifest(manifest_id)

        return {
            "message": "Pickup confirmed, shipment in transit",
            "manifest_id": manifest_id,
            "status": updated["status"],
            "trip": updated["trip"],
            "trip_started": result["trip_started"],
            "pickup_datetime": updated["pickup_datetime"],
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "photos": urls,
        }

    # ------------------------------------------------------------------
    # Delivery OTP
    # ------------------------------------------------------------------

    @staticmethod
    def send_delivery_otp(user, any_id, receiver, ip_address=None):

        manifest = DeliveryService._owned(user, any_id)
        manifest_id = manifest["manifest_id"]

        if manifest["status"] != "In Transit":
            raise HTTPException(status_code=409, detail=f"Delivery OTP only for 'In Transit' manifests (current: '{manifest['status']}')")

        candidates = DeliveryRepository.get_receivers(manifest["destination_store"])
        match = next((r for r in candidates if receiver.strip().lower() in
                      {(r["email"] or "").lower(), (r["full_name"] or "").lower(), (r["first_name"] or "").lower()}), None)

        if not match:
            raise HTTPException(status_code=422, detail=f"Receiver must be a user of store {manifest['destination_store']} (see /receivers)")

        otp = f"{secrets.randbelow(10**6):06d}"
        masked = _mask_email(match["email"])

        log_name = DeliveryRepository.create_delivery_otp(
            manifest, user["sub"], _digest(manifest_id, otp), OTP_EXPIRES_MINUTES, masked, ip_address
        )

        stock_entries = ", ".join(i["stock_entry"] for i in manifest["items"] if i["stock_entry"])

        try:
            EmailService.send_mail(
                to=match["email"],
                subject=f"Delivery OTP for {manifest_id}",
                html=f"""
                <html><body style="font-family:Arial;padding:20px;">
                  <h2 style="margin-top:0;">Delivery OTP</h2>
                  <p>Hi {match['full_name'] or match['email']},</p>
                  <p>Driver <b>{manifest['driver_name'] or manifest['driver']}</b> is delivering
                     <b>{manifest_id}</b> ({stock_entries}) to <b>{manifest['destination_store']}</b>.</p>
                  <p>Share this OTP with the driver only after checking the goods:</p>
                  <p style="font-size:32px;letter-spacing:8px;font-weight:bold;">{otp}</p>
                  <p style="color:#777;font-size:12px;">Valid for {OTP_EXPIRES_MINUTES} minutes.</p>
                </body></html>
                """,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OTP saved but email failed: {e}")

        return {
            "message": f"OTP sent to {masked}",
            "manifest_id": manifest_id,
            "receiver": match["full_name"] or match["email"],
            "sent_to": masked,
            "otp_log": log_name,
            "expires_in_seconds": OTP_EXPIRES_MINUTES * 60,
        }

    # ------------------------------------------------------------------
    # Deliver
    # ------------------------------------------------------------------

    @staticmethod
    def deliver(user, any_id, qr, receiver_name, otp, photos, lat, lng, accuracy, location_note):

        manifest = DeliveryService._owned(user, any_id)
        manifest_id = manifest["manifest_id"]

        if manifest["status"] != "In Transit":
            raise HTTPException(status_code=409, detail=f"Delivery not allowed in status '{manifest['status']}'")

        DeliveryService._check_qr(manifest, qr)

        # OTP check (before photos are uploaded, so a wrong OTP costs nothing)
        log = DeliveryRepository.get_otp_log(manifest["delivery_otp_log"]) if manifest["delivery_otp_log"] else None

        if not log or log["status"] != "Pending":
            raise HTTPException(status_code=400, detail="No active delivery OTP. Send a new one")

        if datetime.now() > log["expires_at"]:
            raise HTTPException(status_code=400, detail="Delivery OTP has expired. Send a new one")

        if log["attempts"] >= log["max_attempts"]:
            raise HTTPException(status_code=400, detail="Too many wrong OTP attempts. Send a new one")

        if not hmac.compare_digest(log["otp_digest"], _digest(manifest_id, otp)):
            DeliveryRepository.record_otp_attempt(log["name"], manifest_id, user["sub"], False, "Wrong OTP")
            raise HTTPException(status_code=401, detail="Invalid delivery OTP")

        photo_data = DeliveryService._read_photos(photos)
        urls = DeliveryService._upload_photos(manifest_id, photo_data, "delivery")

        DeliveryRepository.record_otp_attempt(log["name"], manifest_id, user["sub"], True)

        result = DeliveryRepository.deliver(manifest, user["sub"], qr.strip(), urls[0], receiver_name.strip(), lat, lng, accuracy)

        if not result:
            raise HTTPException(status_code=409, detail="Manifest changed, please refresh")

        updated = DeliveryRepository.get_manifest(manifest_id)

        return {
            "message": "Delivered",
            "manifest_id": manifest_id,
            "status": updated["status"],
            "trip": updated["trip"],
            "trip_closed": result["trip_closed"],
            "delivery_datetime": updated["delivery_datetime"],
            "receiver_name": updated["receiver_name"],
            "location": {"latitude": lat, "longitude": lng, "accuracy_m": accuracy, "note": location_note},
            "photos": urls,
        }
