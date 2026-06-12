from app.db.session import get_connection


class DriverProfileRepository:

    @staticmethod
    def get_driver(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        d.name AS driver_id,
                        d.full_name,
                        d.status,
                        d.employee,
                        d.user,

                        u.first_name,
                        u.last_name,
                        u.username,
                        u.email,
                        u.mobile_no,
                        u.enabled,

                        d.license_number,
                        d.issuing_date,
                        d.expiry_date,
                        d.custom_partner_type,
                        d.custom_courier_partner,
                        d.custom_default_vehicle,
                        d.custom_rating,
                        d.custom_total_deliveries

                    FROM tabDriver d
                    INNER JOIN tabUser u
                        ON d.user = u.email

                    WHERE d.user = %s
                """, (email,))

                return cursor.fetchone()

        finally:
            conn.close()