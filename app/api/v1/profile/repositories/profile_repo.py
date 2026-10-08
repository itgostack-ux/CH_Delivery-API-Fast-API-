from app.db.session import get_connection


class ProfileRepository:

    @staticmethod
    def get_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name,
                        email,
                        full_name,
                        first_name,
                        last_name,
                        mobile_no,
                        phone,
                        user_image,
                        enabled,
                        user_type,
                        last_login
                    FROM tabUser
                    WHERE email = %s
                """, (email,))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def get_drivers_for_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name AS driver_id,
                        full_name,
                        status,
                        availability_status,
                        employee,
                        transporter,
                        cell_number,
                        address,
                        license_number,
                        issuing_date,
                        expiry_date,
                        custom_partner_type AS partner_type,
                        custom_courier_partner AS courier_partner,
                        custom_default_vehicle AS default_vehicle,
                        COALESCE(custom_rating, 0) AS rating,
                        COALESCE(custom_total_deliveries, 0) AS total_deliveries,
                        max_stops_per_trip,
                        current_trip,
                        last_active,
                        current_lat,
                        current_lng,
                        last_geo_at
                    FROM tabDriver
                    WHERE user = %s
                    ORDER BY creation
                """, (email,))

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def get_delivery_stats(driver_ids):

        if not driver_ids:
            return {}

        placeholders = ", ".join(["%s"] * len(driver_ids))

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        COUNT(*) AS manifests_total,
                        COALESCE(SUM(status = 'Delivered'), 0) AS manifests_delivered,
                        COALESCE(SUM(status = 'Rejected'), 0) AS manifests_rejected,
                        COALESCE(SUM(status IN ('Assigned', 'Pickup Started', 'In Transit')), 0) AS manifests_pending
                    FROM `tabCH Transfer Manifest`
                    WHERE driver IN ({placeholders})
                    AND docstatus < 2
                """, driver_ids)

                stats = cursor.fetchone()

                cursor.execute(f"""
                    SELECT COUNT(DISTINCT tmi.stock_entry) AS orders_delivered
                    FROM `tabCH Transfer Manifest Item` tmi
                    JOIN `tabCH Transfer Manifest` tm ON tm.name = tmi.parent
                    WHERE tm.driver IN ({placeholders})
                    AND tm.status = 'Delivered'
                    AND tm.docstatus < 2
                """, driver_ids)

                stats.update(cursor.fetchone())

                return {k: int(v) for k, v in stats.items()}

        finally:
            conn.close()
