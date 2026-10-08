import secrets
from datetime import datetime

from app.db.session import get_connection


def _frappe_id():
    return secrets.token_hex(5)


def _comment(cursor, doctype, docname, user_email, content):
    cursor.execute("""
        INSERT INTO tabComment
        (name, creation, modified, modified_by, owner, docstatus, idx,
         comment_type, comment_email, reference_doctype, reference_name,
         content, published, seen)
        VALUES (%s, NOW(6), NOW(6), %s, %s, 0, 0,
                'Comment', %s, %s, %s, %s, 0, 0)
    """, (_frappe_id(), user_email, user_email, user_email, doctype, docname, content))


def _driver_location(cursor, driver_id, trip, event_type, lat, lng, accuracy, user_email):
    if lat is None or lng is None:
        return
    cursor.execute("""
        INSERT INTO `tabCH Driver Location`
        (name, creation, modified, modified_by, owner, docstatus, idx,
         driver, captured_at, event_type, trip, latitude, longitude, accuracy_m, source)
        VALUES (%s, NOW(6), NOW(6), %s, %s, 0, 0,
                %s, NOW(6), %s, %s, %s, %s, %s, 'Driver App')
    """, (_frappe_id(), user_email, user_email, driver_id, event_type, trip, lat, lng, accuracy))


