from app.db.session import get_connection


def _scope(driver_ids, on_date, date_column, alias=""):
    """WHERE clause + params for an optional list of driver IDs and optional date.

    `alias` prefixes the manifest/trip columns when the query joins tables.
    """

    clauses, params = [f"{alias}docstatus < 2"], []

    if driver_ids:
        clauses.append(f"{alias}driver IN (" + ", ".join(["%s"] * len(driver_ids)) + ")")
        params.extend(driver_ids)

    if on_date:
        clauses.append(f"{alias}{date_column} = %s")
        params.append(on_date)

    return " AND ".join(clauses), params


class DashboardRepository:

    @staticmethod
    def get_drivers_for_user(email):
        """All Driver records linked to this user (ERPNext allows several)."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name AS driver_id, full_name AS driver_name
                    FROM tabDriver
                    WHERE user = %s
                    ORDER BY creation
                """, (email,))

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def get_driver(driver_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name AS driver_id, full_name AS driver_name
                    FROM tabDriver
                    WHERE name = %s
                """, (driver_id,))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def manifest_summary(driver_ids=None, on_date=None):

        where, params = _scope(driver_ids, on_date, "manifest_date")

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        status,
                        COUNT(*) AS n,
                        COALESCE(SUM(total_items), 0) AS items,
                        COALESCE(SUM(total_qty), 0) AS qty
                    FROM `tabCH Transfer Manifest`
                    WHERE {where}
                    GROUP BY status
                """, params)

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def trip_summary(driver_ids=None, on_date=None):

        where, params = _scope(driver_ids, on_date, "trip_date")

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        status,
                        COUNT(*) AS n
                    FROM `tabCH Logistics Trip`
                    WHERE {where}
                    GROUP BY status
                """, params)

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def order_summary(driver_ids=None, on_date=None):
        """Stock Entries carried by the scoped manifests, grouped by logistics status."""

        where, params = _scope(driver_ids, on_date, "manifest_date", alias="tm.")

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        COALESCE(se.custom_logistics_status, tmi.transfer_status) AS status,
                        COUNT(DISTINCT tmi.stock_entry) AS n,
                        COALESCE(SUM(tmi.total_qty), 0) AS qty
                    FROM `tabCH Transfer Manifest Item` tmi
                    JOIN `tabCH Transfer Manifest` tm
                        ON tm.name = tmi.parent
                    LEFT JOIN `tabStock Entry` se
                        ON se.name = tmi.stock_entry
                    WHERE {where}
                    AND tmi.stock_entry IS NOT NULL
                    GROUP BY 1
                """, params)

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def orders_for_manifests(manifest_ids):
        """Stock Entry details for each manifest, keyed by manifest id."""

        if not manifest_ids:
            return {}

        placeholders = ", ".join(["%s"] * len(manifest_ids))

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        tmi.parent AS manifest_id,
                        tmi.stock_entry AS order_id,
                        se.custom_logistics_status AS logistics_status,
                        tmi.transfer_status,
                        se.from_warehouse,
                        se.to_warehouse,
                        COALESCE(tmi.total_qty, se.custom_total_qty, 0) AS qty,
                        se.custom_delivery_challan AS delivery_challan,
                        COALESCE(tmi.material_request, se.custom_material_request) AS material_request
                    FROM `tabCH Transfer Manifest Item` tmi
                    LEFT JOIN `tabStock Entry` se
                        ON se.name = tmi.stock_entry
                    WHERE tmi.parent IN ({placeholders})
                    AND tmi.stock_entry IS NOT NULL
                    ORDER BY tmi.parent, tmi.idx
                """, manifest_ids)

                grouped = {}

                for row in cursor.fetchall():
                    grouped.setdefault(row.pop("manifest_id"), []).append(row)

                return grouped

        finally:
            conn.close()

    @staticmethod
    def manifests_on(on_date, driver_ids=None, limit=50, status="Assigned"):
        """Manifests for the day; by default only the ones still to be handled (Assigned)."""

        where, params = _scope(driver_ids, on_date, "manifest_date")

        if status:
            where += " AND status = %s"
            params.append(status)

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        name AS manifest_id,
                        manifest_date,
                        status,
                        source_store,
                        destination_store,
                        trip,
                        shipment_priority AS priority,
                        COALESCE(total_items, 0) AS total_items,
                        COALESCE(total_qty, 0) AS total_qty
                    FROM `tabCH Transfer Manifest`
                    WHERE {where}
                    ORDER BY stop_sequence, creation DESC
                    LIMIT %s
                """, params + [limit])

                return cursor.fetchall()

        finally:
            conn.close()
