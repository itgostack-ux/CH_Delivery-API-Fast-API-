from app.db.session import get_connection


def _scope(driver_id, on_date, date_column):
    """Build the WHERE clause + params for an optional driver and optional date."""

    clauses, params = ["docstatus < 2"], []

    if driver_id:
        clauses.append("driver = %s")
        params.append(driver_id)

    if on_date:
        clauses.append(f"{date_column} = %s")
        params.append(on_date)

    return " AND ".join(clauses), params


class DashboardRepository:

    @staticmethod
    def get_driver_for_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name AS driver_id, full_name AS driver_name
                    FROM tabDriver
                    WHERE user = %s
                    LIMIT 1
                """, (email,))

                return cursor.fetchone()

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
    def manifest_summary(driver_id=None, on_date=None):

        where, params = _scope(driver_id, on_date, "manifest_date")

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
    def trip_summary(driver_id=None, on_date=None):

        where, params = _scope(driver_id, on_date, "trip_date")

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
    def manifests_on(on_date, driver_id=None, limit=50):

        where, params = _scope(driver_id, on_date, "manifest_date")

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
