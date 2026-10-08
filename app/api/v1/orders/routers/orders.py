from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from ..schemas.order_schema import OrderDetailResponse, OrdersResponse
from ..services.order_service import OrderService

router = APIRouter()


@router.get("/list", response_model=OrdersResponse, summary="My orders (driver: own manifests; manager: all)")
def list_orders(user: dict = Depends(get_current_user)):

    return OrderService.list_orders(user)


@router.get("/{order_id}", response_model=OrderDetailResponse, summary="Order detail with items and serial numbers")
def get_order(order_id: str, user: dict = Depends(get_current_user)):

    return OrderService.get_order(user, order_id)
