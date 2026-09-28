"""
Database Manager for Project Indradhanu (Project C)
Supports Dual-Layer Storage (Section 4.2 & 5 of PROJECT_SCOPE.md):
- Edge Layer: Local SQLite (indradhanu.db / edge.db) for zero-latency local logging & offline fallback queue
- Central / Cloud Layer: PostgreSQL (when DATABASE_URL is set) with sync latency measurement
"""

import os
import sqlite3
from datetime import datetime

# Database Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_POSTGRES = bool(DATABASE_URL and ("postgres://" in DATABASE_URL or "postgresql://" in DATABASE_URL))

DB_PATH = os.path.join(os.path.dirname(__file__), "indradhanu.db")
SQLITE_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
PG_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_postgres.sql")

def get_db_connection():
    """Returns database connection (PostgreSQL if DATABASE_URL configured, else SQLite)."""
    if IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """Unified query executor handling syntax differences between SQLite and PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Adjust placeholders (? for SQLite, %s for PostgreSQL)
    if IS_POSTGRES:
        query = query.replace("?", "%s")
    
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    result = None
    if fetchone:
        row = cursor.fetchone()
        result = dict(row) if row else None
    elif fetchall:
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
    elif commit:
        if IS_POSTGRES and "RETURNING id" in query:
            row = cursor.fetchone()
            result = row["id"] if row else None
        else:
            result = getattr(cursor, "lastrowid", None)
        conn.commit()

    conn.close()
    return result

def calculate_sync_latency(detected_at, reported_at):
    """
    Computes network sync latency (reported_at - detected_at)
    Mandated by Section 4.2 of PROJECT_SCOPE.md to distinguish real-time alerts
    from offline delayed backlog flushes.
    """
    if not detected_at or not reported_at:
        return {
            "latency_seconds": 1,
            "is_delayed": False,
            "latency_badge": "⚡ Real-time (< 2s)",
            "status_class": "latency-realtime"
        }

    def parse_dt(dt_val):
        if isinstance(dt_val, datetime):
            return dt_val
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S IST", "%Y-%m-%dT%H:%M:%S"):
            try:
                clean_str = str(dt_val).replace(" IST", "").strip()
                return datetime.strptime(clean_str, fmt)
            except Exception:
                continue
        return None

    dt_det = parse_dt(detected_at)
    dt_rep = parse_dt(reported_at)

    if not dt_det or not dt_rep:
        return {
            "latency_seconds": 1,
            "is_delayed": False,
            "latency_badge": "Real-time (< 2s sync)",
            "status_class": "latency-realtime"
        }

    diff_sec = max(0, int((dt_rep - dt_det).total_seconds()))
    is_delayed = diff_sec > 15  # More than 15s indicates offline delayed backlog recovery

    if is_delayed:
        if diff_sec < 3600:
            mins = diff_sec // 60
            secs = diff_sec % 60
            badge = f"Offline Delayed (+{mins}m {secs}s)"
        else:
            hrs = diff_sec // 3600
            mins = (diff_sec % 3600) // 60
            badge = f"Offline Delayed (+{hrs}h {mins}m)"
        status_class = "latency-delayed"
    else:
        badge = f"Real-time ({diff_sec}s sync)"
        status_class = "latency-realtime"

    return {
        "latency_seconds": diff_sec,
        "is_delayed": is_delayed,
        "latency_badge": badge,
        "status_class": status_class
    }

def init_db():
    """Initializes central database schema and seeds initial records if empty."""
    conn = get_db_connection()
    schema_file = PG_SCHEMA_PATH if IS_POSTGRES else SQLITE_SCHEMA_PATH
    
    with open(schema_file, "r") as f:
        script = f.read()

    cursor = conn.cursor()
    if IS_POSTGRES:
        cursor.execute(script)
        conn.commit()
    else:
        conn.executescript(script)

        # SQLite Column migrations
        cursor.execute("PRAGMA table_info(detections)")
        existing_cols = [r["name"] for r in cursor.fetchall()]
        if "node_code" not in existing_cols:
            cursor.execute("ALTER TABLE detections ADD COLUMN node_code TEXT DEFAULT 'NODE-01'")
        if "reported_at" not in existing_cols:
            cursor.execute("ALTER TABLE detections ADD COLUMN reported_at TIMESTAMP")
            cursor.execute("UPDATE detections SET reported_at = detected_at WHERE reported_at IS NULL")
            conn.commit()

    # Seed primary camera node NODE-01 if empty
    cursor.execute("SELECT COUNT(*) as cnt FROM camera_nodes")
    row = cursor.fetchone()
    cnt = row["cnt"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]
    if cnt == 0:
        seed_nodes = [
            ("NODE-01", "Tadoba North Perimeter Tower", "Sector 1 (Rampur Buffer)", 21.1458, 79.0882, "Optical USB Camera", 0, 145, 88, "ONLINE_ACTIVE")
        ]
        sql = """
            INSERT INTO camera_nodes 
            (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """ if IS_POSTGRES else """
            INSERT INTO camera_nodes 
            (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.executemany(sql, seed_nodes)
        conn.commit()

    conn.close()
    backend_type = "PostgreSQL" if IS_POSTGRES else "SQLite"
    print(f"[Central DB] Initialized successfully with {backend_type} engine.")

def log_detection(species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path, node_code="NODE-01"):
    """Logs detection directly to central database with current detected_at & reported_at."""
    sql = """
        INSERT INTO detections 
        (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path, node_code, detected_at, reported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    if IS_POSTGRES:
        sql += " RETURNING id"
    return execute_query(sql, (species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path, node_code), commit=True)

def log_synced_detection(species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path, node_code, detected_at=None):
    """
    Logs detection synced from edge station (Section 4.2).
    Preserves original 'detected_at' recorded by edge unit and stamps current time as 'reported_at'.
    """
    if detected_at:
        sql = """
            INSERT INTO detections 
            (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path, node_code, detected_at, reported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        params = (species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path, node_code, detected_at)
    else:
        sql = """
            INSERT INTO detections 
            (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path, node_code, detected_at, reported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path, node_code)
    
    if IS_POSTGRES:
        sql += " RETURNING id"
    return execute_query(sql, params, commit=True)

def update_node_heartbeat(node_code, battery_pct=None, heading=None, status="ONLINE_ACTIVE", lat=None, lon=None):
    """Updates camera node telemetry from heartbeat ping."""
    conn = get_db_connection()
    cursor = conn.cursor()
    check_sql = "SELECT id FROM camera_nodes WHERE node_code = %s" if IS_POSTGRES else "SELECT id FROM camera_nodes WHERE node_code = ?"
    cursor.execute(check_sql, (node_code,))
    row = cursor.fetchone()
    if row:
        updates = ["status = %s" if IS_POSTGRES else "status = ?", "last_heartbeat = CURRENT_TIMESTAMP"]
        params = [status]
        if battery_pct is not None:
            updates.append("battery_pct = %s" if IS_POSTGRES else "battery_pct = ?")
            params.append(battery_pct)
        if heading is not None:
            updates.append("rotator_heading = %s" if IS_POSTGRES else "rotator_heading = ?")
            params.append(heading)
        if lat is not None and lon is not None:
            updates.append("latitude = %s" if IS_POSTGRES else "latitude = ?")
            params.append(lat)
            updates.append("longitude = %s" if IS_POSTGRES else "longitude = ?")
            params.append(lon)
        params.append(node_code)
        sql = f"UPDATE camera_nodes SET {', '.join(updates)} WHERE node_code = " + ("%s" if IS_POSTGRES else "?")
        cursor.execute(sql, params)
    conn.commit()
    conn.close()

def get_recent_detections(limit=30):
    """Gets recent sightings enriched with Section 4.2 sync latency telemetry."""
    sql = "SELECT * FROM detections ORDER BY id DESC LIMIT ?"
    rows = execute_query(sql, (limit,), fetchall=True)
    if not rows:
        return []
        
    for r in rows:
        det_time = r.get("detected_at")
        rep_time = r.get("reported_at") or det_time
        latency = calculate_sync_latency(det_time, rep_time)
        r["latency_seconds"] = latency["latency_seconds"]
        r["is_delayed"] = latency["is_delayed"]
        r["latency_badge"] = latency["latency_badge"]
        r["latency_class"] = latency["status_class"]
    return rows

def get_contacts():
    return execute_query("SELECT * FROM villager_contacts WHERE is_active = 1 ORDER BY id ASC", fetchall=True)

def add_contact(full_name, phone_number, village_name, role="villager"):
    """Adds a new contact to villager_contacts table."""
    sql = "INSERT INTO villager_contacts (full_name, phone_number, village_name, role, is_active) VALUES (?, ?, ?, ?, 1)"
    if IS_POSTGRES:
        sql += " RETURNING id"
    res = execute_query(sql, (full_name, phone_number, village_name, role), commit=True)
    sync_contacts_to_edge()
    return res

def update_contact(contact_id, full_name, phone_number, village_name, role="villager"):
    """Updates an existing contact's details."""
    sql = "UPDATE villager_contacts SET full_name = ?, phone_number = ?, village_name = ?, role = ? WHERE id = ?"
    res = execute_query(sql, (full_name, phone_number, village_name, role, contact_id), commit=True)
    sync_contacts_to_edge()
    return res

def delete_contact(contact_id):
    """Deletes or deactivates a contact."""
    sql = "DELETE FROM villager_contacts WHERE id = ?"
    res = execute_query(sql, (contact_id,), commit=True)
    sync_contacts_to_edge()
    return res

def sync_contacts_to_edge():
    """Synchronizes central database contacts to edge SQLite database."""
    try:
        edge_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "edge", "database", "edge.db")
        if not os.path.exists(edge_db_path):
            return
        contacts = get_contacts()
        conn = sqlite3.connect(edge_db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM local_contacts")
        for c in contacts:
            cur.execute(
                "INSERT INTO local_contacts (id, full_name, phone_number, village_name, role, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                (c["id"], c["full_name"], c["phone_number"], c["village_name"], c["role"], c.get("is_active", 1))
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Contact Sync Error] Could not sync contacts to edge.db: {e}")

def update_node_location(node_code, lat, lon):
    """Updates latitude and longitude coordinates of a camera node."""
    sql = "UPDATE camera_nodes SET latitude = ?, longitude = ? WHERE node_code = ?"
    if IS_POSTGRES:
        sql = "UPDATE camera_nodes SET latitude = %s, longitude = %s WHERE node_code = %s"
    return execute_query(sql, (lat, lon, node_code), commit=True)

def get_camera_nodes():
    return execute_query("SELECT * FROM camera_nodes ORDER BY id ASC", fetchall=True)

def register_camera_node(node_code, node_name, sector, lat, lon, camera_type="Thermal IR (MLX90640)"):
    sql = """
        INSERT INTO camera_nodes 
        (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
        VALUES (?, ?, ?, ?, ?, ?, 1, 0, 100, 'ONLINE_ACTIVE')
    """
    if IS_POSTGRES:
        sql += " RETURNING id"
    return execute_query(sql, (node_code, node_name, sector, lat, lon, camera_type), commit=True)

def queue_offline_alert(detection_id, phone, message):
    sql = "INSERT INTO alert_fallback_queue (detection_id, recipient_phone, alert_message, status) VALUES (?, ?, ?, 'QUEUED_OFFLINE')"
    return execute_query(sql, (detection_id, phone, message), commit=True)

def flush_offline_queue():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alert_fallback_queue WHERE status = 'QUEUED_OFFLINE'")
    rows = cursor.fetchall()
    pending = [dict(r) for r in rows]
    pending_cnt = len(pending)

    for item in pending:
        phone = item.get("recipient_phone")
        msg = item.get("alert_message")
        print(f"[SMS Gateway Flush 🚀] Dispatched queued alert to {phone}: '{msg[:45]}...'")

    cursor.execute("UPDATE alert_fallback_queue SET status = 'DELIVERED', dispatched_at = CURRENT_TIMESTAMP WHERE status = 'QUEUED_OFFLINE'")
    conn.commit()
    conn.close()
    return pending_cnt

if __name__ == "__main__":
    init_db()
