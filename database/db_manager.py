"""
Central Database Manager for Project Indradhanu.
Supports:
- Central Permanent Storage: PostgreSQL (configured via DATABASE_URL environment variable)
- Controlled Local Development Fallback: SQLite (when ALLOW_SQLITE_FALLBACK=true)
- Unique event_id enforcement & idempotent edge event ingestion
- Central AI verification metadata persistence
- Siren activation audit ledger & duplicate command prevention
- Real-time multi-device connectivity computation (based on actual heartbeat & sync timestamps)
"""

import os
import json
import uuid
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from database.system_config import load_dotenv_file

load_dotenv_file()

DB_PATH = os.path.join(os.path.dirname(__file__), "indradhanu.db")
SQLITE_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
PG_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_postgres.sql")

_PG_POOL = None
_PG_LOCK = threading.Lock()
_USE_FALLBACK_SQLITE = False
_LAST_PG_ERROR = None


def _get_database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _allow_sqlite_fallback():
    return os.environ.get("ALLOW_SQLITE_FALLBACK", "true").strip().lower() in ("1", "true", "yes")


def get_pg_pool():
    """Initializes or returns thread-safe connection pool for PostgreSQL."""
    global _PG_POOL, _USE_FALLBACK_SQLITE, _LAST_PG_ERROR
    db_url = _get_database_url()
    is_postgres_configured = bool(db_url and ("postgresql://" in db_url))

    if not is_postgres_configured:
        return None

    if _USE_FALLBACK_SQLITE:
        return None

    with _PG_LOCK:
        if _PG_POOL is None:
            try:
                import psycopg2
                from psycopg2.pool import ThreadedConnectionPool
                _PG_POOL = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=db_url)
                _LAST_PG_ERROR = None
                print("[Central DB] Initialized PostgreSQL connection pool successfully.")
            except Exception as e:
                _LAST_PG_ERROR = str(e)
                if not _allow_sqlite_fallback():
                    raise RuntimeError(f"PostgreSQL connection failed and ALLOW_SQLITE_FALLBACK is false: {e}") from e
                print(f"[Central DB Warning] PostgreSQL unavailable ({e}). Using SQLite fallback.")
                _USE_FALLBACK_SQLITE = True
                return None
    return _PG_POOL


def get_db_status():
    """Returns diagnostic metadata about the active central database backend."""
    db_url = _get_database_url()
    is_pg_configured = bool(db_url and ("postgresql://" in db_url))
    active_engine = "PostgreSQL" if (is_pg_configured and not _USE_FALLBACK_SQLITE and _PG_POOL is not None) else "SQLite"
    return {
        "active_engine": active_engine,
        "postgres_configured": is_pg_configured,
        "using_sqlite_fallback": not (active_engine == "PostgreSQL"),
        "last_pg_error": _LAST_PG_ERROR,
        "sqlite_path": DB_PATH if active_engine == "SQLite" else None,
    }


