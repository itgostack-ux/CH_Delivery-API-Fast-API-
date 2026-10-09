from fastapi import HTTPException

from ..repositories.order_repo import OrderRepository

MANAGER_ROLES = {"System Manager", "Delivery Manager"}


def _serials(row):
    """Serial numbers can live in three fields; return a clean, de-duplicated list."""

    raw = " ".join(
        str(row.get(k) or "")
        for k in ("custom_scanned_serials", "custom_original_serials", "serial_no")
    )

    seen, out = set(), []

    for token in raw.replace(",", " ").replace("\n", " ").split():
        if token not in seen:
            seen.add(token)
            out.append(token)

    return out


def _boxes(row):
    labels = [x for x in (row.pop("box_labels", None) or "").split(",") if x]
    row["box_labels"] = labels
    row["qr"] = labels[0] if labels else None


class OrderService:

    @staticmethod
    def _scope(user):
        """None = all orders (managers); otherwise the user's Driver IDs."""

        if set(user.get("roles", [])) & MANAGER_ROLES:
            return None

        driver_ids = OrderRepository.get_driver_ids_for_user(user["sub"])

        if not driver_ids:
            raise HTTPException(
                status_code=403,
                detail="No Driver record is linked to this user"
            )

        return driver_ids

    @staticmethod
    def list_orders(user):

        rows = OrderRepository.list_orders(OrderService._scope(user))

        for row in rows:
            _boxes(row)

        return {"count": len(rows), "data": rows}

    @staticmethod
    def get_order(user, order_id):

        driver_ids = OrderService._scope(user)
        order = OrderRepository.get_order(order_id)

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if driver_ids is not None and order["driver"] not in driver_ids:
            raise HTTPException(
                status_code=403,
                detail="This order is not assigned to you"
            )

        _boxes(order)
        order["delivery_confirmed"] = bool(order["delivery_confirmed"])
        order["items"] = [{**row, "serials": _serials(row)} for row in order["items"]]

        return {"data": order}
