"""
Local Edge SQLite Database Manager for Project Indradhanu.
Manages immediate local storage on the Raspberry Pi with transactional queuing.
"""

import os
import sqlite3
from datetime import datetime
from edge.config import DB_PATH

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_edge.sql")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_edge_db():
    """Initializes the local SQLite tables and seeds local cached contacts."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
        
    cursor = conn.cursor()
    # Seed default local contacts if empty
    cursor.execute("SELECT COUNT(*) as cnt FROM local_contacts")
    if cursor.fetchone()["cnt"] == 0:
        default_contacts = [
            ("Sanjay Deshmukh (Ranger)", "+919823045612", "Rampur", "forest_ranger"),
            ("Ramesh Patil (Sarpanch)", "+919422188901", "Rampur", "sarpanch"),
            ("Sunita Gawande", "+919765411234", "Rampur", "villager"),
            ("Ganesh Tekam", "+919970066543", "Shivpuri", "villager")
        ]
        cursor.executemany(
            "INSERT INTO local_contacts (full_name, phone_number, village_name, role) VALUES (?, ?, ?, ?)",
            default_contacts
        )
        conn.commit()
    conn.close()

def log_local_detection(node_code, species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path):
    """Saves detection immediately to local SQLite."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO local_detections 
        (node_code, species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path, detected_at, is_synced_to_hq)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 0)
        """,
        (node_code, species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path)
    )
    det_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return det_id

def queue_sms_alert(detection_id, phone, name, message):
    """Adds an SMS to the local offline fallback queue."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alert_fallback_queue 
        (detection_id, recipient_phone, recipient_name, alert_message, status)
        VALUES (?, ?, ?, ?, 'QUEUED_OFFLINE')
        """,
        (detection_id, phone, name, message)
    )
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return alert_id

def get_pending_sms_alerts():
    """Retrieves all unsent SMS alerts in the fallback queue."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM alert_fallback_queue WHERE status = 'QUEUED_OFFLINE' ORDER BY id ASC"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def mark_sms_delivered(alert_id):
    """Marks an alert as successfully delivered via GSM/SMS."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE alert_fallback_queue SET status = 'SENT', sent_at = CURRENT_TIMESTAMP WHERE id = ?",
        (alert_id,)
    )
    conn.commit()
    conn.close()

def get_unsynced_detections(limit=20):
    """Gets all detections that have not yet been synced to Central HQ."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM local_detections WHERE is_synced_to_hq = 0 ORDER BY id ASC LIMIT ?",
        (limit,)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def mark_detection_synced(det_id):
    """Marks a local detection as successfully synchronized with Central HQ."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE local_detections SET is_synced_to_hq = 1, synced_at = CURRENT_TIMESTAMP WHERE id = ?",
        (det_id,)
    )
    conn.commit()
    conn.close()

def get_local_contacts():
    """Gets active contacts for immediate alert broadcast."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM local_contacts WHERE is_active = 1")
    contacts = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return contacts

def log_edge_event(event_type, details):
    """Logs system event to local SQLite."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO edge_logs (event_type, details) VALUES (?, ?)", (event_type, details))
    conn.commit()
    conn.close()