def get_db_connection():
    """Returns database connection (PostgreSQL if configured and reachable, else SQLite if fallback enabled)."""
    global _USE_FALLBACK_SQLITE, _LAST_PG_ERROR
    pool = get_pg_pool()
    if pool and not _USE_FALLBACK_SQLITE:
        try:
            conn = pool.getconn()
            if conn.closed:
                pool.putconn(conn, close=True)
                conn = pool.getconn()
            return conn
        except Exception as e:
            _LAST_PG_ERROR = str(e)
            if not _allow_sqlite_fallback():
                raise
            print(f"[Central DB Warning] Pool getconn failed: {e}. Falling back to SQLite.")
            _USE_FALLBACK_SQLITE = True

    db_url = _get_database_url()
    if db_url and not _allow_sqlite_fallback():
        raise RuntimeError(f"PostgreSQL unavailable ({_LAST_PG_ERROR}) and ALLOW_SQLITE_FALLBACK=false")

    target_sqlite = os.environ.get("CENTRAL_SQLITE_PATH") or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_sqlite)), exist_ok=True)
    conn = sqlite3.connect(target_sqlite, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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


def _is_pg_conn(conn):
    return hasattr(conn, "cursor_factory") or (
        hasattr(conn, "__class__") and "psycopg2" in conn.__class__.__module__
    )


def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """Unified query executor handling parameter binding, transactions, and strict error propagation."""
    conn = get_db_connection()
    is_pg = _is_pg_conn(conn)
    cursor = None
    result = None

    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            query = query.replace("?", "%s")
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
        print(f"[Database Error] Query execution failed: {e}\nQuery: {query[:140]}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)


def _parse_timestamp(dt_val):
    if not dt_val:
        return None
    if isinstance(dt_val, datetime):
        return dt_val.replace(tzinfo=None)
    clean_str = str(dt_val).replace(" IST", "").replace("Z", "").strip()
    if "." in clean_str:
        clean_str = clean_str.split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(clean_str, fmt)
        except Exception:
            continue
    return None


def calculate_sync_latency(detected_at, reported_at):
    """
    Computes network synchronization latency (reported_at - detected_at)
    to distinguish real-time edge uploads from delayed offline backlog flushes.
    """
    dt_det = _parse_timestamp(detected_at)
    dt_rep = _parse_timestamp(reported_at)

    if not dt_det or not dt_rep:
        return {
            "latency_seconds": 0,
            "is_delayed": False,
            "latency_badge": "Real-time (< 2s sync)",
            "status_class": "latency-realtime",
        }

    diff_sec = max(0, int((dt_rep - dt_det).total_seconds()))
    is_delayed = diff_sec > 15

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
        "status_class": status_class,
    }


def _migrate_sqlite_schema(conn, cursor):
    """Safely migrates existing SQLite tables before/after schema execution."""
    # 1. Migrate detections table if it already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='detections'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(detections)")
        existing_cols = [r["name"] for r in cursor.fetchall()]

        add_cols = [
            ("event_id", "TEXT"),
            ("node_code", "TEXT DEFAULT 'NODE-01'"),
            ("edge_species", "TEXT"),
            ("edge_confidence", "REAL"),
            ("verified_species", "TEXT"),
            ("verified_confidence", "REAL"),
            ("verification_status", "TEXT DEFAULT 'PENDING'"),
            ("verification_model", "TEXT"),
            ("verification_notes", "TEXT"),
            ("verified_at", "TIMESTAMP"),
            ("bbox_json", "TEXT"),
            ("siren_status", "TEXT DEFAULT 'NOT_TRIGGERED'"),
            ("is_synced_delayed", "INTEGER DEFAULT 0"),
            ("reported_at", "TIMESTAMP"),
        ]
        for col_name, col_def in add_cols:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE detections ADD COLUMN {col_name} {col_def}")

        # Backfill legacy rows so event_id, edge_species, edge_confidence are populated
        cursor.execute("SELECT id, node_code, species, confidence, detected_at FROM detections WHERE event_id IS NULL OR event_id = ''")
        for row in cursor.fetchall():
            legacy_uid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"central-{row['node_code']}-{row['id']}-{row['detected_at']}"))
            cursor.execute(
                """
                UPDATE detections
                SET event_id = ?,
                    edge_species = COALESCE(edge_species, species),
                    edge_confidence = COALESCE(edge_confidence, confidence),
                    verification_status = COALESCE(verification_status, 'LEGACY_UNVERIFIED'),
                    reported_at = COALESCE(reported_at, detected_at)
                WHERE id = ?
                """,
                (legacy_uid, row["id"]),
            )
        conn.commit()

    # 2. Migrate camera_nodes table if it already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='camera_nodes'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(camera_nodes)")
        node_cols = [r["name"] for r in cursor.fetchall()]
        node_add_cols = [
            ("api_key", "TEXT"),
            ("ip_address", "TEXT"),
            ("firmware_version", "TEXT DEFAULT '2.0.0-edge'"),
            ("pending_queue_count", "INTEGER DEFAULT 0"),
            ("last_sync_at", "TIMESTAMP"),
        ]
        for col_name, col_def in node_add_cols:
            if col_name not in node_cols:
                cursor.execute(f"ALTER TABLE camera_nodes ADD COLUMN {col_name} {col_def}")
        conn.commit()


def _migrate_postgres_schema(conn, cursor):
    """Safely migrates existing PostgreSQL tables if upgrading from an older version."""
    pg_migrations = [
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS event_id VARCHAR(64)",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS edge_species VARCHAR(64)",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS edge_confidence DOUBLE PRECISION",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS verified_species VARCHAR(64)",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS verified_confidence DOUBLE PRECISION",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32) DEFAULT 'PENDING'",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS verification_model VARCHAR(64)",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS verification_notes TEXT",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS bbox_json TEXT",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS siren_status VARCHAR(32) DEFAULT 'NOT_TRIGGERED'",
        "ALTER TABLE detections ADD COLUMN IF NOT EXISTS is_synced_delayed INTEGER DEFAULT 0",
        "ALTER TABLE camera_nodes ADD COLUMN IF NOT EXISTS api_key VARCHAR(128)",
        "ALTER TABLE camera_nodes ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)",
        "ALTER TABLE camera_nodes ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(32) DEFAULT '2.0.0-edge'",
        "ALTER TABLE camera_nodes ADD COLUMN IF NOT EXISTS pending_queue_count INTEGER DEFAULT 0",
        "ALTER TABLE camera_nodes ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP",
    ]
    for stmt in pg_migrations:
        try:
            cursor.execute(stmt)
        except Exception:
            conn.rollback()
    conn.commit()


