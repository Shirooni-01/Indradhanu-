-- =========================================================================
-- PROJECT INDRADHANU (PROJECT C) - LOCAL EDGE SQLITE SCHEMA
-- Deployed on Raspberry Pi 4 Edge Unit
-- =========================================================================

-- 1. Local detections table
CREATE TABLE IF NOT EXISTS local_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL,
    species TEXT NOT NULL,
    scientific_name TEXT,
    confidence REAL NOT NULL,
    threat_level TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    distance_meters INTEGER,
    rotator_heading INTEGER,
    image_snapshot_path TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_synced_to_hq INTEGER DEFAULT 0,
    synced_at TIMESTAMP
);

-- 2. Offline SMS fallback alert queue
-- Guarantees ZERO alert loss if GSM signal drops or network is blackout
CREATE TABLE IF NOT EXISTS alert_fallback_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER,
    recipient_phone TEXT NOT NULL,
    recipient_name TEXT,
    alert_message TEXT NOT NULL,
    status TEXT DEFAULT 'QUEUED_OFFLINE',   -- 'QUEUED_OFFLINE', 'SENT', 'FAILED'
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    FOREIGN KEY (detection_id) REFERENCES local_detections(id)
);

-- 3. Local cached emergency contacts (Villagers & Forest Rangers)
CREATE TABLE IF NOT EXISTS local_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone_number TEXT NOT NULL UNIQUE,
    village_name TEXT NOT NULL,
    role TEXT DEFAULT 'villager',
    is_active INTEGER DEFAULT 1
);

-- 4. Edge system logs (PIR triggers, AI inference times, battery stats)
CREATE TABLE IF NOT EXISTS edge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,               -- 'PIR_WAKE', 'AI_INFERENCE', 'SMS_DISPATCH', 'SYNC_SUCCESS', 'SYNC_FAIL'
    details TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
