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
                        SELECT stock_entry, from_warehouse, to_warehouse, transfer_status
                        FROM `tabCH Transfer Manifest Item`
                        WHERE parent = %s
                        ORDER BY idx
                    """, (manifest_id,))
                    manifest["items"] = cursor.fetchall()

                return manifest

        finally:
            conn.close()
