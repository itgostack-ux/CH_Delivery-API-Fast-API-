from fastapi import HTTPException

from app.core.frappe_client import FrappeClient
from ..repositories.manifest_repo import ManifestRepository

# Rules copied from the ERP (ch_logistics CH Transfer Manifest.reject_manifest)
REJECTABLE_STATUSES = ("Assigned", "Pickup Started", "In Transit")
PICKUP_REASONS = ["Material Not Ready", "Wrong Package", "Store Closed", "Damaged Package", "Other"]
IN_TRANSIT_REASONS = ["Customer Not Available", "Address Not Found", "Receiver Refused", "Damaged in Transit", "Vehicle Breakdown", "Other"]

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024


class ManifestService:

    @staticmethod
    def _driver_ids_for(user):

        driver_ids = ManifestRepository.get_driver_ids_for_user(user["sub"])

        if not driver_ids:
            raise HTTPException(
                status_code=403,
                detail="No Driver record is linked to this user"
            )

        return driver_ids

    @staticmethod
    def resolve(any_id):
        """Manifest id, shipment id (GFTNMT...) or delivery challan (GFTNDC...) -> manifest id."""

        manifest_id = ManifestRepository.resolve_manifest_id(any_id.strip())

        if not manifest_id:
            raise HTTPException(status_code=404, detail="Manifest / shipment not found")

        return manifest_id

    @staticmethod
    def _owned_manifest(manifest_id, driver_ids):
        """Manifest must exist and be assigned to one of the user's Driver records."""

        manifest = ManifestRepository.get_manifest(manifest_id)

        if not manifest or manifest["docstatus"] == 2:
            raise HTTPException(status_code=404, detail="Manifest not found")

        if not manifest["driver"]:
            raise HTTPException(
                status_code=409,
                detail=f"Manifest is not assigned to any driver yet (status '{manifest['status']}')"
            )

        if manifest["driver"] not in driver_ids:
            raise HTTPException(
                status_code=403,
                detail="This manifest is not assigned to you"
            )

        return manifest

    @staticmethod
    def _shipments(user, statuses, days=None):

        driver_ids = ManifestService._driver_ids_for(user)
        rows = ManifestRepository.get_shipments_for_drivers(driver_ids, statuses, days)

        for row in rows:
            labels = [x for x in (row.pop("box_labels", None) or "").split(",") if x]
            row["box_labels"] = labels
            row["qr"] = labels[0] if labels else None

        return {"count": len(rows), "data": rows}

    @staticmethod
    def pending(user):
        """Pickup Pending tab (ERP driver app)."""
        return ManifestService._shipments(user, ("Assigned",))

    @staticmethod
    def delivery_pending(user):
        """Delivery Pending tab: picked up, on the vehicle, not yet delivered."""
        return ManifestService._shipments(user, ("In Transit", "Pickup Started"))

    @staticmethod
    def delivered(user, days=30):
        """Delivered tab: history of completed deliveries."""
        return ManifestService._shipments(user, ("Delivered", "Partially Received", "Received", "Closed"), days)

    @staticmethod
    def reject_reasons():
        """All reasons plus the stage-specific lists the ERP enforces."""

        try:
            reasons = ManifestRepository.get_reject_reasons()
        except Exception:
            reasons = []

        return {
            "reasons": reasons or sorted(set(PICKUP_REASONS) | set(IN_TRANSIT_REASONS)),
            "pickup_reasons": PICKUP_REASONS,
            "in_transit_reasons": IN_TRANSIT_REASONS,
        }

    @staticmethod
    def _read_photo(upload, label):
        """Validate an optional uploaded image; returns (filename, bytes, type) or None."""

        if upload is None or not upload.filename:
            return None

        if upload.content_type not in ALLOWED_PHOTO_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"{label} must be a JPEG, PNG or WEBP image"
            )

        content = upload.file.read()

        if not content:
            raise HTTPException(status_code=422, detail=f"{label} is empty")

        if len(content) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail=f"{label} exceeds 10 MB")

        return upload.filename, content, upload.content_type

    @staticmethod
    def reject(user, any_id, reason, notes, photo1, photo2, latitude=None, longitude=None):
        """Reject Pickup / Failed Delivery - delegated to the ERP's own
        transfer_manifest_api.reject_manifest (whole manifest) or
        reject_manifest_leg (one shipment of a multi-leg manifest), which creates
        the CH Manifest Rejection (Pending Review), reverses the stock to source,
        notifies the dispatcher and feeds the Rejected tab.

        The ERP's rules are checked here first so the driver gets a clear
        answer before any photo is uploaded:
          * status must be Assigned / Pickup Started / In Transit
          * reason must match the stage (pickup vs in-transit list)
          * both proof photos required, and different from each other
        """

        manifest_id = ManifestService.resolve(any_id)
        driver_ids = ManifestService._driver_ids_for(user)
        manifest = ManifestService._owned_manifest(manifest_id, driver_ids)

        if manifest["status"] not in REJECTABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Only an active pickup or in-transit delivery can be rejected (status '{manifest['status']}')")

        stage = "In Transit" if manifest["status"] == "In Transit" else "Pickup"
        valid = IN_TRANSIT_REASONS if stage == "In Transit" else PICKUP_REASONS

        if reason not in valid:
            raise HTTPException(status_code=422, detail=f"'{reason}' is not a valid {stage.lower()} rejection reason. Allowed: {', '.join(valid)}")

        photos = [ManifestService._read_photo(photo1, "Proof Photo 1"), ManifestService._read_photo(photo2, "Proof Photo 2")]

        if not all(photos):
            raise HTTPException(status_code=422, detail="Both proof photos are required (FR-024, FR-025).")

        if photos[0][1] == photos[1][1]:
            raise HTTPException(status_code=422, detail="The two proof photos must be different.")

        urls = []

        for index, (filename, content, content_type) in enumerate(photos, start=1):
            uploaded = FrappeClient.upload_file(
                filename=f"reject_{manifest_id}_{index}_{filename}",
                content=content, content_type=content_type,
                doctype="CH Transfer Manifest", docname=manifest_id,
                as_user=user["sub"],
            )
            urls.append(uploaded["file_url"])

        legs = ManifestRepository.get_stock_entries(manifest_id)
        wanted = any_id.strip()
        leg = wanted if wanted in legs else None      # a shipment id rejects just that leg

        # Both parameter spellings are sent: Frappe keeps only the ones the
        # deployed signature declares (proof_image_1/2 + remarks + lat/lng in
        # the current source; rejection_photo/_2 + rejection_notes in older builds).
        args = {
            "manifest": manifest_id,
            "rejection_reason": reason,
            "proof_image_1": urls[0],
            "proof_image_2": urls[1],
            "rejection_photo": urls[0],
            "rejection_photo_2": urls[1],
            "remarks": notes,
            "rejection_notes": notes,
            "latitude": latitude,
            "longitude": longitude,
        }
        if leg:
            args["stock_entry"] = leg

        result = FrappeClient.call(
            "ch_logistics.api.transfer_manifest_api." + ("reject_manifest_leg" if leg else "reject_manifest"),
            args, as_user=user["sub"],
        )

        if isinstance(result, dict) and result.get("ok") is False:
            raise HTTPException(status_code=400, detail={"message": result.get("message") or "ERPNext refused the rejection", "erp": result})

        # a leg rejection splits the shipment into its own manifest; report that one
        rejected_manifest = result.get("manifest") if isinstance(result, dict) else None
        updated = ManifestRepository.get_manifest(rejected_manifest or manifest_id)

        if not updated or updated["status"] != "Rejected":
            raise HTTPException(status_code=409, detail={"message": "ERPNext did not mark the manifest rejected (status %s)" % ((updated or {}).get("status")), "erp": result})

        return {
            "message": "Shipment rejected. Dispatcher notified." if stage == "Pickup"
                       else "Failed delivery logged. Dispatch notified; goods will be returned to source.",
            "manifest_id": updated["manifest_id"],
            "status": updated["status"],
            "trip": updated["trip"],
            "rejected_at": updated["rejected_at"],
            "rejection_reason": updated["rejection_reason"],
            "rejected_during": stage,
            "rejection_photos": urls,
            "erp": result,
        }
