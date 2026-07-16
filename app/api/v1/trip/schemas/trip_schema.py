from pydantic import BaseModel


class TripResponse(BaseModel):
    tripId: int
    tripNo: str
    driver: str