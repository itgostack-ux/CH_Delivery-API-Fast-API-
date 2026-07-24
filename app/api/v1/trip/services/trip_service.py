from ..repositories.trip_repo import TripRepository
from ..schemas.trip_schema import AcceptStartTripRequest


class TripService:

    def __init__(self):
        self.repo = TripRepository()

    def get_today_trip(self, driver_id: str):

        data = self.repo.get_today_trip(driver_id)

        if not data:
            return {
                "success": False,
                "message": "No Trip Assigned"
            }

        trip = data["trip"]

        return {
            "success": True,
            "data": {
                "trip": {
                    "trip_id": trip["trip_id"],
                    "trip_date": str(trip["trip_date"]),
                    "status": trip["status"],
                    "direction": trip["direction"],
                    "route": trip["route"],
                    "driver_id": trip["driver"],
                    "driver_name": trip["driver_name"],
                    "vehicle": trip["vehicle"],
                    "vehicle_number": trip["vehicle_number"],
                    "planned_start": trip["planned_start"],
                    "planned_end": trip["planned_end"],
                    "actual_start": trip["actual_start"],
                    "actual_end": trip["actual_end"],
                    "pickups": trip["pickups"],
                    "drops": trip["drops"],
                    "shipments": trip["total_shipments"]
                },
                "stops": data["stops"],
                "manifests": data["manifests"]
            }
        }

    def accept_start_trip(self, request: AcceptStartTripRequest):

        return self.repo.accept_start_trip(
            request.tripId,
            request.driverId,
            request.latitude,
            request.longitude
        )
    def get_notifications(self, email):
        return self.repo.get_notifications(email)

    def mark_notification_read(self, notification_name):
        return self.repo.mark_notification_read(notification_name)