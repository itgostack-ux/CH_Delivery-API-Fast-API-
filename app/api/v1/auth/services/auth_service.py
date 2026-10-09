import hashlib
import secrets
from datetime import datetime

from fastapi import HTTPException
from passlib.hash import pbkdf2_sha256

from app.core.email import EmailService
from app.core.security import create_access_token, revoke_token
from ..repositories.auth_repo import AuthRepository

# Roles the app recognises, highest privilege first. The first one the user
# holds becomes their primary_role; "Driver" is granted automatically to any
# user linked to a Driver record.
ROLE_PRIORITY = ["System Manager", "Delivery Manager", "Driver"]

# Users must hold at least one of these roles to log in to this API.
ALLOWED_ROLES = set(ROLE_PRIORITY)

OTP_PURPOSE = "App Login"
OTP_EXPIRES_MINUTES = 5
OTP_RESEND_SECONDS = 60       # minimum gap between two OTP requests
OTP_MAX_ATTEMPTS = 5          # wrong guesses allowed per OTP


def _hash_otp(email: str, otp: str) -> str:
    return hashlib.sha256(f"{email.lower()}:{otp}".encode()).hexdigest()


class AuthService:

    # ------------------------------------------------------------------
    # Password login
    # ------------------------------------------------------------------

    @staticmethod
    def login(email, password):

        user = AuthRepository.get_user_with_password(email)

        if not user or not pbkdf2_sha256.verify(password, user["password"]):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )

        return AuthService._issue_login(user)

    # ------------------------------------------------------------------
    # OTP login
    # ------------------------------------------------------------------

    @staticmethod
    def request_otp(email, ip_address=None):

        user = AuthRepository.get_user(email)

        if not user:
            raise HTTPException(status_code=404, detail="No user with this email")

        if not user["enabled"]:
            raise HTTPException(status_code=403, detail="User account is disabled")

        latest = AuthRepository.get_latest_otp(email, OTP_PURPOSE)

        if latest and latest["status"] == "Pending":
            age = (datetime.now() - latest["generated_at"]).total_seconds()
            if age < OTP_RESEND_SECONDS:
                raise HTTPException(
                    status_code=429,
                    detail=f"OTP already sent. Try again in {int(OTP_RESEND_SECONDS - age)} seconds"
                )

        otp = f"{secrets.randbelow(10**6):06d}"

        AuthRepository.create_otp(
            email=email,
            otp_hash=_hash_otp(email, otp),
            purpose=OTP_PURPOSE,
            expires_minutes=OTP_EXPIRES_MINUTES,
            ip_address=ip_address
        )

        try:
            EmailService.send_login_otp(
                to=email,
                full_name=user["full_name"],
                otp=otp,
                expires_minutes=OTP_EXPIRES_MINUTES
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not send OTP email: {e}")

        return {
            "message": f"OTP sent to {email}",
            "expires_in_seconds": OTP_EXPIRES_MINUTES * 60
        }

    @staticmethod
    def verify_otp(email, otp):

        record = AuthRepository.get_latest_otp(email, OTP_PURPOSE)

        if not record or record["status"] != "Pending":
            raise HTTPException(status_code=400, detail="No active OTP. Request a new one")

        if datetime.now() > record["expires_at"]:
            AuthRepository.expire_otp(record["name"])
            raise HTTPException(status_code=400, detail="OTP has expired. Request a new one")

        if record["attempts"] >= OTP_MAX_ATTEMPTS:
            AuthRepository.expire_otp(record["name"])
            raise HTTPException(status_code=400, detail="Too many wrong attempts. Request a new one")

        if record["otp_code"] != _hash_otp(email, otp):
            AuthRepository.record_otp_attempt(record["name"], verified=False)
            raise HTTPException(status_code=401, detail="Invalid OTP")

        AuthRepository.record_otp_attempt(record["name"], verified=True)

        user = AuthRepository.get_user(email)

        if not user:
            raise HTTPException(status_code=404, detail="No user with this email")

        return AuthService._issue_login(user)

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    @staticmethod
    def logout(user):
        """Same as the ERP's Sign Out: token revoked, devices deactivated, driver Offline."""

        from app.api.v1.driver.services.driver_service import DriverService

        return DriverService.sign_out(user)

    # ------------------------------------------------------------------
    # Shared: roles + token
    # ------------------------------------------------------------------

    @staticmethod
    def _issue_login(user):

        if not user["enabled"]:
            raise HTTPException(status_code=403, detail="User account is disabled")

        roles = AuthRepository.get_user_roles(user["name"])

        if AuthRepository.is_driver(user["name"]) and "Driver" not in roles:
            roles.append("Driver")

        granted = [r for r in ROLE_PRIORITY if r in roles]

        if not granted:
            raise HTTPException(
                status_code=403,
                detail="User has no role permitted to use this application"
            )

        primary_role = granted[0]

        if "Driver" in granted:
            from app.api.v1.driver.services.driver_service import DriverService
            DriverService.on_login(user["email"])

        token = create_access_token({
            "sub": user["email"],
            "name": user["full_name"],
            "roles": granted,
            "role": primary_role
        })

        return {
            "token": token,
            "user": {
                "name": user["name"],
                "email": user["email"],
                "full_name": user["full_name"],
                "mobile_no": user["mobile_no"] or "",
                "roles": granted,
                "primary_role": primary_role
            }
        }
