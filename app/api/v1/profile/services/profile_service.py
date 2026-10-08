from fastapi import HTTPException

from ..repositories.profile_repo import ProfileRepository


class ProfileService:

    @staticmethod
    def me(user):

        record = ProfileRepository.get_user(user["sub"])

        if not record:
            raise HTTPException(status_code=404, detail="User not found")

        drivers = ProfileRepository.get_drivers_for_user(user["sub"])

        return {
            "user": {**record, "enabled": bool(record["enabled"])},
            "roles": user.get("roles", []),
            "primary_role": user.get("role"),
            "is_driver": bool(drivers),
            "driver": drivers[0] if drivers else None,
            "drivers": drivers,
            "stats": ProfileRepository.get_delivery_stats([d["driver_id"] for d in drivers]),
        }
