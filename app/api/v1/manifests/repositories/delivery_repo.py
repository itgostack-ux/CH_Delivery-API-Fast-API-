from app.db.session import get_connection


class DeliveryRepository:
    """Read-only lookups for the pickup/delivery flow. All writes go through
    the ERP's own methods (see delivery_service.py)."""

    @staticmethod
    def otp_email_status(manifest_id, since_seconds=180):
        """Did ERPNext actually get the OTP email out? Looks at its Email Queue."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT status, LEFT(error, 200) AS error
                    FROM `tabEmail Queue`
                    WHERE reference_doctype = 'CH Transfer Manifest'
                    AND reference_name = %s
                    AND creation >= DATE_SUB(NOW(6), INTERVAL %s SECOND)
                    ORDER BY creation DESC
                    LIMIT 1
                """, (manifest_id, since_seconds))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def leg_lookup(manifest_id):
        """Every code that identifies a shipment leg of this manifest, lower-cased:
        the stock entry (GFTNMT...), its delivery challan (GFTNDC...) and each
        box label (GFTNDC...-B01) -> stock entry."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT tmi.stock_entry, se.custom_delivery_challan AS challan, p.package_label
                    FROM `tabCH Transfer Manifest Item` tmi
                    LEFT JOIN `tabStock Entry` se ON se.name = tmi.stock_entry
                    LEFT JOIN `tabCH Stock Entry Package` p
                           ON p.parent = tmi.stock_entry AND p.parenttype = 'Stock Entry'
                    WHERE tmi.parent = %s
                    ORDER BY tmi.idx, p.idx
                """, (manifest_id,))

                lookup = {}
                for row in cursor.fetchall():
                    se = row["stock_entry"]
                    for code in (se, row["challan"], row["package_label"]):
                        if code:
                            lookup.setdefault(code.strip().lower(), se)
                return lookup

        finally:
            conn.close()

    @staticmethod
    def get_item_row_name(manifest_id, stock_entry):
        """Row id of the shipment inside the manifest (tabCH Transfer Manifest Item)."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name
                    FROM `tabCH Transfer Manifest Item`
                    WHERE parent = %s AND stock_entry = %s
                    LIMIT 1
                """, (manifest_id, stock_entry))

                row = cursor.fetchone()
                return row["name"] if row else None

        finally:
            conn.close()

    @staticmethod
    def get_store_location(store_code, warehouse=None):
        """Drop point, resolved the way ch_logistics does it
        (optimizer._warehouse_coords_map): the leg's Warehouse coordinates
        first, then the linked CH Store's latitude/longitude, then the store's
        older custom_latitude/custom_longitude text fields."""

        if not store_code and not warehouse:
            return None

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                wh = None
                if warehouse:
                    cursor.execute("""
                        SELECT name, custom_latitude, custom_longitude, ch_store
                        FROM tabWarehouse WHERE name = %s
                    """, (warehouse,))
                    wh = cursor.fetchone()

                store_key = store_code or (wh or {}).get("ch_store")
                row = None
                if store_key:
                    cursor.execute("""
                        SELECT name AS store, store_name, address, city, pincode,
                               NULLIF(TRIM(custom_latitude), '') AS lat_text,
                               NULLIF(TRIM(custom_longitude), '') AS lng_text,
                               latitude, longitude, google_maps_url
                        FROM `tabCH Store`
                        WHERE name = %s
                    """, (store_key,))
                    row = cursor.fetchone()
                if row is None and warehouse:
                    cursor.execute("""
                        SELECT name AS store, store_name, address, city, pincode,
                               NULLIF(TRIM(custom_latitude), '') AS lat_text,
                               NULLIF(TRIM(custom_longitude), '') AS lng_text,
                               latitude, longitude, google_maps_url
                        FROM `tabCH Store`
                        WHERE warehouse = %s AND disabled = 0
                        LIMIT 1
                    """, (warehouse,))
                    row = cursor.fetchone()

        finally:
            conn.close()

        if not row and not wh:
            return None

        row = row or {"store": store_code, "store_name": None, "address": None, "city": None,
                      "pincode": None, "lat_text": None, "lng_text": None,
                      "latitude": None, "longitude": None, "google_maps_url": None}

        def _num(*candidates):
            for c in candidates:
                try:
                    v = float(c) if c not in (None, "") else 0.0
                except (TypeError, ValueError):
                    v = 0.0
                if v:
                    return v
            return None

        lat_text, lng_text = row.pop("lat_text"), row.pop("lng_text")
        row["latitude"] = _num((wh or {}).get("custom_latitude"), row.get("latitude"), lat_text)
        row["longitude"] = _num((wh or {}).get("custom_longitude"), row.get("longitude"), lng_text)
        row["warehouse"] = warehouse
        row["source"] = ("warehouse" if (wh or {}).get("custom_latitude") else
                         "store" if row.get("latitude") else None)
        return row

    @staticmethod
    def get_manifest(manifest_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name AS manifest_id, status, docstatus, driver, driver_name, trip,
                        source_warehouse, source_store, destination_warehouse, destination_store,
                        stop_sequence, qr_payload, tracking_token, driver_accepted_at,
                        pickup_datetime, delivery_datetime, receiver_name,
                        delivery_otp_log, delivery_otp_expires_at, delivery_otp_verified,
                        total_items, total_qty
                    FROM `tabCH Transfer Manifest`
                    WHERE name = %s
                """, (manifest_id,))

                manifest = cursor.fetchone()

                if manifest:
                    cursor.execute("""
                        SELECT stock_entry, from_warehouse, to_warehouse, transfer_status,
                               driver_accepted_at, pickup_captured_at, delivery_captured_at
                        FROM `tabCH Transfer Manifest Item`
                        WHERE parent = %s
                        ORDER BY idx
                    """, (manifest_id,))
                    manifest["items"] = cursor.fetchall()

                return manifest

        finally:
            conn.close()