class DeliveryRepository:

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    def get_manifest(manifest_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name AS manifest_id, status, docstatus, driver, driver_name, trip,
                        source_warehouse, source_store, destination_warehouse, destination_store,
                        stop_sequence, qr_payload, tracking_token, driver_accepted_at,
                        pickup_datetime, delivery_datetime,
                        delivery_otp, delivery_otp_log, delivery_otp_expires_at,
                        delivery_otp_attempts, delivery_otp_verified, receiver_name,
                        total_items, total_qty
                    FROM `tabCH Transfer Manifest`
                    WHERE name = %s
                """, (manifest_id,))

                manifest = cursor.fetchone()

                if manifest:
                    cursor.execute("""
                        SELECT stock_entry, from_warehouse, to_warehouse
                        FROM `tabCH Transfer Manifest Item`
                        WHERE parent = %s
                        ORDER BY idx
                    """, (manifest_id,))
                    manifest["items"] = cursor.fetchall()

                return manifest

        finally:
            conn.close()

    @staticmethod
    def get_receivers(store):
        """Users scoped to the destination store (who can sign for a delivery)."""

        if not store:
            return []

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT DISTINCT
                        u.name AS email,
                        u.full_name,
                        u.first_name,
                        u.mobile_no,
                        s.is_home_store
                    FROM `tabCH User Scope Store` s
                    JOIN `tabCH User Scope` sc ON sc.name = s.parent AND sc.enabled = 1
                    JOIN tabUser u ON u.name = sc.user AND u.enabled = 1
                    WHERE s.store = %s
                    ORDER BY s.is_home_store DESC, u.full_name
                """, (store,))

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def get_otp_log(name):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT name, manifest, status, otp_digest, expires_at,
                           attempts, max_attempts
                    FROM `tabCH Logistics OTP Log`
                    WHERE name = %s
                """, (name,))

                return cursor.fetchone()

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Pickup
    # ------------------------------------------------------------------

    @staticmethod
    def pickup(manifest, user_email, qr, photo_url, lat, lng, accuracy, commit=True):
        """Mirror ERPNext "Accept & Pick Up" in one transaction."""

        mid, trip = manifest["manifest_id"], manifest["trip"]
        stock_entries = [i["stock_entry"] for i in manifest["items"] if i["stock_entry"]]

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET status = 'In Transit',
                        driver_accepted_at = COALESCE(driver_accepted_at, NOW(6)),
                        pickup_photo = COALESCE(%s, pickup_photo),
                        pickup_datetime = NOW(6),
                        pickup_lat = %s,
                        pickup_lng = %s,
                        modified = NOW(6),
                        modified_by = %s
                    WHERE name = %s
                    AND status = 'Assigned'
                """, (photo_url, lat or 0, lng or 0, user_email, mid))

                if cursor.rowcount != 1:
                    conn.rollback()
                    return False

                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest Item`
                    SET driver_accepted_at = COALESCE(driver_accepted_at, NOW(6)),
                        pickup_photo = COALESCE(%s, pickup_photo),
                        pickup_scanned_qr = %s,
                        pickup_lat = %s,
                        pickup_lng = %s,
                        pickup_gps_accuracy_m = %s,
                        pickup_captured_at = NOW(6),
                        transfer_status = 'Picked Up',
                        modified = NOW(6),
                        modified_by = %s
                    WHERE parent = %s
                """, (photo_url, qr, lat or 0, lng or 0, accuracy or 0, user_email, mid))

                for se in stock_entries:
                    cursor.execute("""
                        UPDATE `tabStock Entry`
                        SET custom_logistics_status = 'In Transit',
                            custom_logistics_person = %s,
                            custom_pickup_datetime = NOW(6),
                            modified = NOW(6),
                            modified_by = %s
                        WHERE name = %s
                    """, (user_email, user_email, se))

                    _comment(cursor, "CH Transfer Manifest", mid, user_email,
                             f"Stock Entry {se} accepted (pickup captured) by driver {user_email}.")

                trip_started = False

                if trip:
                    cursor.execute("""
                        UPDATE `tabCH Logistics Trip`
                        SET status = 'Started',
                            actual_start = NOW(6),
                            modified = NOW(6),
                            modified_by = %s
                        WHERE name = %s
                        AND status IN ('Assigned', 'Accepted')
                    """, (user_email, trip))

                    trip_started = cursor.rowcount == 1

                    if trip_started:
                        first = stock_entries[0] if stock_entries else mid
                        _comment(cursor, "CH Logistics Trip", trip, user_email,
                                 f"Trip auto-started: first shipment ({first}) accepted by {user_email}.")

                _driver_location(cursor, manifest["driver"], trip, "Pickup", lat, lng, accuracy, user_email)

                if commit:
                    conn.commit()
                else:
                    conn.rollback()

                return {"trip_started": trip_started}

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Delivery OTP
    # ------------------------------------------------------------------

    @staticmethod
    def create_delivery_otp(manifest, user_email, digest, expires_minutes, masked_email, ip_address, commit=True):

        mid = manifest["manifest_id"]

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # Supersede a previous pending OTP for this manifest
                cursor.execute("""
                    UPDATE `tabCH Logistics OTP Log`
                    SET status = 'Expired', modified = NOW(6)
                    WHERE manifest = %s AND status = 'Pending'
                """, (mid,))

                year = datetime.now().year
                cursor.execute("""
                    SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(name, '-', -1) AS UNSIGNED)), 0) + 1 AS n
                    FROM `tabCH Logistics OTP Log`
                    WHERE name LIKE %s
                """, (f"LOT-{year}-%",))
                log_name = f"LOT-{year}-{int(cursor.fetchone()['n']):05d}"

                cursor.execute("""
                    INSERT INTO `tabCH Logistics OTP Log`
                    (name, creation, modified, modified_by, owner, docstatus, idx,
                     manifest, trip, stop_sequence, request_source, status, otp_digest,
                     generated_at, expires_at, generated_by, attempts, max_attempts,
                     dispatch_status, sent_at, email_count, sms_count, in_app_count,
                     masked_emails, request_ip)
                    VALUES (%s, NOW(6), NOW(6), %s, %s, 0, 0,
                            %s, %s, %s, 'Driver App', 'Pending', %s,
                            NOW(6), DATE_ADD(NOW(6), INTERVAL %s MINUTE), %s, 0, 5,
                            'Sent', NOW(6), 1, 0, 1,
                            %s, %s)
                """, (log_name, user_email, user_email,
                      mid, manifest["trip"], manifest["stop_sequence"] or 0, digest,
                      expires_minutes, user_email, masked_email, ip_address))

                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET delivery_otp = %s,
                        delivery_otp_log = %s,
                        delivery_otp_generated_at = NOW(6),
                        delivery_otp_expires_at = DATE_ADD(NOW(6), INTERVAL %s MINUTE),
                        delivery_otp_sent_at = NOW(6),
                        delivery_otp_attempts = 0,
                        delivery_otp_verified = 0,
                        modified = NOW(6),
                        modified_by = %s
                    WHERE name = %s
                """, (digest[:28], log_name, expires_minutes, user_email, mid))

                if commit:
                    conn.commit()
                else:
                    conn.rollback()

                return log_name

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    @staticmethod
    def record_otp_attempt(log_name, manifest_id, user_email, verified, failure_reason=None):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                if verified:
                    cursor.execute("""
                        UPDATE `tabCH Logistics OTP Log`
                        SET attempts = attempts + 1, last_attempt_at = NOW(6),
                            status = 'Verified', verified_at = NOW(6), verified_by = %s,
                            modified = NOW(6), modified_by = %s
                        WHERE name = %s
                    """, (user_email, user_email, log_name))
                else:
                    cursor.execute("""
                        UPDATE `tabCH Logistics OTP Log`
                        SET attempts = attempts + 1, last_attempt_at = NOW(6),
                            failure_reason = %s,
                            status = IF(attempts + 1 >= max_attempts, 'Failed', status),
                            modified = NOW(6), modified_by = %s
                        WHERE name = %s
                    """, (failure_reason, user_email, log_name))

                    cursor.execute("""
                        UPDATE `tabCH Transfer Manifest`
                        SET delivery_otp_attempts = COALESCE(delivery_otp_attempts, 0) + 1
                        WHERE name = %s
                    """, (manifest_id,))

                conn.commit()

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Deliver
    # ------------------------------------------------------------------

    @staticmethod
    def deliver(manifest, user_email, qr, photo_url, receiver_name, lat, lng, accuracy, commit=True):
        """Mirror ERPNext "Confirm & Deliver" in one transaction."""

        mid, trip = manifest["manifest_id"], manifest["trip"]
        stock_entries = [i["stock_entry"] for i in manifest["items"] if i["stock_entry"]]

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET status = 'Delivered',
                        delivery_photo = COALESCE(%s, delivery_photo),
                        delivery_datetime = NOW(6),
                        delivery_lat = %s,
                        delivery_lng = %s,
                        arrival_datetime = NOW(6),
                        arrival_lat = %s,
                        arrival_lng = %s,
                        receiver_name = %s,
                        received_by = %s,
                        received_datetime = NOW(6),
                        delivery_otp = NULL,
                        delivery_otp_verified = 1,
                        delivery_otp_verified_at = NOW(6),
                        delivery_otp_verified_by = %s,
                        modified = NOW(6),
                        modified_by = %s
                    WHERE name = %s
                    AND status = 'In Transit'
                """, (photo_url, lat or 0, lng or 0, lat or 0, lng or 0,
                      receiver_name, receiver_name, user_email, user_email, mid))

                if cursor.rowcount != 1:
                    conn.rollback()
                    return False

                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest Item`
                    SET delivery_photo = COALESCE(%s, delivery_photo),
                        delivery_scanned_qr = %s,
                        delivery_receiver_name = %s,
                        delivery_lat = %s,
                        delivery_lng = %s,
                        delivery_gps_accuracy_m = %s,
                        delivery_captured_at = NOW(6),
                        transfer_status = 'Delivered',
                        modified = NOW(6),
                        modified_by = %s
                    WHERE parent = %s
                """, (photo_url, qr, receiver_name, lat or 0, lng or 0, accuracy or 0, user_email, mid))

                for se in stock_entries:
                    cursor.execute("""
                        UPDATE `tabStock Entry`
                        SET custom_status = 'Ready For Receive',
                            custom_status_since = NOW(6),
                            custom_logistics_status = 'Delivered',
                            custom_delivery_datetime = NOW(6),
                            modified = NOW(6),
                            modified_by = %s
                        WHERE name = %s
                    """, (user_email, se))

                    _comment(cursor, "CH Transfer Manifest", mid, user_email,
                             f"Stock Entry {se} delivered (evidence captured) by driver {user_email}.")

                trip_closed = False

                if trip:
                    # Drop stop for this destination -> Completed
                    cursor.execute("""
                        UPDATE `tabCH Logistics Trip Stop`
                        SET status = 'Completed',
                            ata = COALESCE(ata, NOW(6)),
                            delivery_scanned_at = NOW(6),
                            delivery_scanned_by = %s,
                            modified = NOW(6),
                            modified_by = %s
                        WHERE parent = %s
                        AND warehouse = %s
                        AND stop_type IN ('Drop', 'Pickup+Drop')
                    """, (user_email, user_email, trip, manifest["destination_warehouse"]))

                    # Close the trip when nothing is left in transit / assigned
                    cursor.execute("""
                        SELECT COUNT(*) AS open_count
                        FROM `tabCH Transfer Manifest`
                        WHERE trip = %s
                        AND docstatus < 2
                        AND status IN ('Assigned', 'Pickup Started', 'In Transit')
                    """, (trip,))

                    if cursor.fetchone()["open_count"] == 0:
                        cursor.execute("""
                            UPDATE `tabCH Logistics Trip`
                            SET status = 'Closed',
                                actual_end = NOW(6),
                                total_duration_actual_min =
                                    TIMESTAMPDIFF(MINUTE, COALESCE(actual_start, NOW(6)), NOW(6)),
                                modified = NOW(6),
                                modified_by = %s
                            WHERE name = %s
                            AND status IN ('Started', 'Assigned', 'Accepted', 'Completed')
                        """, (user_email, trip))
                        trip_closed = cursor.rowcount == 1

                _driver_location(cursor, manifest["driver"], trip, "Delivery", lat, lng, accuracy, user_email)

                if commit:
                    conn.commit()
                else:
                    conn.rollback()

                return {"trip_closed": trip_closed}

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()
