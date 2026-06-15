from app.db.session import get_connection


class LogisticsRepository:

    @staticmethod
    def get_trip_dashboard_summary(driver_id, trip_date):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        COUNT(*) AS total_trips,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN status = 'Started'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS active_trips,

                        COALESCE(
                            SUM(
                                CASE
                                    WHEN status = 'Completed'
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS completed_trips

                    FROM `tabCH Logistics Trip`

                    WHERE driver=%s
                    AND trip_date=%s
                """, (driver_id, trip_date))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def get_trip_summary(driver_id, from_date, to_date):

        conn = get_connection()

        try:
           with conn.cursor() as cursor:

            cursor.execute("""
                SELECT
                    name AS trip_id,
                    trip_date,
                    status,
                    route,
                    vehicle_number,
                    total_shipments

                FROM `tabCH Logistics Trip`

                WHERE driver=%s
                AND trip_date BETWEEN %s AND %s

                ORDER BY trip_date DESC, creation DESC
            """, (
                driver_id,
                from_date,
                to_date
            ))

            return cursor.fetchall()

        finally:
           conn.close()

    @staticmethod
    def get_trip_details(trip_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        t.name AS trip_id,
                        t.trip_date,
                        t.status AS trip_status,
                        t.route,
                        t.driver,
                        t.driver_name,
                        t.vehicle_number,
                        t.total_shipments,

                        d.full_name,
                        d.cell_number,
                        d.custom_rating,
                        d.custom_total_deliveries,

                        r.route_name,
                        r.hub_warehouse,
                        r.estimated_distance_km,
                        r.estimated_duration_min,

                        rs.sequence,
                        rs.warehouse,
                        rs.store,
                        rs.stop_type,

                        tm.name AS manifest_id,
                        tm.status AS manifest_status,
                        tm.source_store,
                        tm.destination_store,
                        tm.total_items,
                        tm.total_qty

                    FROM `tabCH Logistics Trip` t

                    LEFT JOIN `tabDriver` d
                        ON d.name = t.driver

                    LEFT JOIN `tabCH Route` r
                        ON r.name = t.route

                    LEFT JOIN `tabCH Route Stop` rs
                        ON rs.parent = r.name

                    LEFT JOIN `tabCH Transfer Manifest` tm
                        ON tm.trip = t.name

                    WHERE t.name=%s

                    ORDER BY rs.sequence
                """, (trip_id,))

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def get_manifest_summary(driver_id, manifest_date):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                SELECT
                    name AS manifest_id,
                    manifest_date,
                    status,
                    source_store,
                    destination_store,
                    total_items,
                    total_qty,
                    trip

                FROM `tabCH Transfer Manifest`

                WHERE driver=%s
                AND manifest_date=%s

                ORDER BY creation DESC
            """, (driver_id, manifest_date))

            return cursor.fetchall()

        finally:
            conn.close()


    @staticmethod
    def get_manifest_details(manifest_id):

        conn = get_connection()

        try:
           with conn.cursor() as cursor:

            cursor.execute("""
                SELECT
                    tm.name AS manifest_id,
                    tm.manifest_date,
                    tm.status AS manifest_status,
                    tm.source_store,
                    tm.destination_store,
                    tm.driver,
                    tm.driver_name,
                    tm.vehicle_number,
                    tm.total_items,
                    tm.total_qty,

                    tmi.stock_entry,
                    tmi.material_request,
                    tmi.item_count,
                    tmi.total_qty AS item_qty,
                    tmi.transfer_status

                FROM `tabCH Transfer Manifest` tm

                LEFT JOIN `tabCH Transfer Manifest Item` tmi
                    ON tmi.parent = tm.name

                WHERE tm.name=%s
            """, (manifest_id,))

            return cursor.fetchall()

        finally:
           conn.close()   