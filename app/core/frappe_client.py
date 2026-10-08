import requests

from app.core.config import settings


class FrappeClient:
    """Thin wrapper over the ERPNext/Frappe REST API (port 80 on the site).

    Used for things that must go through Frappe itself rather than raw SQL,
    such as file uploads, so the result shows up in ERPNext exactly as if a
    user had attached it there.
    """

    @staticmethod
    def _headers():

        if not (settings.FRAPPE_API_KEY and settings.FRAPPE_API_SECRET):
            raise RuntimeError(
                "FRAPPE_API_KEY / FRAPPE_API_SECRET are not set in app/.env "
                "(generate them in ERPNext: User > API Access > Generate Keys)"
            )

        return {
            "Authorization": f"token {settings.FRAPPE_API_KEY}:{settings.FRAPPE_API_SECRET}"
        }

    @staticmethod
    def upload_file(
        filename: str,
        content: bytes,
        content_type: str,
        doctype: str,
        docname: str,
        fieldname: str | None = None,
        is_private: bool = True,
    ) -> dict:
        """Attach a file to a document. Returns Frappe's File doc (has file_url)."""

        data = {
            "doctype": doctype,
            "docname": docname,
            "is_private": "1" if is_private else "0",
            "folder": "Home",
        }

        if fieldname:
            data["fieldname"] = fieldname

        response = requests.post(
            f"{settings.FRAPPE_URL.rstrip('/')}/api/method/upload_file",
            headers=FrappeClient._headers(),
            data=data,
            files={"file": (filename, content, content_type)},
            timeout=60,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"ERPNext upload failed ({response.status_code}): {response.text[:300]}"
            )

        return response.json()["message"]
