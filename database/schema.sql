-- =========================================================================
-- PROJECT INDRADHANU (PROJECT C) - SQLITE DATABASE SCHEMA
-- =========================================================================

-- 1. Table for all confirmed wildlife detections
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    species TEXT NOT NULL,                  -- 'Tiger', 'Leopard', 'Lion', 'Indian Sloth Bear'
    scientific_name TEXT,
    confidence REAL NOT NULL,               -- e.g. 94.8 (%)
    threat_level TEXT DEFAULT 'CRITICAL',   -- 'CRITICAL', 'HIGH', 'WARNING'
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    distance_meters INTEGER,               -- Distance to nearest village boundary
    rotator_heading INTEGER,                -- Compass angle in degrees (0-360)
    image_snapshot_path TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Table for Registered Villagers and Forest Department Contacts
CREATE TABLE IF NOT EXISTS villager_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone_number TEXT NOT NULL UNIQUE,
    village_name TEXT NOT NULL,             -- 'Rampur', 'Shivpuri', 'Borpada'
    role TEXT DEFAULT 'villager',           -- 'villager', 'sarpanch', 'forest_ranger'
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Table for Offline Fallback Alert Queue
-- If network/GSM is offline, alerts sit here until network restores!
CREATE TABLE IF NOT EXISTS alert_fallback_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER NOT NULL,
    recipient_phone TEXT NOT NULL,
    alert_message TEXT NOT NULL,
    status TEXT DEFAULT 'QUEUED_OFFLINE',   -- 'QUEUED_OFFLINE', 'DELIVERED', 'FAILED'
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dispatched_at TIMESTAMP,
    FOREIGN KEY (detection_id) REFERENCES detections(id)
);

-- 4. Table for System Telemetry Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,               -- 'PIR_WAKE', 'AI_DETECTION', 'OFFLINE_FALLBACK', 'SYNC_FLUSH'
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Table for Edge Camera Nodes (Multi-Camera Station Network)
CREATE TABLE IF NOT EXISTS camera_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL UNIQUE,         -- e.g. 'NODE-01', 'NODE-02'
    node_name TEXT NOT NULL,                -- e.g. 'Tadoba North Perimeter Tower'
    sector TEXT NOT NULL,                   -- e.g. 'Sector 1 (Rampur Buffer)'
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    camera_type TEXT DEFAULT 'Thermal IR (MLX90640/Seek)',
    has_rotator INTEGER DEFAULT 1,
    rotator_heading INTEGER DEFAULT 145,
    battery_pct INTEGER DEFAULT 88,
    status TEXT DEFAULT 'ONLINE_ACTIVE',    -- 'ONLINE_ACTIVE', 'STANDBY', 'OFFLINE'
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
