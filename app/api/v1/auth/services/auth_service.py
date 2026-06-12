from passlib.hash import pbkdf2_sha256
from jose import jwt
from datetime import datetime, timedelta

from ..repositories.auth_repo import AuthRepository

SECRET_KEY = "CH_DELIVERY_SECRET"
ALGORITHM = "HS256"


class AuthService:

    @staticmethod
    def login(data):

        try:

            user = AuthRepository.get_user(data.usr)

            if not user:
                return {
                    "success": False,
                    "message": "Invalid User"
                }

            is_valid = pbkdf2_sha256.verify(
                data.pwd,
                user["password"]
            )

            if not is_valid:
                return {
                    "success": False,
                    "message": "Invalid Password"
                }

            token = jwt.encode(
                {
                    "sub": user["email"],
                    "name": user["full_name"],
                    "exp": datetime.utcnow() + timedelta(days=7)
                },
                SECRET_KEY,
                algorithm=ALGORITHM
            )

            return {
                "success": True,
                "message": "Login Successful",
                "token": token,
                "user": {
                    "name": user["name"],
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "mobile_no": user["mobile_no"] or ""
                }
            }

        except Exception as e:

            print("LOGIN ERROR:", str(e))

            return {
                "success": False,
                "message": str(e)
            }