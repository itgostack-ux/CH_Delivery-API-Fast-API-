from ..repositories.logout_repo import LogoutRepository


class LogoutService:

    @staticmethod
    def logout(email):

        user = LogoutRepository.get_user(email)

        if not user:
            return {
                "success": False,
                "message": "Invalid User"
            }

        if user["enabled"] != 1:
            return {
                "success": False,
                "message": "User Disabled"
            }

        return {
            "success": True,
            "message": "Logout Successful",
            "email": user["email"]
        }