def init_db():
    """Initializes central database schema and runs safe migrations."""
    conn = get_db_connection()
    is_pg = _is_pg_conn(conn)
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
            _migrate_postgres_schema(conn, cursor)
        else:
            cursor = conn.cursor()
            _migrate_sqlite_schema(conn, cursor)
            conn.executescript(script)
            _migrate_sqlite_schema(conn, cursor)
            conn.commit()

        # Seed default registered edge node NODE-01 as OFFLINE if camera_nodes is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM camera_nodes")
        row = cursor.fetchone()
        cnt = row["cnt"] if isinstance(row, dict) else row[0]
        if cnt == 0:
            default_lat = float(os.environ.get("DEFAULT_LATITUDE", "21.1458"))
            default_lon = float(os.environ.get("DEFAULT_LONGITUDE", "79.0882"))
            seed_nodes = [
                (
                    "NODE-01",
                    "Tadoba North Perimeter Unit",
                    "Sector 1 (Buffer Zone)",
                    default_lat,
                    default_lon,
                    "Raspberry Pi 3B+ Optical/IR Camera",
                    0,
                    0,
                    100,
                    "OFFLINE",
                )
            ]
            sql = (
                """
                INSERT INTO camera_nodes
                (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status, last_heartbeat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """
                if is_pg
                else """
                INSERT INTO camera_nodes
                (node_code, node_name, sector, latitude, longitude, camera_type, has_rotator, rotator_heading, battery_pct, status, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """
            )
            cursor.executemany(sql, seed_nodes)
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


def get_detection_by_event_id(event_id):
    """Fetches an existing detection record by its unique event_id (for duplicate prevention)."""
    if not event_id:
        return None
    return execute_query(
        "SELECT * FROM detections WHERE event_id = ?",
        (str(event_id).strip(),),
        fetchone=True,
    )


