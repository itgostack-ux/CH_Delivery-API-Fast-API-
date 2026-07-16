from pydantic import BaseModel


class DriverDeviceRequest(BaseModel):
    driver: str
    driver_name: str
    user: str
    platform: str
    app_version: str | None = None
    device_id: str
    fcm_token: str