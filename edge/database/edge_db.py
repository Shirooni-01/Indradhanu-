"""
Local Edge SQLite Database Manager for Project Indradhanu.
Manages immediate local storage on the Raspberry Pi with transactional queuing
and robust SMS retry engine with exponential backoff.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from edge.config import DB_PATH

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_edge.sql")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_edge_db():
    """Initializes the local SQLite tables and runs automatic migrations."""
    conn = get_connection()
    cursor = conn.cursor()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # Column migrations for existing databases
    cursor.execute("PRAGMA table_info(alert_fallback_queue)")
    col_info = cursor.fetchall()
    cols = [r["name"] for r in col_info]
    det_col = next((c for c in col_info if c["name"] == "detection_id"), None)
    if det_col and det_col["notnull"] == 1:
        cursor.execute("""
            CREATE TABLE alert_fallback_queue_migrated (
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
            )
        """)
        cursor.execute("""
            INSERT INTO alert_fallback_queue_migrated 
            (id, detection_id, recipient_phone, alert_message, status, retry_count, created_at, sent_at)
            SELECT id, detection_id, recipient_phone, alert_message, status, retry_count, created_at, sent_at 
            FROM alert_fallback_queue
        """)
        cursor.execute("DROP TABLE alert_fallback_queue")
        cursor.execute("ALTER TABLE alert_fallback_queue_migrated RENAME TO alert_fallback_queue")
        cursor.execute("PRAGMA table_info(alert_fallback_queue)")
        cols = [r["name"] for r in cursor.fetchall()]

    if "recipient_name" not in cols:
        cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN recipient_name TEXT")
    if "max_retries" not in cols:
        cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN max_retries INTEGER DEFAULT 3")
    if "next_retry_at" not in cols:
        cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN next_retry_at TIMESTAMP")
    if "last_error" not in cols:
        cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN last_error TEXT")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_alert_queue ON alert_fallback_queue(status, next_retry_at)")
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

def queue_sms_alert(detection_id, phone, name, message, max_retries=3, error_msg=None):
    """Adds an SMS to the local offline fallback queue with retry metadata."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alert_fallback_queue 
        (detection_id, recipient_phone, recipient_name, alert_message, status, retry_count, max_retries, next_retry_at, last_error)
        VALUES (?, ?, ?, ?, 'QUEUED_OFFLINE', 0, ?, CURRENT_TIMESTAMP, ?)
        """,
        (detection_id, phone, name, message, max_retries, error_msg)
    )
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return alert_id

def get_pending_sms_alerts(limit=10):
    """
    Retrieves and atomically locks pending SMS alerts eligible for retry.
    Recovers any stuck 'PROCESSING' state older than 2 minutes to prevent frozen queues.
    """
    conn = get_connection()
    cursor = conn.cursor()
    alerts = []

    try:
        # 1. Recover stale PROCESSING locks
        stale_cutoff = (datetime.now() - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE alert_fallback_queue SET status = 'QUEUED_OFFLINE' WHERE status = 'PROCESSING' AND created_at < ?",
            (stale_cutoff,)
        )

        # 2. Select eligible alerts
        now_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            SELECT id, detection_id, recipient_phone, recipient_name, alert_message, retry_count, max_retries 
            FROM alert_fallback_queue 
            WHERE status = 'QUEUED_OFFLINE' 
              AND retry_count < max_retries 
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
            ORDER BY id ASC 
            LIMIT ?
            """,
            (now_dt, limit)
        )
        rows = cursor.fetchall()

        if rows:
            alerts = [dict(r) for r in rows]
            ids = [a["id"] for a in alerts]
            placeholders = ",".join(["?"] * len(ids))
            cursor.execute(
                f"UPDATE alert_fallback_queue SET status = 'PROCESSING' WHERE id IN ({placeholders})",
                ids
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[Edge DB Error] Failed fetching pending SMS queue: {e}")
    finally:
        conn.close()

    return alerts

def record_edge_sms_result(alert_id, success, error_detail=None, error_msg=None):
    """
    Updates local alert status after retry attempt.
    - Success: Marked 'SENT' with sent_at timestamp.
    - Failure: Increments retry count; terminates with 'FAILED_PERMANENT' when max retries hit.
    """
    if error_msg is not None and error_detail is None:
        error_detail = error_msg

    conn = get_connection()
    cursor = conn.cursor()

    try:
        if success:
            cursor.execute(
                "UPDATE alert_fallback_queue SET status = 'SENT', sent_at = CURRENT_TIMESTAMP, last_error = NULL WHERE id = ?",
                (alert_id,)
            )
        else:
            cursor.execute("SELECT retry_count, max_retries FROM alert_fallback_queue WHERE id = ?", (alert_id,))
            row = cursor.fetchone()
            curr_count = row["retry_count"] if row else 0
            max_limit = row["max_retries"] if row else 3

            new_count = curr_count + 1
            if new_count >= max_limit:
                new_status = "FAILED_PERMANENT"
                next_time = None
                error_detail = f"Max retries ({max_limit}) exhausted: {error_detail or 'Delivery failed'}"
            else:
                new_status = "QUEUED_OFFLINE"
                backoff_sec = min(300, 10 * (2 ** new_count))
                next_time = (datetime.now() + timedelta(seconds=backoff_sec)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "UPDATE alert_fallback_queue SET status = ?, retry_count = ?, next_retry_at = ?, last_error = ? WHERE id = ?",
                (new_status, new_count, next_time, str(error_detail or "")[:250], alert_id)
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[Edge DB Error] Failed updating alert #{alert_id}: {e}")
    finally:
        conn.close()

def mark_sms_delivered(alert_id):
    """Backward-compatible helper: marks an alert as successfully delivered."""
    record_edge_sms_result(alert_id, True)

def flush_edge_sms_queue(sms_service=None):
    """Processes pending offline SMS queue on edge node."""
    if sms_service is None:
        try:
            from edge.services.sms_service import SMSService
            sms_service = SMSService()
        except Exception as e:
            print(f"[Edge SMS Flush Error] Could not load SMS Service: {e}")
            return {"processed": 0, "delivered": 0, "retrying": 0, "failed_permanent": 0}

    pending = get_pending_sms_alerts(limit=15)
    if not pending:
        return {"processed": 0, "delivered": 0, "retrying": 0, "failed_permanent": 0}

    delivered = 0
    retried = 0
    failed_perm = 0

    for item in pending:
        phone = item.get("recipient_phone")
        msg = item.get("alert_message")
        curr_retries = item.get("retry_count", 0)
        max_limit = item.get("max_retries", 3)

        success, detail, provider = sms_service.send_sms(phone, msg)
        record_edge_sms_result(item["id"], success, detail)

        if success:
            delivered += 1
        else:
            if curr_retries + 1 >= max_limit:
                failed_perm += 1
            else:
                retried += 1

    return {
        "processed": len(pending),
        "delivered": delivered,
        "retrying": retried,
        "failed_permanent": failed_perm
    }

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
