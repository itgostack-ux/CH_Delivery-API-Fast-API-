import logging

import requests

from app.db.session import get_connection

logger = logging.getLogger(__name__)


class TripRepository:

    # ---------------------------------------------------------------------
    # READ: Today's Trip (header + stops + manifests)
    # ---------------------------------------------------------------------
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
                    AND t.status IN ('Assigned', 'Started')

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

                    WHERE parent = %s

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

                    WHERE trip = %s

                    ORDER BY creation
                """, (trip["trip_id"],))

                manifests = cursor.fetchall()

                return {
                    "trip": trip,
                    "stops": stops,
                    "manifests": manifests,
                }

        except Exception:
            logger.exception("get_today_trip failed (driver=%s)", driver_id)
            raise

        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # READ: Notifications
    # ---------------------------------------------------------------------
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

        except Exception:
            logger.exception("get_notifications failed (email=%s)", email)
            raise

        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # WRITE: Mark Notification Read
    # ---------------------------------------------------------------------
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
                    "message": "Notification marked as read",
                }

        except Exception as e:
            conn.rollback()
            logger.exception(
                "mark_notification_read failed (name=%s)", notification_name
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()
    @staticmethod
    def scan_pickup_qr(trip_id, driver_id, pickup_token, latitude, longitude):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # -----------------------------------------
                # Validate Trip
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        status
                    FROM `tabCH Logistics Trip`
                    WHERE
                        name=%s
                        AND driver=%s
                """, (trip_id, driver_id))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip not found or not assigned to this driver."
                    }

                if trip["status"] != "Assigned":
                    return {
                        "success": False,
                        "message": f"Trip status '{trip['status']}' is not allowed for Pickup QR scan."
                    }

                # -----------------------------------------
                # Get Driver User
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        user
                    FROM `tabDriver`
                    WHERE name=%s
                """, (driver_id,))

                driver = cursor.fetchone()

                if driver is None:
                    return {
                        "success": False,
                        "message": "Driver not found.",
                        "receivedDriverId": driver_id
                    }

                scanned_by = driver.get("user")

                if not scanned_by:
                    return {
                        "success": False,
                        "message": "User is not mapped to this Driver.",
                        "driver": driver
                    }

                # -----------------------------------------
                # Validate Pickup Stop
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        pickup_token,
                        pickup_scanned_at
                    FROM `tabCH Logistics Trip Stop`
                    WHERE
                        parent=%s
                        AND stop_type='Pickup'
                        AND pickup_token=%s
                    LIMIT 1
                """, (
                    trip_id,
                    pickup_token
                ))

                stop = cursor.fetchone()

                if not stop:
                    return {
                        "success": False,
                        "message": "Invalid Pickup QR."
                    }

                if stop["pickup_scanned_at"]:
                    return {
                        "success": False,
                        "message": "Pickup QR has already been scanned."
                    }

                # -----------------------------------------
                # Update Pickup Scan
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip Stop`
                    SET
                        pickup_scanned_at = NOW(),
                        pickup_scanned_by = %s,
                        gps_lat = %s,
                        gps_lng = %s,
                        ata = NOW(),
                        modified = NOW()
                    WHERE
                        name=%s
                """, (
                    scanned_by,
                    latitude,
                    longitude,
                    stop["name"]
                ))

                conn.commit()

                return {
                    "success": True,
                    "message": "Pickup QR scanned successfully.",
                    "tripId": trip_id,
                    "driverId": driver_id,
                    "pickupStopId": stop["name"],
                    "pickupVerified": True
                }

        except Exception as e:
            conn.rollback()

            return {
                "success": False,
                "message": str(e)
            }

        finally:
            conn.close()


    # ---------------------------------------------------------------------
    # READ: Accept Trip Details (validate + pickup stop + manifests)
    # ---------------------------------------------------------------------
    @staticmethod
    def get_accept_trip_details(trip_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # -----------------------------------------
                # Validate Trip
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name AS trip_id,
                        status,
                        driver,
                        driver_name,
                        vehicle,
                        vehicle_number,
                        route
                    FROM `tabCH Logistics Trip`
                    WHERE name = %s
                """, (trip_id,))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip not found.",
                    }

                if trip["status"] not in ("Assigned", "Accepted"):
                    return {
                        "success": False,
                        "message": f"Trip cannot be opened because status is '{trip['status']}'.",
                    }

                # -----------------------------------------
                # Pickup Stop
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name AS stop_id,
                        warehouse,
                        status,
                        pickup_token,
                        pickup_scanned_at,
                        pickup_scanned_by
                    FROM `tabCH Logistics Trip Stop`
                    WHERE
                        parent = %s
                        AND stop_type = 'Pickup'
                    LIMIT 1
                """, (trip_id,))

                pickup_stop = cursor.fetchone()

                # -----------------------------------------
                # Manifests
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name AS manifest_id,
                        status AS manifest_status,
                        pickup_photo,
                        total_items,
                        total_qty
                    FROM `tabCH Transfer Manifest`
                    WHERE trip = %s
                    ORDER BY creation
                """, (trip_id,))

                manifests = cursor.fetchall()

                return {
                    "success": True,
                    "trip": trip,
                    "pickupStop": pickup_stop,
                    "manifests": manifests,
                }

        except Exception as e:
            logger.exception(
                "get_accept_trip_details failed (trip=%s)", trip_id
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()


    # ---------------------------------------------------------------------
    # WRITE: Upload Pickup Photo
    # ---------------------------------------------------------------------
    @staticmethod
    def upload_pickup_photo(
        manifest_id,
        photo,
        latitude,
        longitude,
        notes,
    ):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # Validate Manifest
                cursor.execute("""
                    SELECT
                        name,
                        status
                    FROM `tabCH Transfer Manifest`
                    WHERE name = %s
                """, (manifest_id,))

                manifest = cursor.fetchone()

                if not manifest:
                    return {
                        "success": False,
                        "message": "Manifest not found.",
                    }

                # Update Pickup Photo
                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET
                        pickup_photo = %s,
                        pickup_datetime = NOW(),
                        pickup_lat = %s,
                        pickup_lng = %s,
                        pickup_notes = %s
                    WHERE
                        name = %s
                """, (
                    photo,
                    latitude,
                    longitude,
                    notes,
                    manifest_id,
                ))

                conn.commit()

                return {
                    "success": True,
                    "message": "Pickup photo uploaded successfully.",
                }

        except Exception as e:
            conn.rollback()
            logger.exception(
                "upload_pickup_photo failed (manifest=%s)", manifest_id
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # WRITE: Confirm Delivery
    # ---------------------------------------------------------------------
    @staticmethod
    def confirm_delivery(
        trip_id,
        manifest_id,
        driver_id,
        delivery_token,
        otp,
        receiver_name,
        delivery_photo,
        notes,
        latitude,
        longitude,
    ):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # ----------------------------------
                # Validate Trip
                # ----------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        status
                    FROM `tabCH Logistics Trip`
                    WHERE
                        name = %s
                        AND driver = %s
                """, (trip_id, driver_id))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip not found.",
                    }

                if trip["status"] != "Started":
                    return {
                        "success": False,
                        "message": "Trip is not in Started status.",
                    }

                # ----------------------------------
                # Validate Manifest
                # ----------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        status,
                        delivery_otp
                    FROM `tabCH Transfer Manifest`
                    WHERE
                        name = %s
                        AND trip = %s
                """, (manifest_id, trip_id))

                manifest = cursor.fetchone()

                if not manifest:
                    return {
                        "success": False,
                        "message": "Manifest not found.",
                    }

                if manifest["status"] != "In Transit":
                    return {
                        "success": False,
                        "message": "Manifest is not in transit.",
                    }

                # ----------------------------------
                # Validate Delivery QR
                # ----------------------------------
                cursor.execute("""
                    SELECT
                        name
                    FROM `tabCH Logistics Trip Stop`
                    WHERE
                        parent = %s
                        AND stop_type = 'Drop'
                        AND delivery_token = %s
                """, (trip_id, delivery_token))

                stop = cursor.fetchone()

                if not stop:
                    return {
                        "success": False,
                        "message": "Invalid Delivery QR.",
                    }

                # ----------------------------------
                # Validate OTP
                # ----------------------------------
                if str(manifest["delivery_otp"]) != str(otp):
                    return {
                        "success": False,
                        "message": "Invalid OTP.",
                    }

                # ----------------------------------
                # Validate Photo
                # ----------------------------------
                if not delivery_photo:
                    return {
                        "success": False,
                        "message": "Delivery photo is required.",
                    }

                # ----------------------------------
                # Validate Receiver
                # ----------------------------------
                if not receiver_name:
                    return {
                        "success": False,
                        "message": "Receiver name is required.",
                    }

                # ----------------------------------
                # Update Drop Stop
                # ----------------------------------
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip Stop`
                    SET
                        status = 'Completed',
                        ata = NOW(),
                        gps_lat = %s,
                        gps_lng = %s,
                        delivery_scanned_at = NOW(),
                        delivery_scanned_by = %s
                    WHERE
                        name = %s
                """, (
                    latitude,
                    longitude,
                    driver_id,
                    stop["name"],
                ))

                # ----------------------------------
                # Update Manifest
                # ----------------------------------
                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET
                        status = 'Delivered',
                        delivery_photo = %s,
                        delivery_datetime = NOW(),
                        delivery_lat = %s,
                        delivery_lng = %s,
                        receiver_name = %s,
                        delivery_otp_verified = 1,
                        received_by = %s,
                        received_datetime = NOW(),
                        notes = %s
                    WHERE
                        name = %s
                """, (
                    delivery_photo,
                    latitude,
                    longitude,
                    receiver_name,
                    receiver_name,
                    notes,
                    manifest_id,
                ))

                # ----------------------------------
                # Update Manifest Items
                # ----------------------------------
                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest Item`
                    SET
                        transfer_status = 'Delivered'
                    WHERE
                        parent = %s
                """, (manifest_id,))

                # ----------------------------------
                # Check Pending Manifests
                # ----------------------------------
                cursor.execute("""
                    SELECT COUNT(*) AS pending
                    FROM `tabCH Transfer Manifest`
                    WHERE
                        trip = %s
                        AND status != 'Delivered'
                """, (trip_id,))

                pending = cursor.fetchone()

                trip_status = "Started"

                if pending["pending"] == 0:

                    cursor.execute("""
                        UPDATE `tabCH Logistics Trip`
                        SET
                            status = 'Completed',
                            actual_end = NOW()
                        WHERE
                            name = %s
                    """, (trip_id,))

                    trip_status = "Completed"

                conn.commit()

                return {
                    "success": True,
                    "message": "Delivery completed successfully.",
                    "tripStatus": trip_status,
                    "manifestStatus": "Delivered",
                }

        except Exception as e:
            conn.rollback()
            logger.exception(
                "confirm_delivery failed (trip=%s, manifest=%s)",
                trip_id,
                manifest_id,
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # EXTERNAL: Request Delivery OTP (ERPNext HTTP endpoint, no DB)
    # ---------------------------------------------------------------------
    @staticmethod
    def request_delivery_otp(manifest_id):

        try:

            ERP_URL = "https://delivery.gogizmo.co"

            response = requests.post(
                f"{ERP_URL}/api/method/ch_logistics.api.transfer_manifest_api.request_delivery_otp",
                data={
                    "manifest": manifest_id,
                },
                timeout=30,

                # If authentication is required, add the appropriate headers or cookies.
                # Example:
                # headers={"Authorization": "token api_key:api_secret"}
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "message": "Unable to contact ERPNext.",
                }

            result = response.json().get("message")

            return {
                "success": True,
                "message": result.get("message"),
                "maskedEmails": result.get("masked_emails", []),
                "maskedMobiles": result.get("masked_mobiles", []),
                "emailCount": result.get("email_count", 0),
                "smsCount": result.get("sms_count", 0),
            }

        except Exception as e:
            logger.exception(
                "request_delivery_otp failed (manifest=%s)", manifest_id
            )
            return {
                "success": False,
                "message": str(e),
            }

    # ---------------------------------------------------------------------
    # WRITE: Accept Trip
    # ---------------------------------------------------------------------
    @staticmethod
    def accept_trip(trip_id, driver_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # -----------------------------------------
                # Validate Trip
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        status,
                        driver,
                        route,
                        vehicle,
                        vehicle_number,
                        planned_start,
                        planned_end
                    FROM `tabCH Logistics Trip`
                    WHERE
                        name = %s
                        AND driver = %s
                """, (trip_id, driver_id))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip not found or not assigned to this driver.",
                    }

                # -----------------------------------------
                # Status Validation
                # -----------------------------------------
                if trip["status"] == "Accepted":
                    return {
                        "success": False,
                        "message": "Trip already accepted.",
                    }

                if trip["status"] == "Started":
                    return {
                        "success": False,
                        "message": "Trip already started.",
                    }

                if trip["status"] == "Completed":
                    return {
                        "success": False,
                        "message": "Trip already completed.",
                    }

                if trip["status"] == "Closed":
                    return {
                        "success": False,
                        "message": "Trip already closed.",
                    }

                if trip["status"] != "Assigned":
                    return {
                        "success": False,
                        "message": f"Invalid Trip Status : {trip['status']}",
                    }

                # -----------------------------------------
                # Accept Trip
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip`
                    SET
                        status = 'Accepted',
                        modified = NOW()
                    WHERE
                        name = %s
                """, (trip_id,))

                conn.commit()

                return {
                    "success": True,
                    "message": "Trip accepted successfully.",
                    "tripId": trip_id,
                    "tripStatus": "Accepted",
                    "driverId": driver_id,
                    "route": trip["route"],
                    "vehicle": trip["vehicle"],
                    "vehicleNumber": trip["vehicle_number"],
                    "plannedStart": trip["planned_start"],
                    "plannedEnd": trip["planned_end"],
                }

        except Exception as e:
            conn.rollback()
            logger.exception(
                "accept_trip failed (trip=%s, driver=%s)", trip_id, driver_id
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # WRITE: Confirm Start Trip
    # ---------------------------------------------------------------------
    @staticmethod
    def confirm_start_trip(
        trip_id,
        driver_id,
        latitude,
        longitude,
    ):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # -----------------------------------------
                # Validate Trip
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        status
                    FROM `tabCH Logistics Trip`
                    WHERE
                        name = %s
                        AND driver = %s
                """, (trip_id, driver_id))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip not found or not assigned to this driver.",
                    }

                if trip["status"] == "Started":
                    return {
                        "success": False,
                        "message": "Trip has already been started.",
                    }

                if trip["status"] == "Completed":
                    return {
                        "success": False,
                        "message": "Trip has already been completed.",
                    }

                if trip["status"] == "Closed":
                    return {
                        "success": False,
                        "message": "Trip has already been closed.",
                    }

                if trip["status"] != "Assigned":
                    return {
                        "success": False,
                        "message": f"Trip cannot be started because status is '{trip['status']}'.",
                    }

                # -----------------------------------------
                # Validate Pickup Stop
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        pickup_scanned_at
                    FROM `tabCH Logistics Trip Stop`
                    WHERE
                        parent = %s
                        AND stop_type = 'Pickup'
                    LIMIT 1
                """, (trip_id,))

                stop = cursor.fetchone()

                if not stop:
                    return {
                        "success": False,
                        "message": "Pickup stop not found.",
                    }

                if not stop["pickup_scanned_at"]:
                    return {
                        "success": False,
                        "message": "Please scan the Pickup QR before starting the trip.",
                    }

                # -----------------------------------------
                # Validate Pickup Photo
                # -----------------------------------------
                cursor.execute("""
                    SELECT COUNT(*) AS cnt
                    FROM `tabCH Transfer Manifest`
                    WHERE
                        trip = %s
                        AND (
                            pickup_photo IS NULL
                            OR pickup_photo = ''
                        )
                """, (trip_id,))

                photo = cursor.fetchone()

                if photo["cnt"] > 0:
                    return {
                        "success": False,
                        "message": "Please upload the pickup photo before starting the trip.",
                    }

                # -----------------------------------------
                # Complete Pickup Stop
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip Stop`
                    SET
                        status = 'Completed',
                        ata = NOW(),
                        gps_lat = %s,
                        gps_lng = %s,
                        modified = NOW()
                    WHERE
                        name = %s
                """, (
                    latitude,
                    longitude,
                    stop["name"],
                ))

                # -----------------------------------------
                # Start Trip
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip`
                    SET
                        status = 'Started',
                        actual_start = NOW(),
                        modified = NOW()
                    WHERE
                        name = %s
                """, (trip_id,))

                # -----------------------------------------
                # Update Manifest
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET
                        status = 'In Transit',
                        modified = NOW()
                    WHERE
                        trip = %s
                """, (trip_id,))

                # -----------------------------------------
                # Update Manifest Items
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest Item`
                    SET
                        transfer_status = 'Picked Up',
                        modified = NOW()
                    WHERE
                        parent IN (
                            SELECT name
                            FROM `tabCH Transfer Manifest`
                            WHERE trip = %s
                        )
                """, (trip_id,))

                conn.commit()

                return {
                    "success": True,
                    "message": "Trip started successfully.",
                    "tripId": trip_id,
                    "driverId": driver_id,
                    "tripStatus": "Started",
                    "manifestStatus": "In Transit",
                }

        except Exception as e:
            conn.rollback()
            logger.exception(
                "confirm_start_trip failed (trip=%s, driver=%s)",
                trip_id,
                driver_id,
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # WRITE: Reject Trip
    # ---------------------------------------------------------------------
    @staticmethod
    def reject_trip(
        trip_id,
        driver_id,
        reason,
        remarks,
    ):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # -----------------------------------------
                # Validate Trip
                # -----------------------------------------
                cursor.execute("""
                    SELECT
                        name,
                        status,
                        driver
                    FROM `tabCH Logistics Trip`
                    WHERE
                        name = %s
                        AND driver = %s
                """, (trip_id, driver_id))

                trip = cursor.fetchone()

                if not trip:
                    return {
                        "success": False,
                        "message": "Trip not found or not assigned to this driver.",
                    }

                # -----------------------------------------
                # Status Validation
                # -----------------------------------------
                if trip["status"] == "Started":
                    return {
                        "success": False,
                        "message": "Started trip cannot be rejected.",
                    }

                if trip["status"] == "Completed":
                    return {
                        "success": False,
                        "message": "Completed trip cannot be rejected.",
                    }

                if trip["status"] == "Closed":
                    return {
                        "success": False,
                        "message": "Closed trip cannot be rejected.",
                    }

                if trip["status"] == "Rejected":
                    return {
                        "success": False,
                        "message": "Trip already rejected.",
                    }

                if trip["status"] != "Assigned":
                    return {
                        "success": False,
                        "message": f"Invalid Trip Status : {trip['status']}",
                    }

                # -----------------------------------------
                # Reject Trip
                # -----------------------------------------
                cursor.execute("""
                    UPDATE `tabCH Logistics Trip`
                    SET
                        status = 'Rejected',
                        cancellation_reason = %s,
                        cancelled_by = %s,
                        cancelled_on = NOW(),
                        notes = %s,
                        modified = NOW()
                    WHERE
                        name = %s
                """, (
                    reason,
                    driver_id,
                    remarks,
                    trip_id,
                ))

                conn.commit()

                return {
                    "success": True,
                    "message": "Trip rejected successfully.",
                    "tripId": trip_id,
                    "tripStatus": "Rejected",
                }

        except Exception as e:
            conn.rollback()
            logger.exception(
                "reject_trip failed (trip=%s, driver=%s)", trip_id, driver_id
            )
            return {
                "success": False,
                "message": str(e),
            }

        finally:
            conn.close()