def log_synced_detection(
    event_id,
    species,
    scientific_name,
    confidence,
    threat_level,
    lat,
    lon,
    distance_m,
    heading,
    img_path,
    node_code="NODE-01",
    detected_at=None,
    edge_species=None,
    edge_confidence=None,
    verified_species=None,
    verified_confidence=None,
    verification_status="VERIFIED",
    verification_model=None,
    verification_notes=None,
    bbox_json=None,
    siren_status="NOT_TRIGGERED",
):
    """
    Idempotently records an edge-synced detection event and its central verification outcome.
    Returns (detection_id, is_duplicate).
    Never silently discards events on database error.
    """
    event_uid = str(event_id).strip() if event_id else str(uuid.uuid4())
    existing = get_detection_by_event_id(event_uid)
    if existing:
        return existing["id"], True

    edge_sp = edge_species or species
    edge_conf = float(edge_confidence if edge_confidence is not None else confidence)
    final_sp = verified_species or species
    final_conf = float(verified_confidence if verified_confidence is not None else confidence)
    bbox_str = json.dumps(bbox_json) if bbox_json is not None and not isinstance(bbox_json, str) else bbox_json

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    det_ts = detected_at or now_str
    latency_info = calculate_sync_latency(det_ts, now_str)
    is_delayed_flag = 1 if latency_info["is_delayed"] else 0

    sql = """
        INSERT INTO detections
        (event_id, node_code, species, scientific_name, confidence,
         edge_species, edge_confidence, verified_species, verified_confidence,
         verification_status, verification_model, verification_notes, verified_at,
         threat_level, latitude, longitude, distance_meters, rotator_heading,
         bbox_json, image_snapshot_path, siren_status, is_synced_delayed,
         detected_at, reported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        event_uid,
        node_code,
        final_sp,
        scientific_name,
        final_conf,
        edge_sp,
        edge_conf,
        verified_species,
        verified_confidence,
        verification_status,
        verification_model,
        verification_notes,
        now_str if verification_status != "PENDING" else None,
        threat_level,
        float(lat),
        float(lon),
        int(distance_m or 0),
        int(heading or 0),
        bbox_str,
        img_path,
        siren_status,
        is_delayed_flag,
        det_ts,
        now_str,
    )
    try:
        det_id = execute_query(sql, params, commit=True)
        return det_id, False
    except Exception as e:
        # Handle concurrent duplicate race condition gracefully
        existing_after = get_detection_by_event_id(event_uid)
        if existing_after:
            return existing_after["id"], True
        raise e


def update_detection_siren_status(event_id, siren_status):
    """Updates the siren_status column on a detection record."""
    return execute_query(
        "UPDATE detections SET siren_status = ? WHERE event_id = ?",
        (siren_status, str(event_id)),
        commit=True,
    )


def get_siren_alert_by_event_id(event_id):
    """Returns existing siren activation record for event_id to prevent duplicate triggers."""
    if not event_id:
        return None
    return execute_query(
        "SELECT * FROM siren_alerts WHERE event_id = ?",
        (str(event_id).strip(),),
        fetchone=True,
    )


def record_siren_alert(
    event_id,
    detection_id,
    node_code,
    species,
    verified_confidence,
    policy_decision,
    siren_mode,
    command_status,
    physical_siren_active=0,
    controller_url=None,
    ack_payload=None,
    error_message=None,
    acknowledged_at=None,
):
    """
    Records a siren activation decision/command/acknowledgement in siren_alerts
    and synchronizes detections.siren_status.
    """
    existing = get_siren_alert_by_event_id(event_id)
    ack_str = json.dumps(ack_payload) if ack_payload is not None and not isinstance(ack_payload, str) else ack_payload

    if existing:
        execute_query(
            """
            UPDATE siren_alerts
            SET policy_decision = ?,
                siren_mode = ?,
                command_status = ?,
                physical_siren_active = ?,
                controller_url = ?,
                ack_payload = ?,
                error_message = ?,
                acknowledged_at = COALESCE(?, acknowledged_at)
            WHERE event_id = ?
            """,
            (
                policy_decision,
                siren_mode,
                command_status,
                int(bool(physical_siren_active)),
                controller_url,
                ack_str,
                error_message,
                acknowledged_at,
                str(event_id),
            ),
            commit=True,
        )
        update_detection_siren_status(event_id, command_status)
        return existing["id"]

    alert_id = execute_query(
        """
        INSERT INTO siren_alerts
        (event_id, detection_id, node_code, species, verified_confidence,
         policy_decision, siren_mode, command_status, physical_siren_active,
         controller_url, ack_payload, error_message, triggered_at, acknowledged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        (
            str(event_id),
            detection_id,
            node_code,
            species,
            float(verified_confidence or 0.0),
            policy_decision,
            siren_mode,
            command_status,
            int(bool(physical_siren_active)),
            controller_url,
            ack_str,
            error_message,
            acknowledged_at,
        ),
        commit=True,
    )
    update_detection_siren_status(event_id, command_status)
    return alert_id


def get_recent_siren_alerts(limit=30):
    """Returns recent siren alert activation history."""
    return execute_query(
        "SELECT * FROM siren_alerts ORDER BY id DESC LIMIT ?",
        (limit,),
        fetchall=True,
    ) or []


