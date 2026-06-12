from app.db.session import get_connection

conn = get_connection()

try:
    with conn.cursor() as cursor:

        cursor.execute("""
            SELECT
                name,
                email,
                full_name
            FROM tabUser
            WHERE email='deliverypatner@gmail.com'
        """)

        print(cursor.fetchone())

finally:
    conn.close()
