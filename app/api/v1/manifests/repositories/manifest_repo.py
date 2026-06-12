from app.db.session import get_connection


class ManifestRepository:

    @staticmethod
    def get_driver_manifests(driver_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        tm.name AS manifest_id,
                        tm.manifest_date,
                        tm.status,
                        tm.source_store,
                        tm.destination_store,
                        tm.vehicle_number,
                        tm.driver,
                        tm.driver_name,
                        tm.trip,
                        tm.shipment_priority,
                        tm.total_items,
                        tm.total_qty,

                        tmi.stock_entry,
                        tmi.material_request,
                        tmi.item_count,
                        tmi.total_qty AS item_qty,
                        tmi.transfer_status,
                        tmi.custom_received_qty,
                        tmi.custom_shortage_qty

                    FROM `tabCH Transfer Manifest` tm

                    LEFT JOIN `tabCH Transfer Manifest Item` tmi
                        ON tm.name = tmi.parent

                    WHERE tm.driver = %s

                    ORDER BY tm.creation DESC

                """, (driver_id,))

                return cursor.fetchall()

        finally:
            conn.close()