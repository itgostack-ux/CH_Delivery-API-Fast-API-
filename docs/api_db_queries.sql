-- ============================================================================
-- CH Delivery API - "what does each API read from the database?"
-- Read-only queries, one block per endpoint. Run against gofixdb.
-- Set the email once; every block below uses it.
-- ============================================================================
SET @email := 'mahalakshmi@gostack.in';


-- ----------------------------------------------------------------------------
-- 1. POST /api/v1/auth/login
--    tabUser  +  __Auth (password hash)  +  tabHas Role  +  tabDriver
--    The API verifies the typed password against password_hash with
--    pbkdf2-sha256 in Python; SQL never sees the plain password.
-- ----------------------------------------------------------------------------
SELECT
    u.name        AS user_name,          -- token.sub
    u.full_name   AS token_name,         -- token.name
    u.enabled,                           -- 0 => 403 "User account is disabled"
    a.password    AS password_hash,      -- $pbkdf2-sha256$...
    GROUP_CONCAT(DISTINCT hr.role ORDER BY hr.idx SEPARATOR ', ') AS roles_in_has_role,
    IF(COUNT(d.name) > 0, 'yes', 'no')  AS driver_role_auto_granted,
    GROUP_CONCAT(DISTINCT d.name ORDER BY d.creation SEPARATOR ', ') AS driver_ids
FROM tabUser u
JOIN `__Auth` a         ON a.name = u.name AND a.doctype = 'User' AND a.fieldname = 'password'
LEFT JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
                           AND hr.role IN ('System Manager', 'Delivery Manager', 'Driver')
LEFT JOIN tabDriver d      ON d.user = u.name
WHERE u.email = @email
GROUP BY u.name, u.full_name, u.enabled, a.password;


-- ----------------------------------------------------------------------------
-- 2. POST /api/v1/auth/otp/request  and  /auth/otp/verify
--    tabCH OTP Log: one row per OTP, purpose 'App Login'.
--    otp_code holds sha256(email:otp), never the OTP itself.
--    Rules: valid 5 min, resend after 60 s, max 5 wrong attempts.
-- ----------------------------------------------------------------------------
SELECT name, email, purpose, status, attempts,
       generated_at, expires_at, verified_at, ip_address,
       TIMESTAMPDIFF(SECOND, generated_at, NOW(6)) AS age_seconds
FROM `tabCH OTP Log`
WHERE email = @email AND purpose = 'App Login'
ORDER BY generated_at DESC
LIMIT 5;


-- ----------------------------------------------------------------------------
-- 3. Token -> driver mapping (used by EVERY driver endpoint on every call)
--    tabDriver.user = token.sub ; the returned names are the manifest filter.
-- ----------------------------------------------------------------------------
SELECT name AS driver_id, full_name AS driver_name, status, availability_status,
       custom_default_vehicle, current_lat, current_lng, last_geo_at
FROM tabDriver
WHERE user = @email
ORDER BY creation;


-- ----------------------------------------------------------------------------
-- 4. GET /api/v1/profile/me  (driver block + stats)
-- ----------------------------------------------------------------------------
SELECT d.name AS driver_id, d.full_name, d.cell_number, d.availability_status,
       d.rating, d.total_deliveries,
       (SELECT COUNT(*) FROM `tabCH Transfer Manifest` m WHERE m.driver = d.name AND m.docstatus < 2) AS manifests_total,
       (SELECT COUNT(*) FROM `tabCH Transfer Manifest` m WHERE m.driver = d.name AND m.status = 'Delivered') AS manifests_delivered,
       (SELECT COUNT(*) FROM `tabCH Transfer Manifest` m WHERE m.driver = d.name AND m.status = 'Rejected')  AS manifests_rejected
FROM tabDriver d
WHERE d.user = @email;


-- ----------------------------------------------------------------------------
-- 5. GET /api/v1/dashboard/summary  -> overall.manifests
--    (today.* adds: trip_date = CURDATE() OR manifest_date = CURDATE()
--     OR DATE(delivery_datetime) = CURDATE() OR DATE(pickup_datetime) = CURDATE())
-- ----------------------------------------------------------------------------
SELECT tm.status, COUNT(*) AS n,
       COALESCE(SUM(tm.total_items), 0) AS items,
       COALESCE(SUM(tm.total_qty), 0)   AS qty
FROM `tabCH Transfer Manifest` tm
LEFT JOIN `tabCH Logistics Trip` tr ON tr.name = tm.trip
WHERE tm.docstatus < 2
  AND tm.driver IN (SELECT name FROM tabDriver WHERE user = @email)
GROUP BY tm.status;

-- dashboard -> overall.orders (stock entries carried by those manifests)
SELECT COALESCE(se.custom_logistics_status, tmi.transfer_status) AS status,
       COUNT(DISTINCT tmi.stock_entry) AS n,
       COALESCE(SUM(tmi.total_qty), 0) AS qty
