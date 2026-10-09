from app.db.session import get_connection

USER_COLUMNS = """
    u.name,
    u.email,
    u.full_name,
    u.mobile_no,
    u.enabled,
    u.user_type
"""


class AuthRepository:

    @staticmethod
    def get_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT {USER_COLUMNS}
                    FROM tabUser u
                    WHERE u.email = %s
                """, (email,))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def get_user_with_password(email):
        """User record plus its password hash from Frappe's __Auth table."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT {USER_COLUMNS},
                        a.password
                    FROM tabUser u
                    INNER JOIN `__Auth` a
                        ON a.name = u.name
                    WHERE u.email = %s
                    AND a.doctype = 'User'
                    AND a.fieldname = 'password'
                """, (email,))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def get_user_roles(user_name):
        """Roles assigned to the user (Frappe `Has Role` child table)."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT role
                    FROM `tabHas Role`
                    WHERE parent = %s
                    AND parenttype = 'User'
                    ORDER BY idx
                """, (user_name,))

                return [row["role"] for row in cursor.fetchall()]

        finally:
            conn.close()

    @staticmethod
    def is_driver(user_name):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name
                    FROM tabDriver
                    WHERE user = %s
                    LIMIT 1
                """, (user_name,))

                return cursor.fetchone() is not None

        finally:
            conn.close()

    @staticmethod
    def get_driver_ids_for_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name
                    FROM tabDriver
                    WHERE user = %s
                    ORDER BY creation
                """, (email,))

                return [row["name"] for row in cursor.fetchall()]

        finally:
            conn.close()

    @staticmethod
    def deactivate_devices(user_name):
        """Stop push notifications for the user's registered app devices."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    UPDATE `tabCH Driver Device`
                    SET is_active = 0,
                        modified = NOW(6),
                        modified_by = %s
                    WHERE user = %s
                    AND is_active = 1
                """, (user_name, user_name))

                conn.commit()

                return cursor.rowcount

        except Exception:
            conn.rollback()
            return 0

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # OTP log (tabCH OTP Log)
    # ------------------------------------------------------------------

    @staticmethod
    def get_latest_otp(email, purpose):
        """Most recent OTP row for this email + purpose, regardless of status."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name,
                        otp_code,
                        status,
                        attempts,
                        generated_at,
                        expires_at
                    FROM `tabCH OTP Log`
                    WHERE email = %s
                    AND purpose = %s
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (email, purpose))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def create_otp(email, otp_hash, purpose, expires_minutes, ip_address=None):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # Supersede any still-pending OTP for this email
                cursor.execute("""
                    UPDATE `tabCH OTP Log`
                    SET status = 'Expired', modified = NOW(6)
                    WHERE email = %s
                    AND purpose = %s
                    AND status = 'Pending'
                """, (email, purpose))

                cursor.execute("""
                    SELECT COALESCE(MAX(otp_id), 0) + 1 AS next_id
                    FROM `tabCH OTP Log`
                """)
                otp_id = cursor.fetchone()["next_id"]
                name = f"CHOTP-{otp_id:05d}"

                cursor.execute("""
                    INSERT INTO `tabCH OTP Log`
                    (
                        name, creation, modified, modified_by, owner,
                        docstatus, idx, naming_series, otp_id,
                        email, otp_code, purpose, status, attempts,
                        generated_by, ip_address,
                        generated_at, expires_at
                    )
                    VALUES
                    (
                        %s, NOW(6), NOW(6), 'Administrator', 'Administrator',
                        0, 0, 'CHOTP-.#####', %s,
                        %s, %s, %s, 'Pending', 0,
                        %s, %s,
                        NOW(6), DATE_ADD(NOW(6), INTERVAL %s MINUTE)
                    )
                """, (name, otp_id, email, otp_hash, purpose, email, ip_address, expires_minutes))

                conn.commit()

                return name

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    @staticmethod
    def record_otp_attempt(name, verified):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                if verified:
                    cursor.execute("""
                        UPDATE `tabCH OTP Log`
                        SET attempts = attempts + 1,
                            status = 'Verified',
                            verified_at = NOW(6),
                            modified = NOW(6)
                        WHERE name = %s
                    """, (name,))
                else:
                    cursor.execute("""
                        UPDATE `tabCH OTP Log`
                        SET attempts = attempts + 1,
                            modified = NOW(6)
                        WHERE name = %s
                    """, (name,))

                conn.commit()

        finally:
            conn.close()

    @staticmethod
    def expire_otp(name):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    UPDATE `tabCH OTP Log`
                    SET status = 'Expired', modified = NOW(6)
                    WHERE name = %s
                """, (name,))

                conn.commit()

        finally:
            conn.close()
