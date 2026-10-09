import json
import threading

import requests
from fastapi import HTTPException

from app.core.config import settings


class FrappeError(Exception):
    """A readable error returned by ERPNext (frappe.throw / validation)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _extract_message(response):
    """Pull the human message out of a Frappe error response."""

    try:
        body = response.json()
    except ValueError:
        return response.text[:300]

    msgs = body.get("_server_messages")
    if msgs:
        try:
            parts = [json.loads(m).get("message", "") for m in json.loads(msgs)]
            text = " ".join(p for p in parts if p)
            if text:
                return text
        except (ValueError, AttributeError):
            pass

    exc = body.get("exception") or body.get("message") or ""
    if isinstance(exc, str) and exc:
        # "frappe.exceptions.ValidationError: Something" -> "Something"
        return exc.split(": ", 1)[-1][:300]

    return response.text[:300]


class FrappeClient:
    """Calls into the ERPNext site over its REST API.

    Two identities:
      * the service account from app/.env (FRAPPE_API_KEY/SECRET) - admin tasks
      * each driver - obtained by minting that user's API keys with the service
        account (frappe.core.doctype.user.user.generate_keys). Driver actions
        then run under the driver's own ERPNext user, exactly like the ERP
        Delivery App page, so permissions, "rejected_by", comments and the
        dispatch board all show the real driver.
    """

    _user_keys: dict[str, tuple[str, str]] = {}
    _admin_user: str | None = None
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    # identities
    # ------------------------------------------------------------------

    @staticmethod
    def _base():
        return settings.FRAPPE_URL.rstrip("/")

    @staticmethod
    def _admin_headers():

        if not (settings.FRAPPE_API_KEY and settings.FRAPPE_API_SECRET):
            raise HTTPException(
                status_code=503,
                detail="FRAPPE_API_KEY / FRAPPE_API_SECRET are not set in app/.env "
                       "(ERPNext: User > API Access > Generate Keys)"
            )

        return {
            "Authorization": f"token {settings.FRAPPE_API_KEY}:{settings.FRAPPE_API_SECRET}",
            "Accept": "application/json",
        }

    @classmethod
    def _admin_user_name(cls):

        if cls._admin_user is None:
            r = requests.get(cls._base() + "/api/method/frappe.auth.get_logged_user",
                             headers=cls._admin_headers(), timeout=30)
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"ERPNext service account rejected: {_extract_message(r)}")
            cls._admin_user = r.json()["message"]

        return cls._admin_user

    @classmethod
    def headers_for_user(cls, email):
        """Headers that make ERPNext treat the call as `email`."""

        if email.lower() == cls._admin_user_name().lower():
            return cls._admin_headers()

        with cls._lock:
            if email not in cls._user_keys:
                admin = cls._admin_headers()

                r = requests.post(cls._base() + "/api/method/frappe.core.doctype.user.user.generate_keys",
                                  headers=admin, json={"user": email}, timeout=30)
                if r.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"Could not create ERPNext API keys for {email}: {_extract_message(r)}")

                secret = r.json()["message"]["api_secret"]

                r = requests.get(cls._base() + f"/api/resource/User/{email}",
                                 headers=admin, params={"fields": json.dumps(["api_key"])}, timeout=30)
                if r.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"Could not read ERPNext API key for {email}: {_extract_message(r)}")

                cls._user_keys[email] = (r.json()["data"]["api_key"], secret)

            key, secret = cls._user_keys[email]

        return {"Authorization": f"token {key}:{secret}", "Accept": "application/json"}

    @classmethod
    def forget_user(cls, email):
        cls._user_keys.pop(email, None)

    # ------------------------------------------------------------------
    # calls
    # ------------------------------------------------------------------

    @classmethod
    def call(cls, method, args=None, as_user=None, timeout=90):
        """POST /api/method/<method>; returns the `message`.

        ERPNext validation errors (frappe.throw) surface as HTTP 400 with the
        ERP's own text; anything else as 502.
        """

        headers = cls.headers_for_user(as_user) if as_user else cls._admin_headers()

        try:
            r = requests.post(cls._base() + "/api/method/" + method,
                              headers=headers, json=args or {}, timeout=timeout)
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"ERPNext unreachable: {e}")

        if r.status_code == 200:
            return r.json().get("message")

        if r.status_code in (401, 403) and as_user:
            # key pair may have been regenerated elsewhere; mint again once
            cls.forget_user(as_user)
            headers = cls.headers_for_user(as_user)
            r = requests.post(cls._base() + "/api/method/" + method, headers=headers, json=args or {}, timeout=timeout)
            if r.status_code == 200:
                return r.json().get("message")

        message = _extract_message(r)
        status = 400 if r.status_code in (417, 409, 403, 404) else 502
        raise HTTPException(status_code=status, detail=message)

    @classmethod
    def set_value(cls, doctype, name, fieldname, value, as_user=None):
        """frappe.client.set_value - single-field update, also for child rows."""

        return cls.call("frappe.client.set_value",
                        {"doctype": doctype, "name": name, "fieldname": fieldname, "value": value},
                        as_user=as_user)

    @classmethod
    def update_doc(cls, doctype, name, data, as_user=None):
        """PUT /api/resource/<doctype>/<name> - a proper document update (runs
        the ERP's validations and hooks, unlike raw SQL)."""

        headers = cls.headers_for_user(as_user) if as_user else cls._admin_headers()

        try:
            r = requests.put(cls._base() + f"/api/resource/{doctype}/{name}", headers=headers, json=data, timeout=60)
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"ERPNext unreachable: {e}")

        if r.status_code != 200:
            raise HTTPException(status_code=400 if r.status_code in (417, 403, 404, 409) else 502, detail=_extract_message(r))

        return r.json().get("data")

    @classmethod
    def upload_file(cls, filename, content, content_type, doctype=None, docname=None,
                    fieldname=None, is_private=True, as_user=None):
        """Attach a file (optionally to a document). Returns the File doc (has file_url)."""

        headers = cls.headers_for_user(as_user) if as_user else cls._admin_headers()

        data = {"is_private": "1" if is_private else "0", "folder": "Home"}
        if doctype and docname:
            data.update({"doctype": doctype, "docname": docname})
        if fieldname:
            data["fieldname"] = fieldname

        try:
            r = requests.post(cls._base() + "/api/method/upload_file", headers=headers, data=data,
                              files={"file": (filename, content, content_type)}, timeout=120)
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"ERPNext unreachable: {e}")

        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"ERPNext upload failed: {_extract_message(r)}")

        return r.json()["message"]
