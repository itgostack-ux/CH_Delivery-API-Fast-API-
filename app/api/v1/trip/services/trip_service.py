from ..repositories.trip_repo import TripRepository
from ..schemas.trip_schema import AcceptStartTripRequest
from ..schemas.trip_schema import (
    AcceptStartTripRequest,
    ScanPickupQRRequest
)
from ..schemas.trip_schema import UploadPickupPhotoRequest
from ..schemas.trip_schema import ConfirmDeliveryRequest
from ..schemas.trip_schema import RequestDeliveryOTPRequest
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

    def get_accept_trip_details(self, trip_id):
        return self.repo.get_accept_trip_details(trip_id)
    
    def scan_pickup_qr(self, request: ScanPickupQRRequest):

        return self.repo.scan_pickup_qr(
        request.tripId,
        request.driverId,
        request.pickupToken,
        request.latitude,
        request.longitude
    )
    def upload_pickup_photo(self, request: UploadPickupPhotoRequest):

        return self.repo.upload_pickup_photo(
        request.manifestId,
        request.photo,
        request.latitude,
        request.longitude,
        request.notes
    )

    def confirm_delivery(self, request: ConfirmDeliveryRequest):

        return self.repo.confirm_delivery(
        request.tripId,
        request.manifestId,
        request.driverId,
        request.deliveryToken,
        request.otp,
        request.receiverName,
        request.deliveryPhoto,
        request.notes,
        request.latitude,
        request.longitude
    )
    def request_delivery_otp(
    self,
    request: RequestDeliveryOTPRequest
    ):
        return self.repo.request_delivery_otp(
            request.manifestId
        )   
   
    