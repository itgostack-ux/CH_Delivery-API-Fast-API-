from app.db.session import get_connection
import uuid


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

    @staticmethod
    def register_device(
        driver,
        driver_name,
        user,
        platform,
        app_version,
        device_id,
        fcm_token
    ):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # Check by Driver OR Device
                cursor.execute("""
                    SELECT
                        name,
                        driver,
                        device_id
                    FROM `tabCH Driver Device`
                    WHERE driver=%s
                       OR device_id=%s
                    LIMIT 1
                """, (driver, device_id))

                existing = cursor.fetchone()

                # Existing record found
                if existing:

                    # Device belongs to another driver
                    if existing["driver"] != driver and existing["device_id"] == device_id:

                        return {
                            "success": False,
                            "message": "Device already registered with another driver."
                        }

                    # Same driver -> Update everything
                    cursor.execute("""
                        UPDATE `tabCH Driver Device`
                        SET
                            driver_name=%s,
                            user=%s,
                            platform=%s,
                            app_version=%s,
                            device_id=%s,
                            fcm_token=%s,
                            is_active=1,
                            last_seen=NOW(),
                            modified=NOW(),
                            modified_by='Administrator'
                        WHERE driver=%s
                    """, (
                        driver_name,
                        user,
                        platform,
                        app_version,
                        device_id,
                        fcm_token,
                        driver
                    ))

                    conn.commit()

                    return {
                        "success": True,
                        "message": "Device Updated"
                    }

                # Insert New Device
                name = str(uuid.uuid4())

                cursor.execute("""
                    INSERT INTO `tabCH Driver Device`
                    (
                        name,
                        owner,
                        creation,
                        modified,
                        modified_by,
                        docstatus,
                        idx,
                        driver,
                        driver_name,
                        user,
                        platform,
                        app_version,
                        is_active,
                        device_id,
                        fcm_token,
                        registered_on,
                        last_seen
                    )
                    VALUES
                    (
                        %s,
                        'Administrator',
                        NOW(),
                        NOW(),
                        'Administrator',
                        0,
                        0,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        1,
                        %s,
                        %s,
                        NOW(),
                        NOW()
                    )
                """, (
                    name,
                    driver,
                    driver_name,
                    user,
                    platform,
                    app_version,
                    device_id,
                    fcm_token
                ))

                conn.commit()

                return {
                    "success": True,
                    "message": "Device Registered"
                }

        except Exception as e:

            conn.rollback()

            return {
                "success": False,
                "message": str(e)
            }

        finally:
            conn.close()