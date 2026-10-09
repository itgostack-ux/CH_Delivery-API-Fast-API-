from datetime import date, datetime

from pydantic import BaseModel


class OrderSummary(BaseModel):
    """A shipment = ERPNext Stock Entry (Material Transfer), e.g. GFTNMT26000179."""
    order_id: str
    posting_date: date | None = None
    status: str | None = None               # ERPNext custom_status (Assigned, Rejected, ...)
    logistics_status: str | None = None     # Pending Pickup, Picked Up, In Transit, Delivered, Reverted
    transfer_type: str | None = None
    from_warehouse: str | None = None
    to_warehouse: str | None = None
    source_store: str | None = None
    target_store: str | None = None
    total_qty: float
    delivery_challan: str | None = None
    box_labels: list[str] = []          # QR labels on the boxes, e.g. GFTNDC26000355-B01
    qr: str | None = None               # first box label = what to send as `qr` at pickup/deliver
    manifest_id: str | None = None
    manifest_status: str | None = None
    manifest_date: date | None = None
    trip: str | None = None
    driver: str | None = None
    driver_name: str | None = None


class OrdersResponse(BaseModel):
    success: bool = True
    count: int
    data: list[OrderSummary]


class OrderLine(BaseModel):
    item_code: str
    item_name: str | None = None
    qty: float
    uom: str | None = None
    rate: float | None = None
    amount: float | None = None
    image: str | None = None
    serials: list[str] = []
    rejected_qty: float | None = None
    rejection_reason: str | None = None


class OrderDetail(OrderSummary):
    material_request: str | None = None
    entered_by: str | None = None
    created_on: date | None = None
    pickup_datetime: datetime | None = None
    delivery_datetime: datetime | None = None
    package_image: str | None = None
    pickup_photo: str | None = None
    delivery_photo: str | None = None
    delivery_confirmed: bool = False
    remarks: str | None = None
    items: list[OrderLine] = []


class OrderDetailResponse(BaseModel):
    success: bool = True
    data: OrderDetail
