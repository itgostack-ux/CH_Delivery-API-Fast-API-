from jose import jwt, JWTError
from fastapi import HTTPException, Header
import os

SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("JWT_ALGORITHM")


def get_current_user(authorization: str = Header(...)):

    try:
        token = authorization.replace("Bearer ", "")

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid Token"
        )