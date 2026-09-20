-- =========================================================================
-- PROJECT INDRADHANU (PROJECT C) - CENTRAL POSTGRESQL SCHEMA
-- Section 4.2 & 5: Cloud / HQ Central Repository
-- Tracks 'detected_at' vs 'reported_at' to measure network sync latency
-- =========================================================================

-- 1. Table for Camera Tower Nodes across forest beats
CREATE TABLE IF NOT EXISTS camera_nodes (
    id SERIAL PRIMARY KEY,
    node_code VARCHAR(32) NOT NULL UNIQUE,
    node_name VARCHAR(128) NOT NULL,
    sector VARCHAR(128) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    camera_type VARCHAR(128) DEFAULT 'Thermal IR (MLX90640)',
    has_rotator INTEGER DEFAULT 1,
    rotator_heading INTEGER DEFAULT 145,
    battery_pct INTEGER DEFAULT 88,
    status VARCHAR(32) DEFAULT 'ONLINE_ACTIVE',
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Table for Wildlife Sightings with Network Sync Latency Tracking
CREATE TABLE IF NOT EXISTS detections (
    id SERIAL PRIMARY KEY,
    species VARCHAR(64) NOT NULL,              -- Bengal Tiger, Indian Leopard, Indian Sloth Bear, Asiatic Lion
    scientific_name VARCHAR(128),
    confidence DOUBLE PRECISION NOT NULL,       -- e.g. 94.8%
    threat_level VARCHAR(32) DEFAULT 'CRITICAL',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    distance_meters INTEGER,                   -- Distance to nearest village boundary
    rotator_heading INTEGER,
    image_snapshot_path TEXT,
    node_code VARCHAR(32) DEFAULT 'NODE-01',
    detected_at TIMESTAMP NOT NULL,            -- Exact forest time recorded on edge Pi
    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Time ingested at Central HQ (reported_at - detected_at = Latency)
);

CREATE INDEX IF NOT EXISTS idx_detections_node_detected ON detections(node_code, detected_at DESC);

-- 3. Table for Registered Villagers and Rangers
CREATE TABLE IF NOT EXISTS villager_contacts (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(128) NOT NULL,
    phone_number VARCHAR(32) NOT NULL UNIQUE,
    village_name VARCHAR(128) NOT NULL,
    role VARCHAR(32) DEFAULT 'villager',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Central Telemetry & Audit Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
