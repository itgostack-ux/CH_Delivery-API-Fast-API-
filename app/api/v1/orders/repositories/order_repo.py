from app.db.session import get_connection

ORDER_COLUMNS = """
    se.name AS order_id,
    se.posting_date,
    se.custom_status AS status,
    se.custom_logistics_status AS logistics_status,
    se.custom_transfer_type AS transfer_type,
    se.from_warehouse,
    se.to_warehouse,
    se.custom_source_store AS source_store,
    se.custom_target_store AS target_store,
    COALESCE(se.custom_total_qty, 0) AS total_qty,
    se.custom_delivery_challan AS delivery_challan,
    tm.name AS manifest_id,
    tm.status AS manifest_status,
    tm.manifest_date,
    tm.trip,
    tm.driver,
    tm.driver_name
"""

# Orders are linked to a manifest either through the manifest's item rows or
# through the stock entry's own custom_transfer_manifest field.
ORDER_FROM = """
    FROM `tabStock Entry` se
    LEFT JOIN `tabCH Transfer Manifest Item` tmi
        ON tmi.stock_entry = se.name
    LEFT JOIN `tabCH Transfer Manifest` tm
        ON tm.name = COALESCE(tmi.parent, se.custom_transfer_manifest)
"""


class OrderRepository:

    @staticmethod
    def get_driver_ids_for_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name
                    FROM tabDriver
                    WHERE user = %s
                    ORDER BY creation
                """, (email,))

                return [row["name"] for row in cursor.fetchall()]

        finally:
            conn.close()

    @staticmethod
    def list_orders(driver_ids=None, limit=200):
        """Orders carried by manifests; restricted to the given drivers when set."""

        where, params = ["se.docstatus < 2", "tm.name IS NOT NULL"], []

        if driver_ids:
            where.append("tm.driver IN (" + ", ".join(["%s"] * len(driver_ids)) + ")")
            params.extend(driver_ids)

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT DISTINCT {ORDER_COLUMNS}
                    {ORDER_FROM}
                    WHERE {" AND ".join(where)}
                    ORDER BY tm.manifest_date DESC, se.name DESC
                    LIMIT %s
                """, params + [limit])

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def get_order(order_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT {ORDER_COLUMNS},
                        se.custom_material_request AS material_request,
                        se.custom_entered_by AS entered_by,
                        se.custom_created_on AS created_on,
                        se.custom_pickup_datetime AS pickup_datetime,
                        se.custom_delivery_datetime AS delivery_datetime,
                        se.custom_package_image AS package_image,
                        se.custom_pickup_photo AS pickup_photo,
                        se.custom_delivery_photo AS delivery_photo,
                        COALESCE(se.custom_delivery_confirmed, 0) AS delivery_confirmed,
                        se.remarks
                    {ORDER_FROM}
                    WHERE se.name = %s
                    LIMIT 1
                """, (order_id,))

                order = cursor.fetchone()

                if not order:
                    return None

                cursor.execute("""
                    SELECT
                        item_code,
                        item_name,
                        COALESCE(qty, 0) AS qty,
                        uom,
                        basic_rate AS rate,
                        amount,
                        image,
                        serial_no,
                        custom_original_serials,
                        custom_scanned_serials,
                        custom_rejected_qty AS rejected_qty,
                        custom_rejection_reason AS rejection_reason
                    FROM `tabStock Entry Detail`
                    WHERE parent = %s
                    AND parenttype = 'Stock Entry'
                    ORDER BY idx
                """, (order_id,))

                order["items"] = cursor.fetchall()

                return order

        finally:
            conn.close()
