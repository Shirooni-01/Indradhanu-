-- =========================================================================
-- PROJECT INDRADHANU - CENTRAL SQLITE FALLBACK SCHEMA
-- Mirrors schema_postgres.sql for local development / testing fallback
-- =========================================================================

-- 1. Registered Forest Edge Camera Nodes
CREATE TABLE IF NOT EXISTS camera_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL UNIQUE,
    node_name TEXT NOT NULL,
    sector TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    camera_type TEXT DEFAULT 'Raspberry Pi Optical/IR Camera',
    has_rotator INTEGER DEFAULT 0,
    rotator_heading INTEGER DEFAULT 0,
    battery_pct INTEGER DEFAULT 100,
    status TEXT DEFAULT 'OFFLINE',
    api_key TEXT,
    ip_address TEXT,
    firmware_version TEXT DEFAULT '2.0.0-edge',
    pending_queue_count INTEGER DEFAULT 0,
    last_sync_at TIMESTAMP,
    last_heartbeat TIMESTAMP
);

-- 2. Verified & Unverified Wildlife Detection Events from Edge Devices
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    node_code TEXT NOT NULL DEFAULT 'NODE-01',
    species TEXT NOT NULL,
    scientific_name TEXT,
    confidence REAL NOT NULL,
    edge_species TEXT NOT NULL,
    edge_confidence REAL NOT NULL,
    verified_species TEXT,
    verified_confidence REAL,
    verification_status TEXT DEFAULT 'PENDING',
    verification_model TEXT,
    verification_notes TEXT,
    verified_at TIMESTAMP,
    threat_level TEXT DEFAULT 'CRITICAL',
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    distance_meters INTEGER,
    rotator_heading INTEGER,
    bbox_json TEXT,
    image_snapshot_path TEXT,
    siren_status TEXT DEFAULT 'NOT_TRIGGERED',
    is_synced_delayed INTEGER DEFAULT 0,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_detections_node_detected ON detections(node_code, detected_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_detections_event_id ON detections(event_id);

-- 3. Siren Controller Activation Audit & Acknowledgement Ledger
CREATE TABLE IF NOT EXISTS siren_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    detection_id INTEGER,
    node_code TEXT NOT NULL,
    species TEXT NOT NULL,
    verified_confidence REAL NOT NULL,
    policy_decision TEXT NOT NULL,
    siren_mode TEXT NOT NULL,
    command_status TEXT NOT NULL,
    physical_siren_active INTEGER DEFAULT 0,
    controller_url TEXT,
    ack_payload TEXT,
    error_message TEXT,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    FOREIGN KEY (detection_id) REFERENCES detections(id)
);

CREATE INDEX IF NOT EXISTS idx_siren_alerts_triggered ON siren_alerts(triggered_at DESC);

-- 4. Registered Villagers and Forest Department Contacts
CREATE TABLE IF NOT EXISTS villager_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone_number TEXT NOT NULL UNIQUE,
    village_name TEXT NOT NULL,
    role TEXT DEFAULT 'villager',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Central Telemetry & Audit Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Offline Fallback SMS Alert Queue with Retry State Tracking
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
    dispatched_at TIMESTAMP,
    FOREIGN KEY (detection_id) REFERENCES detections(id)
);

CREATE INDEX IF NOT EXISTS idx_alert_queue_status ON alert_fallback_queue(status, next_retry_at);
