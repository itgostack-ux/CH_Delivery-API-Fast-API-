from trip.repositories.trip_repo import TripRepository


class TripService:

    def __init__(self):
        self.repo = TripRepository()

    def get_trips(self):
        return self.repo.get_trips()

    def get_trip(self, trip_id: int):
        return self.repo.get_trip(trip_id)