FROM `tabCH Transfer Manifest Item` tmi
JOIN `tabCH Transfer Manifest` tm ON tm.name = tmi.parent
LEFT JOIN `tabStock Entry` se    ON se.name = tmi.stock_entry
WHERE tm.docstatus < 2
  AND tmi.stock_entry IS NOT NULL
  AND tm.driver IN (SELECT name FROM tabDriver WHERE user = @email)
GROUP BY 1;

-- dashboard -> overall.trips
SELECT status, COUNT(*) AS n
FROM `tabCH Logistics Trip`
WHERE docstatus < 2
  AND driver IN (SELECT name FROM tabDriver WHERE user = @email)
GROUP BY status;

-- dashboard -> today_manifests (active work + delivered today)
SELECT tm.name AS manifest_id, tm.status, tm.trip, tr.status AS trip_status, tr.trip_date,
       tm.source_store, tm.destination_store, tm.stop_sequence, tm.shipment_priority,
       tm.total_items, tm.total_qty, tm.pickup_datetime, tm.delivery_datetime
FROM `tabCH Transfer Manifest` tm
LEFT JOIN `tabCH Logistics Trip` tr ON tr.name = tm.trip
WHERE tm.docstatus < 2
  AND tm.driver IN (SELECT name FROM tabDriver WHERE user = @email)
  AND (tm.status IN ('Assigned', 'Pickup Started', 'In Transit')
       OR DATE(tm.delivery_datetime) = CURDATE())
ORDER BY FIELD(tm.status, 'In Transit', 'Pickup Started', 'Assigned', 'Delivered'),
         tr.trip_date DESC, tm.stop_sequence;


-- ----------------------------------------------------------------------------
-- 6. The three tabs: one row per SHIPMENT (manifest x stock entry)
--      GET /manifests/pending           -> status IN ('Assigned')
--      GET /manifests/delivery-pending  -> status IN ('In Transit', 'Pickup Started')
--      GET /manifests/delivered?days=30 -> status IN ('Delivered', ...) AND manifest_date >= 30 days
--    Change @statuses / @days to switch tab.
-- ----------------------------------------------------------------------------
SET @days := 30;

SELECT tm.name AS manifest_id,
       tmi.stock_entry AS shipment_id,            -- GFTNMT...
       se.custom_delivery_challan AS delivery_challan,   -- GFTNDC...
       tm.manifest_date, tm.status, tmi.transfer_status,
       se.custom_logistics_status AS logistics_status,
       tm.trip, tm.stop_sequence, tm.source_store, tm.destination_store,
       COALESCE(tmi.from_warehouse, tm.source_warehouse)     AS from_warehouse,
       COALESCE(tmi.to_warehouse,   tm.destination_warehouse) AS to_warehouse,
       COALESCE(tmi.item_count, tm.total_items, 0) AS total_items,
       COALESCE(tmi.total_qty,  tm.total_qty,  0)  AS total_qty,
       tm.box_count, tm.pickup_datetime, tm.delivery_datetime, tm.receiver_name,
       (SELECT GROUP_CONCAT(p.package_label ORDER BY p.idx SEPARATOR ',')
          FROM `tabCH Stock Entry Package` p
         WHERE p.parent = tmi.stock_entry AND p.parenttype = 'Stock Entry') AS box_labels  -- first one = qr
FROM `tabCH Transfer Manifest` tm
LEFT JOIN `tabCH Transfer Manifest Item` tmi ON tmi.parent = tm.name
LEFT JOIN `tabStock Entry` se ON se.name = tmi.stock_entry
WHERE tm.docstatus < 2
  AND tm.driver IN (SELECT name FROM tabDriver WHERE user = @email)
  AND tm.status IN ('Assigned', 'Pickup Started', 'In Transit')          -- pending + delivery-pending
  -- AND tm.status IN ('Delivered','Partially Received','Received','Closed')
  -- AND tm.manifest_date >= DATE_SUB(CURDATE(), INTERVAL @days DAY)       -- delivered tab only
ORDER BY tm.manifest_date DESC, tm.stop_sequence, tmi.idx;


-- ----------------------------------------------------------------------------
-- 7. GET /manifests/{id}/boxes   (box QR labels to scan; ERP method reads this)
-- ----------------------------------------------------------------------------
SET @manifest := 'GFMF26000009';

SELECT tmi.parent AS manifest_id, tmi.stock_entry AS shipment_id,
       p.idx AS box_no, p.package_label AS box_qr
FROM `tabCH Transfer Manifest Item` tmi
JOIN `tabCH Stock Entry Package` p ON p.parent = tmi.stock_entry AND p.parenttype = 'Stock Entry'
WHERE tmi.parent = @manifest
ORDER BY tmi.idx, p.idx;


