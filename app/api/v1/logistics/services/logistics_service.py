from ..repositories.logistics_repo import LogisticsRepository


class LogisticsService:

    @staticmethod
    def trip_dashboard_summary(driver_id, trip_date):

        return {
            "success": True,
            "data": LogisticsRepository.get_trip_dashboard_summary(
                driver_id,
                trip_date
            )
        }
    @staticmethod
    def trip_summary(driver_id, from_date, to_date):

        return {
        "success": True,
        "data": LogisticsRepository.get_trip_summary(
            driver_id,
            from_date,
            to_date
        )
    }
    @staticmethod
    def trip_details(trip_id):

        rows = LogisticsRepository.get_trip_details(trip_id)

        if not rows:
            return {
                "success": False,
                "message": "Trip Not Found"
            }

        first = rows[0]

        manifests = []
        manifest_ids = set()

        for row in rows:
            if row["manifest_id"] and row["manifest_id"] not in manifest_ids:

                manifests.append({
                    "manifest_id": row["manifest_id"],
                    "status": row["manifest_status"],
                    "source_store": row["source_store"],
                    "destination_store": row["destination_store"],
                    "total_items": row["total_items"],
                    "total_qty": row["total_qty"]
                })

                manifest_ids.add(row["manifest_id"])

        stops = []

        for row in rows:
            if row["sequence"] is not None:

                stop = {
                    "sequence": row["sequence"],
                    "warehouse": row["warehouse"],
                    "store": row["store"],
                    "stop_type": row["stop_type"]
                }

                if stop not in stops:
                    stops.append(stop)

        return {
            "success": True,
            "data": {

                "trip": {
                    "trip_id": first["trip_id"],
                    "trip_date": str(first["trip_date"]),
                    "status": first["trip_status"],
                    "route": first["route"],
                    "vehicle_number": first["vehicle_number"],
                    "total_shipments": first["total_shipments"]
                },

                "driver": {
                    "driver_id": first["driver"],
                    "driver_name": first["driver_name"],
                    "mobile_no": first["cell_number"],
                    "rating": first["custom_rating"],
                    "total_deliveries": first["custom_total_deliveries"]
                },

                "route": {
                    "route_name": first["route_name"],
                    "hub_warehouse": first["hub_warehouse"],
                    "estimated_distance_km": first["estimated_distance_km"],
                    "estimated_duration_min": first["estimated_duration_min"]
                },

                "stops": stops,

                "manifests": manifests
            }
        }

    @staticmethod
    def manifest_summary(driver_id, manifest_date):

         return {
        "success": True,
        "data": LogisticsRepository.get_manifest_summary(
            driver_id,
            manifest_date
        )
    }

    @staticmethod
    def manifest_details(manifest_id):

        rows = LogisticsRepository.get_manifest_details(
        manifest_id
    )

        if not rows:
         return {
            "success": False,
            "message": "Manifest Not Found"
        }

        first = rows[0]

        return {
        "success": True,
        "data": {
            "manifest": {
                "manifest_id": first["manifest_id"],
                "manifest_date": str(first["manifest_date"]),
                "status": first["manifest_status"],
                "source_store": first["source_store"],
                "destination_store": first["destination_store"],
                "driver_name": first["driver_name"],
                "vehicle_number": first["vehicle_number"],
                "total_items": first["total_items"],
                "total_qty": first["total_qty"]
            },
            "items": [
                {
                    "stock_entry": row["stock_entry"],
                    "material_request": row["material_request"],
                    "item_count": row["item_count"],
                    "qty": row["item_qty"],
                    "transfer_status": row["transfer_status"]
                }
                for row in rows
            ]
        }
    }