def update_node_heartbeat(
    node_code,
    battery_pct=None,
    heading=None,
    status="ONLINE_ACTIVE",
    lat=None,
    lon=None,
    pending_queue_count=None,
    ip_address=None,
    firmware_version=None,
    mark_synced=False,
):
    """Updates edge device telemetry from heartbeat or sync upload, auto-registering if unknown."""
    conn = get_db_connection()
    is_pg = _is_pg_conn(conn)
    cursor = None
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cursor = conn.cursor()

        check_sql = "SELECT id FROM camera_nodes WHERE node_code = %s" if is_pg else "SELECT id FROM camera_nodes WHERE node_code = ?"
        cursor.execute(check_sql, (node_code,))
        row = cursor.fetchone()
        ph = "%s" if is_pg else "?"

        if row:
            updates = [f"status = {ph}", f"last_heartbeat = {ph}"]
            params = [status, now_str]
            if mark_synced:
                updates.append(f"last_sync_at = {ph}")
                params.append(now_str)
            if battery_pct is not None:
                updates.append(f"battery_pct = {ph}")
                params.append(int(battery_pct))
            if heading is not None:
                updates.append(f"rotator_heading = {ph}")
                params.append(int(heading))
            if lat is not None and lon is not None:
                updates.append(f"latitude = {ph}")
                params.append(float(lat))
                updates.append(f"longitude = {ph}")
                params.append(float(lon))
            if pending_queue_count is not None:
                updates.append(f"pending_queue_count = {ph}")
                params.append(int(pending_queue_count))
            if ip_address is not None:
                updates.append(f"ip_address = {ph}")
                params.append(str(ip_address))
            if firmware_version is not None:
                updates.append(f"firmware_version = {ph}")
                params.append(str(firmware_version))

            params.append(node_code)
            sql = f"UPDATE camera_nodes SET {', '.join(updates)} WHERE node_code = {ph}"
            cursor.execute(sql, params)
        else:
            default_lat = float(lat if lat is not None else os.environ.get("DEFAULT_LATITUDE", "21.1458"))
            default_lon = float(lon if lon is not None else os.environ.get("DEFAULT_LONGITUDE", "79.0882"))
            ins_sql = f"""
                INSERT INTO camera_nodes
                (node_code, node_name, sector, latitude, longitude, camera_type,
                 has_rotator, rotator_heading, battery_pct, status, pending_queue_count,
                 ip_address, firmware_version, last_sync_at, last_heartbeat)
                VALUES ({', '.join([ph] * 15)})
            """
            cursor.execute(
                ins_sql,
                (
                    node_code,
                    f"Edge Unit {node_code}",
                    "Forest Perimeter Sector",
                    default_lat,
                    default_lon,
                    "Raspberry Pi 3B+ Optical/IR Camera",
                    0,
                    int(heading or 0),
                    int(battery_pct if battery_pct is not None else 100),
                    status,
                    int(pending_queue_count or 0),
                    ip_address,
                    firmware_version or "2.0.0-edge",
                    now_str if mark_synced else None,
                    now_str,
                ),
            )
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[Heartbeat Update Error] {e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)


def get_recent_detections(limit=30, verified_only=False):
    """Gets recent sightings enriched with sync latency and central verification telemetry."""
    if verified_only:
        sql = "SELECT * FROM detections WHERE verification_status = 'VERIFIED' ORDER BY id DESC LIMIT ?"
    else:
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


def get_camera_nodes(heartbeat_timeout_sec=60):
    """
    Returns all registered edge camera nodes with dynamically computed connectivity state
    based on actual heartbeat freshness (never hardcoded).
    """
    rows = execute_query("SELECT * FROM camera_nodes ORDER BY id ASC", fetchall=True) or []
    now_dt = datetime.now()

    for node in rows:
        hb_dt = _parse_timestamp(node.get("last_heartbeat"))
        sync_dt = _parse_timestamp(node.get("last_sync_at"))

        if hb_dt:
            age_sec = max(0, int((now_dt - hb_dt).total_seconds()))
            is_online = age_sec <= heartbeat_timeout_sec
            node["heartbeat_age_seconds"] = age_sec
            node["status"] = "ONLINE_ACTIVE" if is_online else "OFFLINE"
            node["is_online"] = is_online
        else:
            node["heartbeat_age_seconds"] = None
            node["status"] = "OFFLINE"
            node["is_online"] = False

        if sync_dt:
            node["sync_age_seconds"] = max(0, int((now_dt - sync_dt).total_seconds()))
        else:
            node["sync_age_seconds"] = None

    return rows


def register_camera_node(
    node_code,
    node_name,
    sector,
    lat,
    lon,
    camera_type="Raspberry Pi 3B+ Optical/IR Camera",
    api_key=None,
):
    """Registers a new edge camera node idempotently (starts OFFLINE until it connects)."""
    existing = execute_query(
        "SELECT id FROM camera_nodes WHERE node_code = ?",
        (node_code,),
        fetchone=True,
    )
    if existing:
        execute_query(
            """
            UPDATE camera_nodes
            SET node_name = ?, sector = ?, latitude = ?, longitude = ?, camera_type = ?
            WHERE node_code = ?
            """,
            (node_name, sector, float(lat), float(lon), camera_type, node_code),
            commit=True,
        )
        return existing["id"]

    sql = """
        INSERT INTO camera_nodes
        (node_code, node_name, sector, latitude, longitude, camera_type,
         has_rotator, rotator_heading, battery_pct, status, api_key, last_heartbeat)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 100, 'OFFLINE', ?, NULL)
    """
    return execute_query(sql, (node_code, node_name, sector, float(lat), float(lon), camera_type, api_key), commit=True)


