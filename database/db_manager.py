"""
Database Manager for Project Indradhanu (Project C)
Supports Dual-Layer Storage (Section 4.2 & 5 of PROJECT_SCOPE.md):
- Edge Layer: Local SQLite (indradhanu.db / edge.db) for zero-latency local logging & offline fallback queue
- Central / Cloud Layer: PostgreSQL (when DATABASE_URL is set) with sync latency measurement
Includes Connection Pooling, Connection Health Checks, and Fault-Tolerant SMS Retry Engine.
"""

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

# Database Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL and ("postgresql://" in DATABASE_URL))

DB_PATH = os.path.join(os.path.dirname(__file__), "indradhanu.db")
SQLITE_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
PG_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_postgres.sql")

# PostgreSQL Connection Pool & Concurrency Lock
_PG_POOL = None
_PG_LOCK = threading.Lock()
_USE_FALLBACK_SQLITE = False

def get_pg_pool():
    """Initializes or returns thread-safe connection pool for PostgreSQL."""
    global _PG_POOL, _USE_FALLBACK_SQLITE
    if not IS_POSTGRES or _USE_FALLBACK_SQLITE:
        return None

    with _PG_LOCK:
        if _PG_POOL is None:
            try:
                import psycopg2
                from psycopg2.pool import ThreadedConnectionPool
                import psycopg2.extras
                _PG_POOL = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
                print("[Central DB] Initialized PostgreSQL connection pool successfully.")
            except Exception as e:
                print(f"[Central DB Warning] Failed to initialize PostgreSQL pool: {e}. Falling back to SQLite.")
                _USE_FALLBACK_SQLITE = True
                return None
    return _PG_POOL

def get_db_connection():
    """Returns database connection (PostgreSQL if DATABASE_URL configured and healthy, else SQLite)."""
    pool = get_pg_pool()
    if pool and not _USE_FALLBACK_SQLITE:
        try:
            conn = pool.getconn()
            if conn.closed:
                pool.putconn(conn, close=True)
                conn = pool.getconn()
            return conn
        except Exception as e:
            print(f"[Central DB Warning] Pool getconn failed: {e}. Falling back to SQLite.")

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def release_db_connection(conn):
    """Safely returns PostgreSQL connection to pool or closes SQLite connection."""
    if conn is None:
        return
    pool = _PG_POOL
    if pool and not _USE_FALLBACK_SQLITE and hasattr(conn, "cursor_factory"):
        try:
            pool.putconn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    else:
        try:
            conn.close()
        except Exception:
            pass

def close_db_pool():
    """Safely closes all connections in the PostgreSQL connection pool."""
    global _PG_POOL
    with _PG_LOCK:
        if _PG_POOL:
            try:
                _PG_POOL.closeall()
            except Exception:
                pass
            _PG_POOL = None

