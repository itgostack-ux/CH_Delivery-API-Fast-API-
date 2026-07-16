class TripRepository:

    def get_trips(self):
        return [
            {
                "tripId": 1,
                "tripNo": "TRIP0001",
                "driver": "John"
            }
        ]

    def get_trip(self, trip_id: int):
        return {
            "tripId": trip_id,
            "tripNo": f"TRIP{trip_id:04}",
            "driver": "John"
        }