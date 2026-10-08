from fastapi import HTTPException

from app.core.frappe_client import FrappeClient
from ..repositories.manifest_repo import ManifestRepository

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
    def pending(user):

        driver_ids = ManifestService._driver_ids_for(user)
        rows = ManifestRepository.get_pending_for_drivers(driver_ids)

        return {"count": len(rows), "data": rows}

    @staticmethod
    def reject_reasons():

        return {"reasons": ManifestRepository.get_reject_reasons()}

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
    def reject(user, any_id, reason, notes, photo1, photo2):

        manifest_id = ManifestService.resolve(any_id)
        driver_ids = ManifestService._driver_ids_for(user)
        manifest = ManifestService._owned_manifest(manifest_id, driver_ids)

        # Photos are optional; validate any that were sent before writing anything
        photos = [
            p for p in (
                ManifestService._read_photo(photo1, "Proof Photo 1"),
                ManifestService._read_photo(photo2, "Proof Photo 2"),
            ) if p
        ]

        if manifest["status"] == "Rejected":
            raise HTTPException(status_code=409, detail="Manifest already rejected")

        if manifest["status"] != "Assigned":
            raise HTTPException(
                status_code=409,
                detail=f"Manifest cannot be rejected in status '{manifest['status']}'"
            )

        reasons = ManifestRepository.get_reject_reasons()

        if reasons and reason not in reasons:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid reason. Allowed: {', '.join(reasons)}"
            )

        if reason == "Other" and not (notes and notes.strip()):
            raise HTTPException(
                status_code=422,
                detail="notes are required when reason is 'Other'"
            )

        # Upload any proof photos to ERPNext as attachments of the manifest.
        # The first also fills the "Rejection Proof Photo" field; the second is
        # a plain attachment visible in the ERPNext sidebar.
        photo_urls = []

        for index, (filename, content, content_type) in enumerate(photos, start=1):

            try:
                uploaded = FrappeClient.upload_file(
                    filename=f"reject_{manifest_id}_{index}_{filename}",
                    content=content,
                    content_type=content_type,
                    doctype="CH Transfer Manifest",
                    docname=manifest_id,
                    fieldname="rejection_photo" if index == 1 else None,
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Photo {index} upload failed: {e}")

            photo_urls.append(uploaded["file_url"])

        first_photo = photo_urls[0] if photo_urls else None

        if not ManifestRepository.reject(manifest_id, user["sub"], reason, notes, first_photo):
            raise HTTPException(status_code=409, detail="Manifest changed, please refresh")

        updated = ManifestRepository.get_manifest(manifest_id)

        return {
            "message": "Manifest rejected",
            "manifest_id": manifest_id,
            "status": updated["status"],
            "trip": updated["trip"],
            "rejected_at": updated["rejected_at"],
            "rejection_reason": updated["rejection_reason"],
            "rejection_photos": photo_urls,
        }
