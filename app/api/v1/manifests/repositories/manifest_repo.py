from app.db.session import get_connection


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
        """Pickup Pending tab: shipments waiting for Accept & Pick Up / Reject Pickup."""

        return ManifestRepository.get_shipments_for_drivers(driver_ids, ("Assigned",))

    @staticmethod
    def get_shipments_for_drivers(driver_ids, statuses, days=None, limit=200):
        """One row per shipment (like the ERP driver app tabs) for the given
        manifest statuses; `days` limits by manifest_date for history tabs."""

        if not driver_ids or not statuses:
            return []

        placeholders = ", ".join(["%s"] * len(driver_ids))
        status_ph = ", ".join(["%s"] * len(statuses))
        params = list(driver_ids) + list(statuses)
        date_clause = ""

        if days:
            date_clause = "AND tm.manifest_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)"
            params.append(days)

        params.append(limit)

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
                        tm.estimated_delivery_date,
                        tm.driver_accepted_at,
                        tm.pickup_datetime,
                        tm.delivery_datetime,
                        tm.receiver_name,
                        (SELECT GROUP_CONCAT(p.package_label ORDER BY p.idx SEPARATOR ',')
                           FROM `tabCH Stock Entry Package` p
                           WHERE p.parent = tmi.stock_entry AND p.parenttype = 'Stock Entry') AS box_labels
                    FROM `tabCH Transfer Manifest` tm
                    LEFT JOIN `tabCH Transfer Manifest Item` tmi ON tmi.parent = tm.name
                    LEFT JOIN `tabStock Entry` se ON se.name = tmi.stock_entry
                    WHERE tm.driver IN ({placeholders})
                    AND tm.status IN ({status_ph})
                    AND tm.docstatus < 2
                    {date_clause}
                    ORDER BY tm.manifest_date DESC, tm.stop_sequence, tm.creation DESC, tmi.idx
                    LIMIT %s
                """, params)

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
    def get_stock_entries(manifest_id):

        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT stock_entry
                    FROM `tabCH Transfer Manifest Item`
                    WHERE parent = %s
                    AND stock_entry IS NOT NULL
                    ORDER BY idx
                """, (manifest_id,))

                return [row["stock_entry"] for row in cursor.fetchall()]

        finally:
            conn.close()
