from app.db.session import get_connection


class TripRepository:

    @staticmethod
    def get_today_trip(driver_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # Trip Header
                cursor.execute("""
                    SELECT
                        t.name AS trip_id,
                        t.trip_date,
                        t.status,
                        t.direction,
                        t.route,
                        t.driver,
                        t.driver_name,
                        t.vehicle,
                        t.vehicle_number,
                        t.planned_start,
                        t.planned_end,
                        t.actual_start,
                        t.actual_end,
                        t.total_shipments,

                        (
                            SELECT COUNT(*)
                            FROM `tabCH Logistics Trip Stop`
                            WHERE parent = t.name
                            AND stop_type = 'Pickup'
                        ) AS pickups,

                        (
                            SELECT COUNT(*)
                            FROM `tabCH Logistics Trip Stop`
                            WHERE parent = t.name
                            AND stop_type = 'Drop'
                        ) AS drops

                    FROM `tabCH Logistics Trip` t

                    WHERE t.driver = %s
                    AND t.status IN ('Assigned','Started')

                    ORDER BY t.creation DESC
                    LIMIT 1
                """, (driver_id,))

                trip = cursor.fetchone()

                if not trip:
                    return None

                # Stops
                cursor.execute("""
                    SELECT
                        sequence,
                        stop_type,
                        warehouse,
                        store,
                        status,
                        eta,
                        ata,
                        gps_lat,
                        gps_lng,
                        manifest_count,
                        pickup_token,
                        delivery_token,
                        pickup_scanned_at,
                        pickup_scanned_by,
                        delivery_scanned_at,
                        delivery_scanned_by

                    FROM `tabCH Logistics Trip Stop`

                    WHERE parent=%s

                    ORDER BY sequence
                """, (trip["trip_id"],))

                stops = cursor.fetchall()

                # Manifests
                cursor.execute("""
                    SELECT
                        name AS manifest_id,
                        status,
                        source_store,
                        destination_store,
                        total_items,
                        total_qty

                    FROM `tabCH Transfer Manifest`

                    WHERE trip=%s

                    ORDER BY creation
                """, (trip["trip_id"],))

                manifests = cursor.fetchall()

                return {
                    "trip": trip,
                    "stops": stops,
                    "manifests": manifests
                }

        finally:
            conn.close()

    @staticmethod
    def accept_start_trip(
        trip_id,
        driver_id,
        latitude,
        longitude
    ):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # Validate Trip
                cursor.execute("""
                    SELECT
                        name
                    FROM `tabCH Logistics Trip`
                    WHERE name=%s
                    AND driver=%s
                    AND status='Assigned'
                """, (
                    trip_id,
                    driver_id
                ))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip Not Found or Already Started"
                    }

                # Update Trip
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip`
                    SET
                        status='Started',
                        actual_start=NOW(),
                        modified=NOW()
                    WHERE
                        name=%s
                        AND driver=%s
                """, (
                    trip_id,
                    driver_id
                ))

                # Update Pickup Stop
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip Stop`
                    SET
                        status='Completed',
                        ata=NOW(),
                        gps_lat=%s,
                        gps_lng=%s,
                        pickup_scanned_at=NOW(),
                        pickup_scanned_by=%s
                    WHERE
                        parent=%s
                        AND stop_type='Pickup'
                """, (
                    latitude,
                    longitude,
                    driver_id,
                    trip_id
                ))

                # Update Manifests
                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET
                        status='In Transit'
                    WHERE trip=%s
                """, (trip_id,))

                conn.commit()

                return {
                    "success": True,
                    "message": "Trip Started Successfully"
                }

        except Exception as e:

            conn.rollback()

            return {
                "success": False,
                "message": str(e)
            }

        finally:
            conn.close()
    @staticmethod
    def get_notifications(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                SELECT
                    name,
                    creation,
                    subject,
                    email_content,
                    document_type,
                    document_name,
                    `read`
                FROM `tabNotification Log`
                WHERE for_user = %s
                  AND document_type = 'CH Logistics Trip'
                ORDER BY creation DESC
            """, (email,))

            return cursor.fetchall()

        finally:
         conn.close()

    @staticmethod
    def mark_notification_read(notification_name):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                UPDATE `tabNotification Log`
                SET `read` = 1
                WHERE name = %s
            """, (notification_name,))

            conn.commit()

            return {
                "success": True,
                "message": "Notification marked as read"
            }

        finally:
            conn.close()