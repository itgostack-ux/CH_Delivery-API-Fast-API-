import secrets
import time
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

# Tokens revoked by /auth/logout, kept until they would have expired anyway.
# In-memory: fine for a single API process; move to Redis/DB when scaling out.
_revoked_tokens: dict[str, float] = {}


def _purge_revoked():
    now = time.time()
    for jti in [j for j, exp in _revoked_tokens.items() if exp < now]:
        _revoked_tokens.pop(jti, None)


def create_access_token(claims: dict) -> str:
    payload = {
        **claims,
        "jti": secrets.token_urlsafe(16),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def revoke_token(payload: dict) -> None:
    """Invalidate a token (by its jti) for the rest of its lifetime."""
    _purge_revoked()
    jti = payload.get("jti")
    if jti:
        _revoked_tokens[jti] = float(payload.get("exp", time.time()))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)
) -> dict:
    """Decode the Bearer token; returns the JWT payload (sub, name, roles, role)."""

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid Token")

    if payload.get("jti") in _revoked_tokens:
        raise HTTPException(status_code=401, detail="Token has been logged out")

    return payload


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
