"""Which tab a shipment leg belongs to - decided the way the ERPNext driver app
decides it: per Stock Entry leg, not per manifest.

A manifest can carry several legs. After "Accept Shipment" on one leg the ERP
stamps that leg's own driver_accepted_at / pickup_captured_at while the
manifest stays "Assigned" until every sibling leg is decided. That leg is
already on the vehicle, so it must show under Delivery Pending (the ERP calls
these "orphan accepted legs"), while its siblings stay under Pickup Pending.
"""

PICKUP_PENDING = "pickup_pending"
IN_TRANSIT = "in_transit"
DELIVERED = "delivered"
REJECTED = "rejected"

_DELIVERED_MANIFEST = {"delivered", "partially received", "received", "closed"}
_REJECTED_MANIFEST = {"rejected", "cancelled", "reverted", "recalled"}
# get_driver_assignments buckets "Recall Initiated" with In Transit: the goods
# are still on the vehicle and the driver has to bring them back.
_TRANSIT_MANIFEST = {"in transit", "pickup started", "recall initiated"}


def _norm(value):
    return (value or "").strip().lower()


def leg_stage(manifest_status, leg):
    """`leg` is a dict with the per-leg columns of CH Transfer Manifest Item
    (driver_accepted_at, pickup_captured_at, delivery_captured_at) and the
    Stock Entry's logistics_status."""

    ms = _norm(manifest_status)
    ls = _norm(leg.get("logistics_status"))

    if leg.get("delivery_captured_at") or ms in _DELIVERED_MANIFEST or ls == "delivered":
        return DELIVERED

    if ms in _REJECTED_MANIFEST or ls in ("reverted", "rejected"):
        return REJECTED

    if (leg.get("leg_accepted_at") or leg.get("pickup_captured_at")
            or ms in _TRANSIT_MANIFEST or ls in ("in transit", "picked up")):
        return IN_TRANSIT

    return PICKUP_PENDING


# Per-leg columns every shipment listing exposes (alias -> SQL expression).
LEG_COLUMNS = """
    tmi.driver_accepted_at   AS leg_accepted_at,
    tmi.pickup_captured_at,
    tmi.pickup_scanned_qr,
    tmi.delivery_captured_at,
    tmi.delivery_receiver_name
"""
