from app.db.session import get_connection


class LogoutRepository:

    @staticmethod
    def get_user(email):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name,
                        email,
                        enabled
                    FROM tabUser
                    WHERE email = %s
                    LIMIT 1
                """, (email,))

                return cursor.fetchone()

        finally:
            conn.close()