import secrets

from app.db.session import get_connection


def _frappe_id():
    """10-char random id, same shape Frappe uses for child/comment rows."""
    return secrets.token_hex(5)


class ManifestRepository:

    @staticmethod
    def get_driver_ids_for_user(email):
        """All Driver records linked to this user (ERPNext allows several)."""

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
    def resolve_manifest_id(any_id):
        """Accept a manifest id, a shipment id (Stock Entry, GFTNMT...) or a
        delivery challan id (GFTNDC...) - the ids the ERPNext dialogs show -
        and return the manifest name, or None."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT tm.name
                    FROM `tabCH Transfer Manifest` tm
                    WHERE tm.name = %s
                    UNION
                    SELECT tmi.parent
                    FROM `tabCH Transfer Manifest Item` tmi
                    LEFT JOIN `tabStock Entry` se ON se.name = tmi.stock_entry
                    WHERE tmi.stock_entry = %s
                    OR se.custom_delivery_challan = %s
                    LIMIT 1
                """, (any_id, any_id, any_id))

                row = cursor.fetchone()
                return row["name"] if row else None

        finally:
            conn.close()

    @staticmethod
    def get_pending_for_drivers(driver_ids):
        """Shipments assigned to any of the driver IDs that are still waiting for
        "Accept & Pick Up" / "Reject Pickup" - one row per shipment, like ERPNext."""

        if not driver_ids:
            return []

        placeholders = ", ".join(["%s"] * len(driver_ids))

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(f"""
                    SELECT
                        tm.name AS manifest_id,
                        tmi.stock_entry AS shipment_id,
                        se.custom_delivery_challan AS delivery_challan,
                        tm.manifest_date,
                        tm.status,
                        tmi.transfer_status,
                        se.custom_logistics_status AS logistics_status,
                        tm.trip,
                        tm.stop_sequence,
                        tm.source_store,
                        tm.destination_store,
                        COALESCE(tmi.from_warehouse, tm.source_warehouse) AS from_warehouse,
                        COALESCE(tmi.to_warehouse, tm.destination_warehouse) AS to_warehouse,
                        tm.shipment_priority AS priority,
                        COALESCE(tmi.item_count, tm.total_items, 0) AS total_items,
                        COALESCE(tmi.total_qty, tm.total_qty, 0) AS total_qty,
                        tm.box_count,
                        tm.estimated_delivery_date
                    FROM `tabCH Transfer Manifest` tm
                    LEFT JOIN `tabCH Transfer Manifest Item` tmi ON tmi.parent = tm.name
                    LEFT JOIN `tabStock Entry` se ON se.name = tmi.stock_entry
                    WHERE tm.driver IN ({placeholders})
                    AND tm.status = 'Assigned'
                    AND tm.docstatus < 2
                    ORDER BY tm.manifest_date, tm.stop_sequence, tm.creation, tmi.idx
                """, driver_ids)

                return cursor.fetchall()

        finally:
            conn.close()

    @staticmethod
    def get_manifest(manifest_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        name AS manifest_id,
                        status,
                        driver,
                        trip,
                        driver_accepted_at,
                        rejected_at,
                        rejection_reason,
                        docstatus
                    FROM `tabCH Transfer Manifest`
                    WHERE name = %s
                """, (manifest_id,))

                return cursor.fetchone()

        finally:
            conn.close()

    @staticmethod
    def get_reject_reasons():
        """Options of the ERPNext Select field, so the app stays in sync."""

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT options
                    FROM `tabCustom Field`
                    WHERE dt = 'CH Transfer Manifest'
                    AND fieldname = 'rejection_reason'
                """)

                row = cursor.fetchone()

                if not row or not row["options"]:
                    return []

                return [o.strip() for o in row["options"].split("\n") if o.strip()]

        finally:
            conn.close()

    @staticmethod
    def reject(manifest_id, user_email, reason, notes, photo_url=None, commit=True):
        """Mirror ERPNext's "Reject Pickup" action, in one transaction:

        1. manifest -> Rejected with reason/notes/photo/by/at
        2. each shipment (Stock Entry) in the manifest -> Rejected / Reverted,
           pending qty moved to rejected qty, scanned serials cleared
        3. timeline comment "Stock returned to source (...)" on each shipment

        Steps 2-3 are what ERPNext's dispatch screen reads for its Rejected tab.
        """

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    UPDATE `tabCH Transfer Manifest`
                    SET
                        status = 'Rejected',
                        rejection_reason = %s,
                        rejection_notes = %s,
                        rejection_photo = COALESCE(%s, rejection_photo),
                        rejected_by = %s,
                        rejected_at = NOW(6),
                        rejected_during = 'Pickup',
                        modified = NOW(6),
                        modified_by = %s
                    WHERE name = %s
                    AND status = 'Assigned'
                """, (reason, notes, photo_url, user_email, user_email, manifest_id))

                if cursor.rowcount != 1:
                    conn.rollback()
                    return False

                cursor.execute("""
                    SELECT stock_entry
                    FROM `tabCH Transfer Manifest Item`
                    WHERE parent = %s
                    AND stock_entry IS NOT NULL
                """, (manifest_id,))

                stock_entries = [row["stock_entry"] for row in cursor.fetchall()]

                for stock_entry in stock_entries:

                    cursor.execute("""
                        UPDATE `tabStock Entry`
                        SET
                            custom_status = 'Rejected',
                            custom_status_since = NOW(6),
                            custom_logistics_status = 'Reverted',
                            custom_logistics_person = '',
                            custom_rejected_qty = COALESCE(custom_rejected_qty, 0)
                                                  + COALESCE(custom_pending_qty, 0),
                            custom_pending_qty = 0,
                            modified = NOW(6),
                            modified_by = %s
                        WHERE name = %s
                    """, (user_email, stock_entry))

                    cursor.execute("""
                        UPDATE `tabStock Entry Detail`
                        SET
                            custom_receive_qty = 0,
                            custom_scanned_serials = '',
                            custom_final_scanned_serials = '',
                            modified = NOW(6),
                            modified_by = %s
                        WHERE parent = %s
                        AND parenttype = 'Stock Entry'
                    """, (user_email, stock_entry))

                    cursor.execute("""
                        INSERT INTO tabComment
                        (
                            name, creation, modified, modified_by, owner,
                            docstatus, idx, comment_type, comment_email,
                            reference_doctype, reference_name, content,
                            published, seen
                        )
                        VALUES
                        (
                            %s, NOW(6), NOW(6), %s, %s,
                            0, 0, 'Comment', %s,
                            'Stock Entry', %s, %s,
                            0, 0
                        )
                    """, (
                        _frappe_id(), user_email, user_email, user_email,
                        stock_entry,
                        f"Stock returned to source ({manifest_id}). Reason: {reason}",
                    ))

                if commit:
                    conn.commit()
                else:
                    conn.rollback()      # dry run

                return True

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()