def update_node_location(node_code, lat, lon):
    """Updates latitude and longitude coordinates of a camera node."""
    sql = "UPDATE camera_nodes SET latitude = ?, longitude = ? WHERE node_code = ?"
    return execute_query(sql, (float(lat), float(lon), node_code), commit=True)


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
    """Synchronizes central database contacts to local edge SQLite database if colocated."""
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
                (c["id"], c["full_name"], c["phone_number"], c["village_name"], c["role"], c.get("is_active", 1)),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Contact Sync Warning] Could not sync contacts to edge.db: {e}")


def log_system_event(event_type, message):
    """Records a system audit log entry in central DB."""
    return execute_query(
        "INSERT INTO system_logs (event_type, message) VALUES (?, ?)",
        (event_type, message),
        commit=True,
    )


def get_recent_system_logs(limit=30):
    """Fetches recent system audit logs."""
    return execute_query(
        "SELECT * FROM system_logs ORDER BY id DESC LIMIT ?",
        (limit,),
        fetchall=True,
    ) or []


# ==============================================================================
# SMS RETRY ENGINE - CENTRAL LAYER (PostgreSQL & SQLite)
# ==============================================================================

def queue_offline_alert(detection_id=None, phone="", message="", name="Villager", max_retries=3, error_msg=None, recipient_name=None):
    if recipient_name:
        name = recipient_name
    sql = """
        INSERT INTO alert_fallback_queue
        (detection_id, recipient_phone, recipient_name, alert_message, status, retry_count, max_retries, next_retry_at, last_error)
        VALUES (?, ?, ?, ?, 'QUEUED_OFFLINE', 0, ?, CURRENT_TIMESTAMP, ?)
    """
    return execute_query(sql, (detection_id, phone, name, message, max_retries, error_msg), commit=True)


def get_pending_offline_alerts(limit=10):
    conn = get_db_connection()
    is_pg = _is_pg_conn(conn)
    cursor = None
    alerts = []

    try:
        if is_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "UPDATE alert_fallback_queue SET status = 'QUEUED_OFFLINE' WHERE status = 'PROCESSING' AND created_at < NOW() - INTERVAL '120 seconds'"
            )
            cursor.execute(
                """
                SELECT id, detection_id, recipient_phone, recipient_name, alert_message, retry_count, max_retries
                FROM alert_fallback_queue
                WHERE status = 'QUEUED_OFFLINE'
                  AND retry_count < max_retries
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
        else:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE alert_fallback_queue SET status = 'QUEUED_OFFLINE' WHERE status = 'PROCESSING' AND created_at < datetime('now', '-120 seconds')"
            )
            cursor.execute(
                """
                SELECT id, detection_id, recipient_phone, recipient_name, alert_message, retry_count, max_retries
                FROM alert_fallback_queue
                WHERE status = 'QUEUED_OFFLINE'
                  AND retry_count < max_retries
                  AND (next_retry_at IS NULL OR next_retry_at <= datetime('now'))
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()

        if rows:
            alerts = [dict(r) for r in rows]
            ids = [a["id"] for a in alerts]
            if is_pg:
                cursor.execute("UPDATE alert_fallback_queue SET status = 'PROCESSING' WHERE id = ANY(%s)", (ids,))
            else:
                placeholders = ",".join(["?"] * len(ids))
                cursor.execute(f"UPDATE alert_fallback_queue SET status = 'PROCESSING' WHERE id IN ({placeholders})", ids)

        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[SMS Retry Engine Error] Error checking pending queue: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)

    return alerts


def record_alert_retry_result(alert_id, success, error_detail=None, error_msg=None):
    if error_msg is not None and error_detail is None:
        error_detail = error_msg

    conn = get_db_connection()
    is_pg = _is_pg_conn(conn)
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
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[SMS Retry Engine Error] Error recording retry result for alert #{alert_id}: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)


def flush_offline_queue(sms_service=None):
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
            else:
                success = bool(res)
                detail = "Delivered" if success else "Provider rejected SMS"
        except Exception as e:
            success = False
            detail = f"Exception during SMS dispatch: {e}"

        record_alert_retry_result(item["id"], success, detail)

        if success:
            delivered_cnt += 1
        else:
            if curr_retries + 1 >= max_limit:
                perm_failed_cnt += 1
            else:
                retrying_cnt += 1

    return {
        "processed": len(pending),
        "total_processed": len(pending),
        "delivered": delivered_cnt,
        "retrying": retrying_cnt,
        "failed_permanent": perm_failed_cnt,
    }


if __name__ == "__main__":
    init_db()
