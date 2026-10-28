from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Single source of configuration, loaded once from app/.env."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Database
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    # ERPNext/Frappe REST API (used to upload photos so they appear in ERPNext)
    FRAPPE_URL: str = "http://204.12.251.252"
    FRAPPE_API_KEY: str | None = None
    FRAPPE_API_SECRET: str | None = None

    # Delivery geofence: the driver must be within this many metres of the
    # destination store's lat/lng (CH Store) to call /deliver. 0 disables it.
    DELIVERY_GEOFENCE_M: int = 50

    # ch_logistics (logistics-testing branch) hides Reject from drivers
    # (DRIVER_CAN_REJECT = false in the driver page); rejections are now
    # raised by dispatch. Set true to expose POST /manifests/{id}/reject again.
    DRIVER_CAN_REJECT: bool = False

    # SMTP (optional: only needed by endpoints that send mail)
    SMTP_SERVER: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    FROM_EMAIL: str | None = None


settings = Settings()
