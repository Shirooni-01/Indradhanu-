"""
Local Edge SQLite Database Manager for Project Indradhanu.
Manages offline-tolerant event buffering on Raspberry Pi 3 Model B+ with:
- Unique UUID event_id generation and persistence
- Safe recovery of pending events across process/device restarts
- Exponential backoff retry state for central server synchronization
- Offline SMS fallback queue
"""

import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from edge.config import DB_PATH

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_edge.sql")


def get_connection(db_path=None):
    target_path = db_path or os.environ.get("EDGE_DB_PATH") or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_edge_db(db_path=None):
    """Initializes local SQLite tables, runs safe schema migrations, and recovers interrupted uploads."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # 1. Inspect if local_detections already exists without event_id
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='local_detections'")
        has_local_det = cursor.fetchone() is not None

        if has_local_det:
            cursor.execute("PRAGMA table_info(local_detections)")
            det_cols = [r["name"] for r in cursor.fetchall()]

            if "event_id" not in det_cols:
                cursor.execute("ALTER TABLE local_detections ADD COLUMN event_id TEXT")
            if "bbox_json" not in det_cols:
                cursor.execute("ALTER TABLE local_detections ADD COLUMN bbox_json TEXT")
            if "sync_status" not in det_cols:
                cursor.execute("ALTER TABLE local_detections ADD COLUMN sync_status TEXT DEFAULT 'PENDING'")
            if "sync_attempts" not in det_cols:
                cursor.execute("ALTER TABLE local_detections ADD COLUMN sync_attempts INTEGER DEFAULT 0")
            if "next_sync_retry_at" not in det_cols:
                cursor.execute("ALTER TABLE local_detections ADD COLUMN next_sync_retry_at TIMESTAMP")
            if "last_sync_error" not in det_cols:
                cursor.execute("ALTER TABLE local_detections ADD COLUMN last_sync_error TEXT")

            # Backfill missing event_id for any legacy rows
            cursor.execute("SELECT id, node_code, detected_at FROM local_detections WHERE event_id IS NULL OR event_id = ''")
            legacy_rows = cursor.fetchall()
            for row in legacy_rows:
                deterministic_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"edge-{row['node_code']}-{row['id']}-{row['detected_at']}"))
                cursor.execute("UPDATE local_detections SET event_id = ? WHERE id = ?", (deterministic_uuid, row["id"]))

            cursor.execute(
                "UPDATE local_detections SET sync_status = CASE WHEN is_synced_to_hq = 1 THEN 'SYNCED' ELSE 'PENDING' END WHERE sync_status IS NULL"
            )
            conn.commit()

        # 2. Ensure alert_fallback_queue columns exist if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_fallback_queue'")
        if cursor.fetchone() is not None:
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
            conn.commit()

        # 3. Execute full schema script
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        # 4. Recover any stuck UPLOADING events from an abrupt crash/reboot
        cursor.execute(
            """
            UPDATE local_detections
            SET sync_status = 'PENDING', next_sync_retry_at = NULL
            WHERE is_synced_to_hq = 0 AND sync_status = 'UPLOADING'
            """
        )
        conn.commit()
    finally:
        conn.close()


def recover_pending_events_on_restart(db_path=None):
    """
    Ensures all unsynced detections survive restarts intact and resets any interrupted
    'UPLOADING' locks back to 'PENDING' for immediate retry.
    Returns the number of pending unsynced events ready for upload.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE local_detections
            SET sync_status = 'PENDING', next_sync_retry_at = NULL
            WHERE is_synced_to_hq = 0 AND sync_status IN ('UPLOADING', 'FAILED_RETRY')
            """
        )
        cursor.execute("SELECT COUNT(*) AS cnt FROM local_detections WHERE is_synced_to_hq = 0")
        row = cursor.fetchone()
        pending_count = row["cnt"] if row else 0
        conn.commit()
        return pending_count
    finally:
        conn.close()


def log_local_detection(
    node_code,
    species,
    scientific_name,
    confidence,
    threat_level,
    lat,
    lon,
    distance_m,
    heading,
    img_path,
    event_id=None,
    bbox=None,
    detected_at=None,
    db_path=None,
):
    """
    Saves a new edge detection event immediately to local SQLite.
    Generates a unique UUIDv4 event_id if not provided.
    Returns (det_id, event_id).
    """
    event_uid = str(event_id).strip() if event_id else str(uuid.uuid4())
    bbox_str = json.dumps(bbox) if bbox is not None and not isinstance(bbox, str) else bbox
    ts_str = detected_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        # Check idempotency if event_id already exists locally
        cursor.execute("SELECT id, event_id FROM local_detections WHERE event_id = ?", (event_uid,))
        existing = cursor.fetchone()
        if existing:
            return existing["id"], existing["event_id"]

        cursor.execute(
            """
            INSERT INTO local_detections
            (event_id, node_code, species, scientific_name, confidence, threat_level,
             latitude, longitude, distance_meters, rotator_heading, bbox_json,
             image_snapshot_path, detected_at, is_synced_to_hq, sync_status, sync_attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'PENDING', 0)
            """,
            (
                event_uid,
                node_code,
                species,
                scientific_name,
                float(confidence),
                threat_level,
                float(lat),
                float(lon),
                int(distance_m or 0),
                int(heading or 0),
                bbox_str,
                img_path,
                ts_str,
            ),
        )
        det_id = cursor.lastrowid
        conn.commit()
        return det_id, event_uid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_unsynced_detections(limit=20, respect_backoff=False, db_path=None):
    """
    Gets pending local detections that have not yet been synchronized to the central server.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        if respect_backoff:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                SELECT * FROM local_detections
                WHERE is_synced_to_hq = 0
                  AND (next_sync_retry_at IS NULL OR next_sync_retry_at <= ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (now_str, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM local_detections
                WHERE is_synced_to_hq = 0
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_pending_sync_count(db_path=None):
    """Returns count of unsynced detection events currently buffered on this edge device."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) AS cnt FROM local_detections WHERE is_synced_to_hq = 0")
        row = cursor.fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def mark_detection_synced(det_id_or_event_id, db_path=None):
    """Marks a local detection (by integer id or UUID event_id) as synchronized with the central server."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        if isinstance(det_id_or_event_id, int) or str(det_id_or_event_id).isdigit():
            cursor.execute(
                """
                UPDATE local_detections
                SET is_synced_to_hq = 1,
                    sync_status = 'SYNCED',
                    last_sync_error = NULL,
                    synced_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(det_id_or_event_id),),
            )
        else:
            cursor.execute(
                """
                UPDATE local_detections
                SET is_synced_to_hq = 1,
                    sync_status = 'SYNCED',
                    last_sync_error = NULL,
                    synced_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (str(det_id_or_event_id),),
            )
        conn.commit()
    finally:
        conn.close()


def record_sync_failure(det_id_or_event_id, error_msg, db_path=None):
    """
    Records a failed synchronization attempt without discarding the event.
    Applies bounded exponential backoff for subsequent retries.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        if isinstance(det_id_or_event_id, int) or str(det_id_or_event_id).isdigit():
            cursor.execute("SELECT id, sync_attempts FROM local_detections WHERE id = ?", (int(det_id_or_event_id),))
        else:
            cursor.execute("SELECT id, sync_attempts FROM local_detections WHERE event_id = ?", (str(det_id_or_event_id),))
        row = cursor.fetchone()
        if not row:
            return
        attempts = int(row["sync_attempts"] or 0) + 1
        backoff_sec = min(120, 5 * (2 ** min(attempts, 5)))
        next_retry = (datetime.now() + timedelta(seconds=backoff_sec)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            UPDATE local_detections
            SET is_synced_to_hq = 0,
                sync_status = 'FAILED_RETRY',
                sync_attempts = ?,
                next_sync_retry_at = ?,
                last_sync_error = ?
            WHERE id = ?
            """,
            (attempts, next_retry, str(error_msg or "")[:300], row["id"]),
        )
        conn.commit()
    finally:
        conn.close()


def get_local_detection_by_event_id(event_id, db_path=None):
    """Fetches a single local detection record by its UUID event_id."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM local_detections WHERE event_id = ?", (str(event_id),))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def queue_sms_alert(detection_id, phone, name, message, max_retries=3, error_msg=None, db_path=None):
    """Adds an SMS to the local offline fallback queue with retry metadata."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO alert_fallback_queue
            (detection_id, recipient_phone, recipient_name, alert_message, status, retry_count, max_retries, next_retry_at, last_error)
            VALUES (?, ?, ?, ?, 'QUEUED_OFFLINE', 0, ?, CURRENT_TIMESTAMP, ?)
            """,
            (detection_id, phone, name, message, max_retries, error_msg),
        )
        alert_id = cursor.lastrowid
        conn.commit()
        return alert_id
    finally:
        conn.close()


def get_pending_sms_alerts(limit=10, db_path=None):
    """Retrieves and atomically locks pending SMS alerts eligible for retry."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    alerts = []

    try:
        stale_cutoff = (datetime.now() - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE alert_fallback_queue SET status = 'QUEUED_OFFLINE' WHERE status = 'PROCESSING' AND created_at < ?",
            (stale_cutoff,),
        )

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
            (now_dt, limit),
        )
        rows = cursor.fetchall()

        if rows:
            alerts = [dict(r) for r in rows]
            ids = [a["id"] for a in alerts]
            placeholders = ",".join(["?"] * len(ids))
            cursor.execute(
                f"UPDATE alert_fallback_queue SET status = 'PROCESSING' WHERE id IN ({placeholders})",
                ids,
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[Edge DB Error] Failed fetching pending SMS queue: {e}")
    finally:
        conn.close()

    return alerts


def record_edge_sms_result(alert_id, success, error_detail=None, error_msg=None, db_path=None):
    """Updates local alert status after retry attempt."""
    if error_msg is not None and error_detail is None:
        error_detail = error_msg

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        if success:
            cursor.execute(
                "UPDATE alert_fallback_queue SET status = 'SENT', sent_at = CURRENT_TIMESTAMP, last_error = NULL WHERE id = ?",
                (alert_id,),
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
                (new_status, new_count, next_time, str(error_detail or "")[:250], alert_id),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[Edge DB Error] Failed updating alert #{alert_id}: {e}")
    finally:
        conn.close()


def mark_sms_delivered(alert_id, db_path=None):
    record_edge_sms_result(alert_id, True, db_path=db_path)


def flush_edge_sms_queue(sms_service=None, db_path=None):
    """Processes pending offline SMS queue on edge node."""
    if sms_service is None:
        try:
            from edge.services.sms_service import SMSService
            sms_service = SMSService()
        except Exception as e:
            print(f"[Edge SMS Flush Error] Could not load SMS Service: {e}")
            return {"processed": 0, "delivered": 0, "retrying": 0, "failed_permanent": 0}

    pending = get_pending_sms_alerts(limit=15, db_path=db_path)
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
        record_edge_sms_result(item["id"], success, detail, db_path=db_path)

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
        "failed_permanent": failed_perm,
    }


def get_local_contacts(db_path=None):
    """Gets active contacts for immediate alert broadcast."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM local_contacts WHERE is_active = 1")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def log_edge_event(event_type, details, db_path=None):
    """Logs system event to local SQLite."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO edge_logs (event_type, details) VALUES (?, ?)", (event_type, details))
        conn.commit()
    finally:
        conn.close()
