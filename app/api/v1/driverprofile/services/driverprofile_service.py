from ..repositories.driverprofile_repo import DriverProfileRepository


class DriverProfileService:

    @staticmethod
    def get_profile(email):

        driver = DriverProfileRepository.get_driver(email)

        if not driver:
            return {
                "success": False,
                "message": "Driver Not Found"
            }

        return {
            "success": True,
            "data": {
                "driver_id": driver["driver_id"],
                "first_name": driver["first_name"] or "",
                "last_name": driver["last_name"] or "",
                "username": driver["username"] or "",
                "full_name": driver["full_name"],

                "email": driver["email"],
                "mobile_no": driver["mobile_no"] or "",
                "enabled": driver["enabled"],

                "status": driver["status"],
                "employee": driver["employee"],

                "license_number": driver["license_number"] or "",
                "issuing_date": str(driver["issuing_date"]) if driver["issuing_date"] else "",
                "expiry_date": str(driver["expiry_date"]) if driver["expiry_date"] else "",

                "partner_type": driver["custom_partner_type"] or "",
                "courier_partner": driver["custom_courier_partner"] or "",
                "vehicle": driver["custom_default_vehicle"] or "",

                "rating": float(driver["custom_rating"] or 0),
                "total_deliveries": int(driver["custom_total_deliveries"] or 0)
            }
        }