-- ----------------------------------------------------------------------------
-- 8. {id} resolution: the app may send manifest id, shipment id or challan.
-- ----------------------------------------------------------------------------
SET @any_id := 'GFTNDC26000353';

SELECT tm.name AS manifest_id
FROM `tabCH Transfer Manifest` tm
LEFT JOIN `tabCH Transfer Manifest Item` tmi ON tmi.parent = tm.name
LEFT JOIN `tabStock Entry` se ON se.name = tmi.stock_entry
WHERE tm.name = @any_id OR tmi.stock_entry = @any_id OR se.custom_delivery_challan = @any_id
LIMIT 1;


-- ----------------------------------------------------------------------------
-- 9. GET /manifests/{id}/reached  and the 50 m check inside POST /deliver
--    Drop point = CH Store of destination_store. Distance computed in Python
--    (haversine); here it is computed in SQL for checking.
-- ----------------------------------------------------------------------------
SET @lat := 13.0843;  SET @lng := 80.2623;   -- driver's GPS

SELECT tm.name AS manifest_id, tm.destination_store,
       s.store_name, s.address,
       CAST(NULLIF(TRIM(s.custom_latitude),  '') AS DECIMAL(12,7)) AS store_lat,
       CAST(NULLIF(TRIM(s.custom_longitude), '') AS DECIMAL(12,7)) AS store_lng,
       ROUND(ST_Distance_Sphere(
             POINT(@lng, @lat),
             POINT(CAST(NULLIF(TRIM(s.custom_longitude), '') AS DECIMAL(12,7)),
                   CAST(NULLIF(TRIM(s.custom_latitude),  '') AS DECIMAL(12,7)))), 1) AS distance_m,
       50 AS limit_m
FROM `tabCH Transfer Manifest` tm
LEFT JOIN `tabCH Store` s ON s.name = tm.destination_store
WHERE tm.name = @manifest;


-- ----------------------------------------------------------------------------
-- 10. POST /manifests/{id}/delivery-otp   (ERP request_delivery_otp)
--     tabCH Logistics OTP Log + tabEmail Queue (did the mail really go out?)
-- ----------------------------------------------------------------------------
SELECT name, status, LEFT(error, 120) AS error, creation
FROM `tabEmail Queue`
WHERE reference_doctype = 'CH Transfer Manifest' AND reference_name = @manifest
ORDER BY creation DESC LIMIT 3;

SELECT *                               -- LOT-... rows; columns are ERP-defined
FROM `tabCH Logistics OTP Log`
WHERE manifest = @manifest
ORDER BY creation DESC LIMIT 3;


-- ----------------------------------------------------------------------------
-- 11. After POST /pickup, /deliver, /reject - what the ERP wrote
-- ----------------------------------------------------------------------------
SELECT name, status, driver, trip,
       driver_accepted_at, pickup_datetime, pickup_lat, pickup_lng,
       delivery_datetime, delivery_lat, delivery_lng, receiver_name,
       rejected_at, rejection_reason
FROM `tabCH Transfer Manifest`
WHERE name = @manifest;

-- per-shipment row (distance_km from actual_distance_km, delivery photo, GPS)
SELECT parent AS manifest_id, stock_entry, transfer_status,
       pickup_lat, pickup_lng, pickup_gps_accuracy_m,
       delivery_lat, delivery_lng, delivery_gps_accuracy_m, distance_km
FROM `tabCH Transfer Manifest Item`
WHERE parent = @manifest;

-- rejections feeding the ERP "Rejected" tab
SELECT *                               -- MR-... rows (reason, stage, photos, latitude, longitude)
FROM `tabCH Manifest Rejection`
WHERE manifest = @manifest
ORDER BY creation DESC;

-- photos uploaded by the API (attached to the manifest)
SELECT file_name, file_url, is_private, creation
FROM tabFile
WHERE attached_to_doctype = 'CH Transfer Manifest' AND attached_to_name = @manifest
ORDER BY creation DESC;


-- ----------------------------------------------------------------------------
-- 12. Driver status: GET /driver/status, POST /driver/break, /resume, /sign-out
--     and the device rows deactivated by /auth/logout
-- ----------------------------------------------------------------------------
SELECT name, full_name, availability_status, modified
FROM tabDriver WHERE user = @email;

SELECT name, user, fcm_token, is_active, modified
FROM `tabCH Driver Device`
WHERE user = @email;                   -- /auth/logout sets is_active = 0 here


-- ----------------------------------------------------------------------------
-- 13. GET /manifests/reject-reasons  (public: options of the ERP Select field)
-- ----------------------------------------------------------------------------
SELECT options
FROM `tabCustom Field`
WHERE dt = 'CH Transfer Manifest' AND fieldname = 'rejection_reason';
