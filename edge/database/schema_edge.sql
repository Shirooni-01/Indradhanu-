-- =========================================================================
-- PROJECT INDRADHANU - LOCAL EDGE SQLITE SCHEMA
-- Deployed on Raspberry Pi 3 Model B+ Edge Unit (Raspberry Pi OS Lite)
-- =========================================================================

-- 1. Local detections buffer table with unique event_id & retry state
CREATE TABLE IF NOT EXISTS local_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    node_code TEXT NOT NULL,
    species TEXT NOT NULL,
    scientific_name TEXT,
    confidence REAL NOT NULL,
    threat_level TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    distance_meters INTEGER,
    rotator_heading INTEGER,
    bbox_json TEXT,
    image_snapshot_path TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_synced_to_hq INTEGER DEFAULT 0,
    sync_status TEXT DEFAULT 'PENDING',
    sync_attempts INTEGER DEFAULT 0,
    next_sync_retry_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync_error TEXT,
    synced_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_local_detections_event_id ON local_detections(event_id);
CREATE INDEX IF NOT EXISTS idx_local_detections_sync ON local_detections(is_synced_to_hq, next_sync_retry_at);

-- 2. Offline SMS fallback alert queue
CREATE TABLE IF NOT EXISTS alert_fallback_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER,
    recipient_phone TEXT NOT NULL,
    recipient_name TEXT,
    alert_message TEXT NOT NULL,
    status TEXT DEFAULT 'QUEUED_OFFLINE',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    FOREIGN KEY (detection_id) REFERENCES local_detections(id)
);

CREATE INDEX IF NOT EXISTS idx_edge_alert_queue ON alert_fallback_queue(status, next_retry_at);

-- 3. Local cached emergency contacts (Villagers & Forest Rangers)
CREATE TABLE IF NOT EXISTS local_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone_number TEXT NOT NULL UNIQUE,
    village_name TEXT NOT NULL,
    role TEXT DEFAULT 'villager',
    is_active INTEGER DEFAULT 1
);

-- 4. Edge system logs (PIR triggers, AI inference times, sync & battery stats)
CREATE TABLE IF NOT EXISTS edge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
