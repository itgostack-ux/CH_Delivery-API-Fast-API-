from ..repositories.manifest_repo import ManifestRepository


class ManifestService:

    @staticmethod
    def get_manifests(driver_id):

        rows = ManifestRepository.get_driver_manifests(
            driver_id
        )

        manifests = {}

        for row in rows:

            manifest_id = row["manifest_id"]

            if manifest_id not in manifests:

                manifests[manifest_id] = {
                    "manifest_id": row["manifest_id"],
                    "manifest_date": str(row["manifest_date"]),
                    "status": row["status"],
                    "source_store": row["source_store"],
                    "destination_store": row["destination_store"],
                    "vehicle_number": row["vehicle_number"] or "",
                    "driver": row["driver"],
                    "driver_name": row["driver_name"],
                    "trip": row["trip"] or "",
                    "priority": row["shipment_priority"],
                    "total_items": row["total_items"],
                    "total_qty": row["total_qty"],
                    "items": []
                }

            manifests[manifest_id]["items"].append({
                "stock_entry": row["stock_entry"],
                "material_request": row["material_request"] or "",
                "item_count": row["item_count"],
                "qty": row["item_qty"],
                "transfer_status": row["transfer_status"],
                "received_qty": row["custom_received_qty"],
                "shortage_qty": row["custom_shortage_qty"]
            })

        return {
            "success": True,
            "count": len(manifests),
            "data": list(manifests.values())
        }