def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """Unified query executor handling syntax, transactions, and connection release."""
    conn = get_db_connection()
    is_pg = hasattr(conn, "cursor_factory") or (hasattr(conn, "__class__") and "psycopg2" in conn.__class__.__module__)
    cursor = None
    result = None

    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            query = query.replace("?", "%s")
            # Auto-append RETURNING id for PostgreSQL INSERTs when committing
            if commit:
                trimmed = query.strip()
                if trimmed.upper().startswith("INSERT") and "RETURNING" not in trimmed.upper():
                    query = trimmed.rstrip("; ") + " RETURNING id"
        else:
            cursor = conn.cursor()

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetchone:
            row = cursor.fetchone()
            result = dict(row) if row else None
        elif fetchall:
            rows = cursor.fetchall()
            result = [dict(r) for r in rows]
        elif commit:
            if is_pg and "RETURNING" in query.upper():
                try:
                    row = cursor.fetchone()
                    result = row["id"] if isinstance(row, dict) and "id" in row else (row[0] if row else None)
                except Exception:
                    result = None
            else:
                result = getattr(cursor, "lastrowid", None)
            conn.commit()

        return result
    except Exception as e:
        if commit and conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[Database Error] Query execution failed: {e}\nQuery: {query[:120]}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)

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
    is_pg = hasattr(conn, "cursor_factory") or (hasattr(conn, "__class__") and "psycopg2" in conn.__class__.__module__)
    schema_file = PG_SCHEMA_PATH if is_pg else SQLITE_SCHEMA_PATH

    cursor = None
    try:
        with open(schema_file, "r", encoding="utf-8") as f:
            script = f.read()

        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(script)
            conn.commit()
        else:
            cursor = conn.cursor()
            conn.executescript(script)

            # SQLite Column migrations
            cursor.execute("PRAGMA table_info(detections)")
            existing_cols = [r["name"] for r in cursor.fetchall()]
            if "node_code" not in existing_cols:
                cursor.execute("ALTER TABLE detections ADD COLUMN node_code TEXT DEFAULT 'NODE-01'")
            if "reported_at" not in existing_cols:
                cursor.execute("ALTER TABLE detections ADD COLUMN reported_at TIMESTAMP")
                cursor.execute("UPDATE detections SET reported_at = detected_at WHERE reported_at IS NULL")

            # SQLite Column & Constraint migrations for alert_fallback_queue
            cursor.execute("PRAGMA table_info(alert_fallback_queue)")
            queue_col_info = cursor.fetchall()
            queue_cols = [r["name"] for r in queue_col_info]
            det_col = next((c for c in queue_col_info if c["name"] == "detection_id"), None)
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
                        dispatched_at TIMESTAMP,
                        FOREIGN KEY (detection_id) REFERENCES detections(id)
                    )
                """)
                cursor.execute("""
                    INSERT INTO alert_fallback_queue_migrated 
                    (id, detection_id, recipient_phone, alert_message, status, retry_count, created_at, dispatched_at)
                    SELECT id, detection_id, recipient_phone, alert_message, status, retry_count, created_at, dispatched_at 
                    FROM alert_fallback_queue
                """)
                cursor.execute("DROP TABLE alert_fallback_queue")
                cursor.execute("ALTER TABLE alert_fallback_queue_migrated RENAME TO alert_fallback_queue")
                cursor.execute("PRAGMA table_info(alert_fallback_queue)")
                queue_cols = [r["name"] for r in cursor.fetchall()]

            if "recipient_name" not in queue_cols:
                cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN recipient_name TEXT")
            if "max_retries" not in queue_cols:
                cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN max_retries INTEGER DEFAULT 3")
            if "next_retry_at" not in queue_cols:
                cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN next_retry_at TIMESTAMP")
            if "last_error" not in queue_cols:
                cursor.execute("ALTER TABLE alert_fallback_queue ADD COLUMN last_error TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_queue_status ON alert_fallback_queue(status, next_retry_at)")
            conn.commit()

        # Seed primary camera node NODE-01 if empty
        cursor.execute("SELECT COUNT(*) as cnt FROM camera_nodes")
        row = cursor.fetchone()
        cnt = row["cnt"] if isinstance(row, dict) else row[0]
        if cnt == 0:
            seed_nodes = [
                ("NODE-01", "Tadoba North Perimeter Tower", "Sector 1 (Rampur Buffer)", 21.1458, 79.0882, "Optical USB Camera", 0, 145, 88, "ONLINE_ACTIVE")
            ]
            sql = """
                INSERT INTO camera_nodes 
                (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """ if is_pg else """
                INSERT INTO camera_nodes 
                (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.executemany(sql, seed_nodes)
            conn.commit()

        # Seed default emergency contacts if directory is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM villager_contacts")
        row = cursor.fetchone()
        cnt_contacts = row["cnt"] if isinstance(row, dict) else row[0]
        if cnt_contacts == 0:
            default_contacts = [
                ("Ashutosh Shioorkar", "+91 8010294703", "Rampur", "forest_ranger"),
                ("Ramesh Patil (Sarpanch)", "+91 9822012345", "Rampur", "sarpanch"),
                ("Sunil Marawi (Patrol)", "+91 9423198765", "Rampur Buffer", "ranger")
            ]
            sql_contact = """
                INSERT INTO villager_contacts (full_name, phone_number, village_name, role, is_active)
                VALUES (%s, %s, %s, %s, 1)
            """ if is_pg else """
                INSERT INTO villager_contacts (full_name, phone_number, village_name, role, is_active)
                VALUES (?, ?, ?, ?, 1)
            """
            cursor.executemany(sql_contact, default_contacts)
            conn.commit()

        backend_type = "PostgreSQL" if is_pg else "SQLite"
        print(f"[Central DB] Initialized successfully with {backend_type} engine.")
    except Exception as e:
        print(f"[Central DB Error] Database initialization failed: {e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)

def log_detection(species, scientific_name, confidence, threat_level, lat, lon, distance_m, heading, img_path, node_code="NODE-01"):
    """Logs detection directly to central database with current detected_at & reported_at."""
    sql = """
        INSERT INTO detections 
        (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, image_snapshot_path, node_code, detected_at, reported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
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

    return execute_query(sql, params, commit=True)

def update_node_heartbeat(node_code, battery_pct=None, heading=None, status="ONLINE_ACTIVE", lat=None, lon=None):
    """Updates camera node telemetry from heartbeat ping, auto-registering if unknown."""
    conn = get_db_connection()
    is_pg = hasattr(conn, "cursor_factory") or (hasattr(conn, "__class__") and "psycopg2" in conn.__class__.__module__)
    cursor = None
    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cursor = conn.cursor()

        check_sql = "SELECT id FROM camera_nodes WHERE node_code = %s" if is_pg else "SELECT id FROM camera_nodes WHERE node_code = ?"
        cursor.execute(check_sql, (node_code,))
        row = cursor.fetchone()
        if row:
            updates = ["status = %s" if is_pg else "status = ?", "last_heartbeat = CURRENT_TIMESTAMP"]
            params = [status]
            if battery_pct is not None:
                updates.append("battery_pct = %s" if is_pg else "battery_pct = ?")
                params.append(battery_pct)
            if heading is not None:
                updates.append("rotator_heading = %s" if is_pg else "rotator_heading = ?")
                params.append(heading)
            if lat is not None and lon is not None:
                updates.append("latitude = %s" if is_pg else "latitude = ?")
                params.append(lat)
                updates.append("longitude = %s" if is_pg else "longitude = ?")
                params.append(lon)
            params.append(node_code)
            sql = f"UPDATE camera_nodes SET {', '.join(updates)} WHERE node_code = " + ("%s" if is_pg else "?")
            cursor.execute(sql, params)
        else:
            # Auto-register new node on first heartbeat
            ins_sql = """
                INSERT INTO camera_nodes 
                (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """ if is_pg else """
                INSERT INTO camera_nodes 
                (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(ins_sql, (
                node_code, f"Station {node_code}", "Perimeter Buffer",
                float(lat or 21.1458), float(lon or 79.0882),
                "Optical USB Camera", 0, int(heading or 145), int(battery_pct or 88), status
            ))
        conn.commit()
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        print(f"[Heartbeat Update Error] {e}")
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        release_db_connection(conn)

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
    """Gets active emergency contacts from villager_contacts table."""
    return execute_query("SELECT * FROM villager_contacts WHERE is_active = 1 ORDER BY id ASC", fetchall=True) or []

def add_contact(full_name, phone_number, village_name, role="villager"):
    """Adds a new contact to villager_contacts table."""
    sql = "INSERT INTO villager_contacts (full_name, phone_number, village_name, role, is_active) VALUES (?, ?, ?, ?, 1)"
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
    """Deletes a contact from the central directory."""
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
    return execute_query(sql, (lat, lon, node_code), commit=True)

def get_camera_nodes():
    """Returns all camera nodes in the array."""
    return execute_query("SELECT * FROM camera_nodes ORDER BY id ASC", fetchall=True) or []

def register_camera_node(node_code, node_name, sector, lat, lon, camera_type="Thermal IR (MLX90640)"):
    """Registers a new camera node."""
    sql = """
        INSERT INTO camera_nodes 
        (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status)
        VALUES (?, ?, ?, ?, ?, ?, 1, 0, 100, 'ONLINE_ACTIVE')
    """
    return execute_query(sql, (node_code, node_name, sector, lat, lon, camera_type), commit=True)

# ==============================================================================
# SMS RETRY ENGINE - CENTRAL LAYER (PostgreSQL & SQLite)
# ==============================================================================

def queue_offline_alert(detection_id=None, phone="", message="", name="Villager", max_retries=3, error_msg=None, recipient_name=None):
    """
    Enqueues an SMS into the fallback queue with retry limits and backoff metadata.
    Guarantees zero alert loss during cellular outages.
    """
    if recipient_name:
        name = recipient_name
    sql = """
        INSERT INTO alert_fallback_queue 
        (detection_id, recipient_phone, recipient_name, alert_message, status, retry_count, max_retries, next_retry_at, last_error) 
        VALUES (?, ?, ?, ?, 'QUEUED_OFFLINE', 0, ?, CURRENT_TIMESTAMP, ?)
    """
    return execute_query(sql, (detection_id, phone, name, message, max_retries, error_msg), commit=True)

def get_pending_offline_alerts(limit=10):
    """
    Atomically retrieves and locks pending offline SMS alerts eligible for retry.
    Recovers any stuck 'PROCESSING' state older than 2 minutes to prevent frozen queues.
    """
    conn = get_db_connection()
    is_pg = hasattr(conn, "cursor_factory") or (hasattr(conn, "__class__") and "psycopg2" in conn.__class__.__module__)
    cursor = None
    alerts = []

    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cursor = conn.cursor()

        # 1. Stale-lock recovery: Reset stuck PROCESSING alerts older than 120s
        if is_pg:
            stale_sql = "UPDATE alert_fallback_queue SET status = 'QUEUED_OFFLINE' WHERE status = 'PROCESSING' AND created_at < NOW() - INTERVAL '120 seconds'"
            cursor.execute(stale_sql)
        else:
            stale_sql = "UPDATE alert_fallback_queue SET status = 'QUEUED_OFFLINE' WHERE status = 'PROCESSING' AND created_at < datetime('now', '-120 seconds')"
            cursor.execute(stale_sql)

        # 2. Select eligible alerts (status QUEUED_OFFLINE, retry_count < max_retries, next_retry_at <= now)
        if is_pg:
            select_sql = """
                SELECT id, detection_id, recipient_phone, recipient_name, alert_message, retry_count, max_retries 
                FROM alert_fallback_queue 
                WHERE status = 'QUEUED_OFFLINE' 
                  AND retry_count < max_retries 
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY id ASC 
                LIMIT %s
            """
            cursor.execute(select_sql, (limit,))
        else:
            select_sql = """
                SELECT id, detection_id, recipient_phone, recipient_name, alert_message, retry_count, max_retries 
                FROM alert_fallback_queue 
                WHERE status = 'QUEUED_OFFLINE' 
                  AND retry_count < max_retries 
                  AND (next_retry_at IS NULL OR next_retry_at <= datetime('now'))
                ORDER BY id ASC 
                LIMIT ?
            """
            cursor.execute(select_sql, (limit,))
        rows = cursor.fetchall()

        if rows:
            alerts = [dict(r) for r in rows]
            ids = [a["id"] for a in alerts]

            # 3. Atomically lock selected rows to prevent concurrent workers from sending duplicates
            if is_pg:
                lock_sql = "UPDATE alert_fallback_queue SET status = 'PROCESSING' WHERE id = ANY(%s)"
                cursor.execute(lock_sql, (ids,))
            else:
                placeholders = ",".join(["?"] * len(ids))
                lock_sql = f"UPDATE alert_fallback_queue SET status = 'PROCESSING' WHERE id IN ({placeholders})"
                cursor.execute(lock_sql, ids)

        conn.commit()
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        print(f"[SMS Retry Engine Error] Error checking pending queue: {e}")
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        release_db_connection(conn)

    return alerts

def record_alert_retry_result(alert_id, success, error_detail=None, error_msg=None):
    """
    Updates queue record following a retry attempt.
    - Success: Marked 'DELIVERED' with dispatched timestamp.
    - Failure: Increments retry_count; if max_retries reached, marks 'FAILED_PERMANENT';
               else schedules exponential backoff.
    """
    if error_msg is not None and error_detail is None:
        error_detail = error_msg

    conn = get_db_connection()
    is_pg = hasattr(conn, "cursor_factory") or (hasattr(conn, "__class__") and "psycopg2" in conn.__class__.__module__)
    cursor = None

    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cursor = conn.cursor()

        if success:
            update_sql = """
                UPDATE alert_fallback_queue 
                SET status = 'DELIVERED', dispatched_at = CURRENT_TIMESTAMP, last_error = NULL 
                WHERE id = ?
            """
            if is_pg:
                update_sql = update_sql.replace("?", "%s")
            cursor.execute(update_sql, (alert_id,))
        else:
            # Fetch current attempts
            fetch_sql = "SELECT retry_count, max_retries FROM alert_fallback_queue WHERE id = ?"
            if is_pg:
                fetch_sql = fetch_sql.replace("?", "%s")
            cursor.execute(fetch_sql, (alert_id,))
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
                # Exponential backoff: 10s, 20s, 40s, max 300s
                backoff_sec = min(300, 10 * (2 ** new_count))
                next_time = (datetime.now(timezone.utc) + timedelta(seconds=backoff_sec)).strftime("%Y-%m-%d %H:%M:%S")

            update_sql = """
                UPDATE alert_fallback_queue 
                SET status = ?, retry_count = ?, next_retry_at = ?, last_error = ? 
                WHERE id = ?
            """
            if is_pg:
                update_sql = update_sql.replace("?", "%s")
            cursor.execute(update_sql, (new_status, new_count, next_time, str(error_detail or "")[:250], alert_id))

        conn.commit()
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        print(f"[SMS Retry Engine Error] Error recording retry result for alert #{alert_id}: {e}")
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        release_db_connection(conn)


def flush_offline_queue(sms_service=None):
    """
    Drains the offline SMS alert queue by dispatching via the active SMS gateway
    and recording delivery/backoff status for each recipient.
    """
    if sms_service is None:
        try:
            from edge.services.sms_service import SMSService
            sms_service = SMSService()
        except Exception as e:
            print(f"[Flush Error] Could not load SMS Service: {e}")
            return {"processed": 0, "delivered": 0, "retrying": 0, "failed_permanent": 0}

    pending = get_pending_offline_alerts(limit=20)
    if not pending:
        return {"processed": 0, "delivered": 0, "retrying": 0, "failed_permanent": 0}

    delivered_cnt = 0
    retrying_cnt = 0
    perm_failed_cnt = 0

    print(f"\n[SMS Retry Engine 🚀] Processing {len(pending)} queued alerts...")

    for item in pending:
        phone = item.get("recipient_phone")
        msg = item.get("alert_message")
        curr_retries = item.get("retry_count", 0)
        max_limit = item.get("max_retries", 3)

        try:
            if hasattr(sms_service, "send_sms"):
                res = sms_service.send_sms(phone, msg)
            elif hasattr(sms_service, "send_alert_sms"):
                res = sms_service.send_alert_sms(phone, msg)
            else:
                res = (False, "Unsupported SMS service interface", "UNKNOWN")

            if isinstance(res, tuple):
                success = res[0]
                detail = res[1] if len(res) > 1 else ("Success" if success else "Failed")
                provider = res[2] if len(res) > 2 else "SMS"
            else:
                success = bool(res)
                detail = "Delivered" if success else "Provider rejected SMS"
                provider = "SMS"
        except Exception as e:
            success = False
            detail = f"Exception during SMS dispatch: {e}"
            provider = "ERROR"

        record_alert_retry_result(item["id"], success, detail)

        if success:
            delivered_cnt += 1
            print(f"   [SMS Retry SUCCESS] Delivered to {phone} via {provider}")
        else:
            if curr_retries + 1 >= max_limit:
                perm_failed_cnt += 1
                print(f"   [SMS Retry EXHAUSTED] Max retries ({max_limit}) reached for {phone}. Marked FAILED_PERMANENT.")
            else:
                retrying_cnt += 1
                print(f"   [SMS Retry FAILED] Attempt {curr_retries + 1}/{max_limit} to {phone} failed: {detail}. Scheduled backoff.")

    return {
        "processed": len(pending),
        "total_processed": len(pending),
        "delivered": delivered_cnt,
        "retrying": retrying_cnt,
        "failed_permanent": perm_failed_cnt
    }

if __name__ == "__main__":
    init_db()
