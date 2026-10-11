-- =========================================================================
-- PROJECT INDRADHANU - CENTRAL POSTGRESQL SCHEMA
-- Edge Detection + Central Verification + Siren Controller Architecture
-- =========================================================================

-- 1. Registered Forest Edge Camera Nodes
CREATE TABLE IF NOT EXISTS camera_nodes (
    id SERIAL PRIMARY KEY,
    node_code VARCHAR(32) NOT NULL UNIQUE,
    node_name VARCHAR(128) NOT NULL,
    sector VARCHAR(128) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    camera_type VARCHAR(128) DEFAULT 'Raspberry Pi Optical/IR Camera',
    has_rotator INTEGER DEFAULT 0,
    rotator_heading INTEGER DEFAULT 0,
    battery_pct INTEGER DEFAULT 100,
    status VARCHAR(32) DEFAULT 'OFFLINE',
    api_key VARCHAR(128),
    ip_address VARCHAR(64),
    firmware_version VARCHAR(32) DEFAULT '2.0.0-edge',
    pending_queue_count INTEGER DEFAULT 0,
    last_sync_at TIMESTAMP,
    last_heartbeat TIMESTAMP
);

-- 2. Verified & Unverified Wildlife Detection Events from Edge Devices
CREATE TABLE IF NOT EXISTS detections (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL UNIQUE,
    node_code VARCHAR(32) NOT NULL DEFAULT 'NODE-01',
    species VARCHAR(64) NOT NULL,
    scientific_name VARCHAR(128),
    confidence DOUBLE PRECISION NOT NULL,
    edge_species VARCHAR(64) NOT NULL,
    edge_confidence DOUBLE PRECISION NOT NULL,
    verified_species VARCHAR(64),
    verified_confidence DOUBLE PRECISION,
    verification_status VARCHAR(32) DEFAULT 'PENDING',
    verification_model VARCHAR(64),
    verification_notes TEXT,
    verified_at TIMESTAMP,
    threat_level VARCHAR(32) DEFAULT 'CRITICAL',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    distance_meters INTEGER,
    rotator_heading INTEGER,
    bbox_json TEXT,
    image_snapshot_path TEXT,
    siren_status VARCHAR(32) DEFAULT 'NOT_TRIGGERED',
    is_synced_delayed INTEGER DEFAULT 0,
    detected_at TIMESTAMP NOT NULL,
    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_detections_node_detected ON detections(node_code, detected_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_detections_event_id ON detections(event_id);

-- 3. Siren Controller Activation Audit & Acknowledgement Ledger
CREATE TABLE IF NOT EXISTS siren_alerts (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL UNIQUE,
    detection_id INTEGER REFERENCES detections(id) ON DELETE SET NULL,
    node_code VARCHAR(32) NOT NULL,
    species VARCHAR(64) NOT NULL,
    verified_confidence DOUBLE PRECISION NOT NULL,
    policy_decision VARCHAR(64) NOT NULL,
    siren_mode VARCHAR(32) NOT NULL,
    command_status VARCHAR(32) NOT NULL,
    physical_siren_active INTEGER DEFAULT 0,
    controller_url TEXT,
    ack_payload TEXT,
    error_message TEXT,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_siren_alerts_triggered ON siren_alerts(triggered_at DESC);

-- 4. Registered Villagers and Forest Department Contacts
CREATE TABLE IF NOT EXISTS villager_contacts (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(128) NOT NULL,
    phone_number VARCHAR(32) NOT NULL UNIQUE,
    village_name VARCHAR(128) NOT NULL,
    role VARCHAR(32) DEFAULT 'villager',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Central Telemetry & Audit Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Offline Fallback SMS Alert Queue with Retry State Tracking
CREATE TABLE IF NOT EXISTS alert_fallback_queue (
    id SERIAL PRIMARY KEY,
    detection_id INTEGER REFERENCES detections(id) ON DELETE SET NULL,
    recipient_phone VARCHAR(32) NOT NULL,
    recipient_name VARCHAR(128),
    alert_message TEXT NOT NULL,
    status VARCHAR(32) DEFAULT 'QUEUED_OFFLINE',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dispatched_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alert_queue_status_retry ON alert_fallback_queue(status, next_retry_at);
