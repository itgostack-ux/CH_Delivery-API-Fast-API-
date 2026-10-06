from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(claims: dict) -> str:
    payload = {
        **claims,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)
) -> dict:
    """Decode the Bearer token; returns the JWT payload (sub, name, roles, role)."""

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid Token")


def require_roles(*allowed: str):
    """Dependency factory: allow only users holding at least one of `allowed`.

    Usage: Depends(require_roles("System Manager", "Delivery Manager"))
    """

    def checker(user: dict = Depends(get_current_user)) -> dict:

        if not set(user.get("roles", [])) & set(allowed):
            raise HTTPException(
                status_code=403,
                detail=f"Requires role: {', '.join(allowed)}"
            )

        return user

    return checker
