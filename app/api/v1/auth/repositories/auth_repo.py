from app.db.session import get_connection


class AuthRepository:

    @staticmethod
    def get_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        u.name,
                        u.email,
                        u.full_name,
                        u.mobile_no,
                        u.enabled,
                        a.password
                    FROM tabUser u
                    INNER JOIN __Auth a
                        ON a.name = u.name
                    WHERE u.email = %s
                    AND u.enabled = 1
                    AND a.doctype = 'User'
                    AND a.fieldname = 'password'
                """, (email,))

                return cursor.fetchone()

        except Exception as e:
            print("DB ERROR:", str(e))
            return None

        finally:
            conn.close()