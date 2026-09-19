"""
Database manager for Project Indradhanu.
Handles SQLite operations, detections logging, contact registry, and offline queue.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "indradhanu.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    
    # Seed initial contacts if empty
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM villager_contacts")
    if cursor.fetchone()["cnt"] == 0:
        seed_contacts = [
            ("Sanjay Deshmukh", "+919823045612", "Rampur", "forest_ranger"),
            ("Ramesh Patil (Sarpanch)", "+919422188901", "Rampur", "sarpanch"),
            ("Sunita Gawande", "+919765411234", "Rampur", "villager"),
            ("Ganesh Tekam", "+919970066543", "Shivpuri", "villager"),
            ("Vikram Shinde", "+919158833219", "Borpada", "forest_ranger")
        ]
        cursor.executemany(
            "INSERT INTO villager_contacts (full_name, phone_number, village_name, role) VALUES (?, ?, ?, ?)",
            seed_contacts
        )
        conn.commit()

    # Seed initial camera nodes if empty
    cursor.execute("SELECT COUNT(*) as cnt FROM camera_nodes")
    if cursor.fetchone()["cnt"] == 0:
        seed_nodes = [
            ("NODE-01", "Tadoba North Perimeter Tower", "Sector 1 (Rampur Buffer)", 21.1458, 79.0882, "Thermal IR (MLX90640)", 1, 145, 88, "ONLINE_ACTIVE"),
            ("NODE-02", "Rampur East Buffer Tower", "Sector 1 (Rampur Buffer)", 21.1410, 79.0940, "Thermal IR + Night Vision", 1, 210, 94, "STANDBY"),
            ("NODE-03", "Shivpuri West Fringe Tower", "Sector 2 (Shivpuri Fringe)", 21.1495, 79.0790, "Thermal IR (Seek Compact)", 1, 90, 79, "STANDBY")
        ]
        cursor.executemany(
            """
            INSERT INTO camera_nodes 
            (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed_nodes
        )
        conn.commit()

    # Seed initial detections if empty
    cursor.execute("SELECT COUNT(*) as cnt FROM detections")
    if cursor.fetchone()["cnt"] == 0:
        seed_detections = [
            ("Tiger", "Panthera tigris", 94.8, "CRITICAL", 21.1441, 79.0865, 280, 145, "/static/snapshots/tiger_sample.jpg"),
            ("Leopard", "Panthera pardus", 91.2, "CRITICAL", 21.1468, 79.0845, 390, 145, "/static/snapshots/leopard_sample.jpg"),
            ("Indian Sloth Bear", "Melursus ursinus", 88.5, "HIGH", 21.1478, 79.0910, 450, 145, "/static/snapshots/bear_sample.jpg"),
            ("Lion", "Panthera leo persica", 93.1, "CRITICAL", 21.1415, 79.0895, 320, 145, "/static/snapshots/lion_sample.jpg")
        ]
        cursor.executemany(
            """
            INSERT INTO detections 
            (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed_detections
        )
        conn.commit()
    conn.close()

def log_detection(species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO detections 
        (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path)
    )
    det_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return det_id

def queue_offline_alert(detection_id, phone, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alert_fallback_queue (detection_id, recipient_phone, alert_message, status)
        VALUES (?, ?, ?, 'QUEUED_OFFLINE')
        """,
        (detection_id, phone, message)
    )
    conn.commit()
    conn.close()

def flush_offline_queue():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alert_fallback_queue WHERE status = 'QUEUED_OFFLINE'")
    pending = cursor.fetchall()
    
    cursor.execute(
        "UPDATE alert_fallback_queue SET status = 'DELIVERED', dispatched_at = CURRENT_TIMESTAMP WHERE status = 'QUEUED_OFFLINE'"
    )
    conn.commit()
    conn.close()
    return len(pending)

def get_recent_detections(limit=20):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM detections ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_contacts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM villager_contacts WHERE is_active = 1 ORDER BY id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_camera_nodes():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM camera_nodes ORDER BY id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def register_camera_node(node_code, node_name, sector, lat, lon, camera_type="Thermal IR (MLX90640)"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO camera_nodes 
        (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
        VALUES (?, ?, ?, ?, ?, ?, 1, 0, 100, 'ONLINE_ACTIVE')
        """,
        (node_code, node_name, sector, lat, lon, camera_type)
    )
    node_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return node_id

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
