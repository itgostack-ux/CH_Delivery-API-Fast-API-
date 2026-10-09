from app.db.session import get_connection


# A manifest counts as "today's work" when its trip runs today, when it was
# dated today, or when it was delivered today - not only by manifest_date,
# because dispatch often attaches older manifests to a trip created today.
MANIFEST_TODAY = """(
    tr.trip_date = %s
    OR tm.manifest_date = %s
    OR DATE(tm.delivery_datetime) = %s
    OR DATE(tm.pickup_datetime) = %s
)"""

ACTIVE_STATUSES = ("Assigned", "Pickup Started", "In Transit")


def _scope(driver_ids, on_date, date_column, alias=""):
    """WHERE clause + params for an optional list of driver IDs and optional date.

    `alias` prefixes the manifest/trip columns when the query joins tables.
    For manifests (alias "tm.") the date test is MANIFEST_TODAY (needs the
    `tr` trip join); for trips it is the plain date column.
    """

    clauses, params = [f"{alias}docstatus < 2"], []

    if driver_ids:
        clauses.append(f"{alias}driver IN (" + ", ".join(["%s"] * len(driver_ids)) + ")")
        params.extend(driver_ids)

    if on_date:
        if alias == "tm.":
            clauses.append(MANIFEST_TODAY)
            params.extend([on_date] * 4)
        else:
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

        where, params = _scope(driver_ids, on_date, "manifest_date", alias="tm.")

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        tm.status,
                        COUNT(*) AS n,
                        COALESCE(SUM(tm.total_items), 0) AS items,
                        COALESCE(SUM(tm.total_qty), 0) AS qty
                    FROM `tabCH Transfer Manifest` tm
                    LEFT JOIN `tabCH Logistics Trip` tr ON tr.name = tm.trip
                    WHERE {where}
                    GROUP BY tm.status
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
                    LEFT JOIN `tabCH Logistics Trip` tr
                        ON tr.name = tm.trip
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
                        COALESCE(tmi.material_request, se.custom_material_request) AS material_request,
                        (SELECT GROUP_CONCAT(p.package_label ORDER BY p.idx SEPARATOR ',')
                           FROM `tabCH Stock Entry Package` p
                           WHERE p.parent = tmi.stock_entry AND p.parenttype = 'Stock Entry') AS box_labels
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
    def manifests_on(on_date, driver_ids=None, limit=50, statuses=ACTIVE_STATUSES):
        """Work on hand: every active manifest in scope (Assigned / Pickup
        Started / In Transit) whatever its date, plus the ones delivered on
        `on_date` - i.e. what the driver sees on the ERP board today."""

        where, params = _scope(driver_ids, None, "manifest_date", alias="tm.")

        where += " AND (tm.status IN (" + ", ".join(["%s"] * len(statuses)) + ") OR DATE(tm.delivery_datetime) = %s)"
        params.extend(list(statuses) + [on_date])

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        tm.name AS manifest_id,
                        tm.manifest_date,
                        tr.trip_date,
                        tm.status,
                        tm.source_store,
                        tm.destination_store,
                        tm.trip,
                        tr.status AS trip_status,
                        tm.driver,
                        tm.driver_name,
                        tm.stop_sequence,
                        tm.shipment_priority AS priority,
                        COALESCE(tm.total_items, 0) AS total_items,
                        COALESCE(tm.total_qty, 0) AS total_qty,
                        tm.driver_accepted_at,
                        tm.pickup_datetime,
                        tm.delivery_datetime
                    FROM `tabCH Transfer Manifest` tm
                    LEFT JOIN `tabCH Logistics Trip` tr ON tr.name = tm.trip
                    WHERE {where}
                    ORDER BY FIELD(tm.status, 'In Transit', 'Pickup Started', 'Assigned', 'Delivered'),
                             tr.trip_date DESC, tm.stop_sequence, tm.creation DESC
                    LIMIT %s
                """, params + [limit])

                return cursor.fetchall()

        finally:
            conn.close()
