"""
Project Indradhanu - Central Coordination Server & Verification Dashboard
Single coordination point for registered forest edge devices:
1. Authenticated ingestion of edge detections & snapshots (/api/sync/detection, /api/sync/heartbeat)
2. Separate Central AI Verification model (EfficientNet-B0 + YOLOv8 spatial verifier) running exclusively on edge snapshots
3. Policy-driven Village Siren activation & acknowledgement tracking (/api/siren/*)
4. Multi-device connectivity, synchronization latency, and PostgreSQL persistence
"""

import os
import sys
import time
import uuid
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from werkzeug.utils import secure_filename

os.environ["OPENCV_LOG_LEVEL"] = "FATAL"

from database.db_manager import (
    init_db,
    get_db_status,
    get_detection_by_event_id,
    log_synced_detection,
    calculate_sync_latency,
    get_recent_detections,
    get_camera_nodes,
    register_camera_node,
    update_node_heartbeat,
    update_node_location,
    get_contacts,
    add_contact,
    update_contact,
    delete_contact,
    queue_offline_alert,
    flush_offline_queue,
    get_pending_offline_alerts,
    get_recent_siren_alerts,
    get_siren_alert_by_event_id,
    log_system_event,
)
from database.system_config import load_system_config, save_system_config
from edge.services.sms_service import SMSService
from ml_engine.detector import IndradhanuDetector
from ml_engine.verifier import CentralVerificationEngine
from services.siren_service import SirenService

app = Flask(__name__, template_folder="templates", static_folder="static")

# Initialize Central Database Schema & Safe Migrations
init_db()

# Initialize Central AI Verification Engine (Separate from Edge AI)
central_verifier = CentralVerificationEngine.get_instance()
edge_detector_info = IndradhanuDetector.get_instance()
siren_service = SirenService.get_instance()
sms_gateway = SMSService()


def _get_configured_edge_api_key():
    cfg = load_system_config()
    return (
        os.environ.get("EDGE_API_KEY")
        or os.environ.get("EDGE_SHARED_API_KEY")
        or cfg.get("edge_api_key", "indradhanu-edge-secret-key-2026")
    ).strip()


def _authenticate_edge_request(payload_dict=None):
    """
    Validates X-API-Key and extracts X-Device-ID for edge device requests.
    Returns (is_valid, node_code, error_message).
    """
    payload_dict = payload_dict or {}
    provided_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
        or payload_dict.get("api_key")
        or ""
    ).strip()
    expected_key = _get_configured_edge_api_key()

    node_code = (
        request.headers.get("X-Device-ID")
        or payload_dict.get("node_code")
        or "NODE-01"
    ).strip()

    if not provided_key or provided_key != expected_key:
        return False, node_code, "Unauthorized edge device: invalid or missing X-API-Key."
    return True, node_code, None


# ==============================================================================
# HTML DASHBOARD ROUTES (No local camera / webcam pages)
# ==============================================================================

@app.route("/")
def index():
    return render_template("index.html", active_page="map")


@app.route("/history")
def history_page():
    return render_template("history.html", active_page="history")


@app.route("/nodes")
def nodes_page():
    return render_template("nodes.html", active_page="nodes")


@app.route("/contacts")
def contacts_page():
    return render_template("contacts.html", active_page="contacts")


@app.route("/system")
def system_page():
    nodes = get_camera_nodes()
    return render_template("system.html", active_page="system", nodes=nodes)


# ==============================================================================
# AUTHENTICATED EDGE DEVICE SYNCHRONIZATION APIS
# ==============================================================================

@app.route("/api/sync/heartbeat", methods=["POST"])
def sync_heartbeat():
    """Authenticated endpoint for registered edge devices to report connectivity and queue status."""
    data = request.get_json(silent=True) or {}
    is_auth, node_code, err = _authenticate_edge_request(data)
    if not is_auth:
        return jsonify({"success": False, "error": err}), 401

    battery = data.get("battery_pct")
    heading = data.get("rotator_heading")
    status = data.get("status", "ONLINE_ACTIVE")
    lat = data.get("latitude")
    lon = data.get("longitude")
    pending_queue = data.get("pending_queue_count", 0)
    firmware = data.get("firmware_version")
    ip_addr = request.remote_addr

    update_node_heartbeat(
        node_code=node_code,
        battery_pct=battery,
        heading=heading,
        status=status,
        lat=lat,
        lon=lon,
        pending_queue_count=pending_queue,
        ip_address=ip_addr,
        firmware_version=firmware,
        mark_synced=False,
    )
    return jsonify({
        "success": True,
        "node_code": node_code,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": f"Authenticated heartbeat recorded for {node_code}",
    })


@app.route("/api/sync/detection", methods=["POST"])
def sync_detection():
    """
    Authenticated endpoint for edge camera stations to upload detection events and snapshots.
    Workflow:
    1. Authenticate edge device (X-Device-ID, X-API-Key).
    2. Check event_id idempotency (prevent duplicate events & duplicate siren commands).
    3. Save uploaded edge snapshot to static/snapshots/.
    4. Run separate Central AI Verification model (EfficientNet-B0 + YOLOv8 spatial verifier) on the snapshot.
    5. Persist verified/rejected event to PostgreSQL (or SQLite fallback).
    6. Evaluate Siren Alert Policy and trigger/record Village Siren command.
    7. Dispatch emergency SMS alerts if verified.
    """
    if request.form:
        data = request.form.to_dict()
    else:
        data = request.get_json(silent=True) or {}

    is_auth, node_code, err = _authenticate_edge_request(data)
    if not is_auth:
        return jsonify({"success": False, "error": err}), 401

    event_id = (data.get("event_id") or "").strip() or str(uuid.uuid4())

    # 1. Duplicate event check (Idempotent handling)
    existing_det = get_detection_by_event_id(event_id)
    if existing_det:
        existing_siren = get_siren_alert_by_event_id(event_id)
        update_node_heartbeat(
            node_code=node_code,
            status="ONLINE_ACTIVE",
            ip_address=request.remote_addr,
            mark_synced=True,
        )
        return jsonify({
            "success": True,
            "duplicate_prevented": True,
            "event_id": event_id,
            "detection_id": existing_det["id"],
            "verification_status": existing_det.get("verification_status"),
            "verified_species": existing_det.get("verified_species"),
            "verified_confidence": existing_det.get("verified_confidence"),
            "siren_status": existing_det.get("siren_status"),
            "siren_alert": existing_siren,
            "message": f"Duplicate event {event_id} already processed; skipped re-insertion and duplicate siren trigger.",
        }), 200

    edge_species = data.get("species", "Unknown")
    scientific_name = data.get("scientific_name", "")
    edge_confidence = float(data.get("confidence", 0.0))
    threat_level = data.get("threat_level", "CRITICAL")
    lat = float(data.get("latitude", 21.1458))
    lon = float(data.get("longitude", 79.0882))
    distance_m = int(data.get("distance_meters", 280))
    heading = int(data.get("rotator_heading", 145))
    bbox_json = data.get("bbox_json")
    detected_at = data.get("detected_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Save uploaded snapshot from edge device
    upload_dir = Path(__file__).resolve().parent / "static" / "snapshots"
    upload_dir.mkdir(parents=True, exist_ok=True)
    disk_snapshot_path = None
    web_snapshot_path = None

    if "snapshot" in request.files:
        snap_file = request.files["snapshot"]
        if snap_file and snap_file.filename:
            safe_evt = secure_filename(event_id)[:36]
            safe_name = f"edge_{safe_evt}_{secure_filename(snap_file.filename)}"
            dest = upload_dir / safe_name
            snap_file.save(str(dest))
            disk_snapshot_path = str(dest)
            web_snapshot_path = f"/static/snapshots/{safe_name}"
    elif data.get("image_snapshot_path"):
        candidate = Path(data["image_snapshot_path"])
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parent / data["image_snapshot_path"].lstrip("/\\")
        if candidate.exists() and candidate.is_file():
            disk_snapshot_path = str(candidate)
            web_snapshot_path = data["image_snapshot_path"]

    # 3. Run Central AI Verification Model exclusively on the edge-submitted snapshot
    cfg = load_system_config()
    verify_thresh = float(
        os.environ.get("CENTRAL_VERIFY_CONF_THRESHOLD", cfg.get("central_verify_conf_threshold", 60.0))
    )
    verification = central_verifier.verify_edge_snapshot(
        image_path=disk_snapshot_path,
        edge_species=edge_species,
        edge_confidence=edge_confidence,
        event_id=event_id,
        verify_threshold=verify_thresh,
        save_annotated=True,
    )

    final_web_img = verification.get("web_snapshot_path") or web_snapshot_path
    final_species = verification["verified_species"] if verification["is_verified"] else edge_species
    final_scientific = verification["scientific_name"] if verification["is_verified"] else scientific_name
    final_conf = verification["verified_confidence"] if verification["is_verified"] else edge_confidence

    # 4. Persist to Central Database (PostgreSQL / SQLite fallback)
    det_id, is_dup = log_synced_detection(
        event_id=event_id,
        species=final_species,
        scientific_name=final_scientific,
        confidence=final_conf,
        threat_level=threat_level if verification["is_verified"] else "UNVERIFIED",
        lat=lat,
        lon=lon,
        distance_m=distance_m,
        heading=heading,
        img_path=final_web_img,
        node_code=node_code,
        detected_at=detected_at,
        edge_species=edge_species,
        edge_confidence=edge_confidence,
        verified_species=verification["verified_species"],
        verified_confidence=verification["verified_confidence"],
        verification_status=verification["verification_status"],
        verification_model=verification["verification_model"],
        verification_notes=verification["verification_notes"],
        bbox_json=bbox_json,
        siren_status="EVALUATING",
    )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    latency_info = calculate_sync_latency(detected_at, now_str)

    # 5. Evaluate Siren Alert Policy & Trigger Village Siren Controller
    siren_outcome = siren_service.evaluate_and_trigger(
        event_id=event_id,
        detection_id=det_id,
        node_code=node_code,
        verification_result=verification,
        sync_latency_seconds=latency_info["latency_seconds"],
    )

    # 6. Update Edge Node Sync & Connectivity Telemetry
    update_node_heartbeat(
        node_code=node_code,
        heading=heading,
        status="ONLINE_ACTIVE",
        lat=lat,
        lon=lon,
        ip_address=request.remote_addr,
        mark_synced=True,
    )

    # 7. Dispatch SMS Alerts if Central Verification confirmed a target animal
    sms_reports = []
    if verification["is_verified"] and not is_dup:
        contacts = get_contacts()
        if contacts:
            try:
                _sent_cnt, failed_list, _alert_msg, sms_reports = sms_gateway.broadcast_alert(
                    contacts,
                    final_species,
                    final_scientific,
                    threat_level,
                    node_code,
                    "Perimeter Sector",
                    distance_m,
                )
                for fail in failed_list:
                    queue_offline_alert(
                        det_id,
                        fail["phone"],
                        fail["message"],
                        name=fail.get("name", "Villager"),
                        max_retries=3,
                        error_msg=fail.get("error"),
                    )
            except Exception as sms_err:
                print(f"[Central SMS Dispatch Warning] {sms_err}")

    log_system_event(
        "CENTRAL_VERIFICATION",
        f"Event {event_id} from {node_code}: Edge={edge_species} ({edge_confidence}%) -> "
        f"Central={verification['verification_status']} ({verification['verified_species']} @ {verification['verified_confidence']}%) | "
        f"Siren={siren_outcome['command_status']}",
    )

    return jsonify({
        "success": True,
        "duplicate_prevented": is_dup,
        "event_id": event_id,
        "detection_id": det_id,
        "node_code": node_code,
        "edge_species": edge_species,
        "edge_confidence": edge_confidence,
        "verification": verification,
        "siren": siren_outcome,
        "sync_latency": latency_info,
        "image_path": final_web_img,
        "reported_at": now_str,
        "sms_reports": sms_reports,
        "message": f"Event {event_id} from {node_code} processed by Central Verification AI ({verification['verification_status']}).",
    }), 201


# ==============================================================================
# DETECTIONS, VERIFICATION & LIVE POLLING APIS
# ==============================================================================

@app.route("/api/detections", methods=["GET"])
def list_detections():
    node_filter = request.args.get("node_code")
    status_filter = request.args.get("verification_status")
    limit = int(request.args.get("limit", 30))

    detections = get_recent_detections(limit=limit)
    if node_filter and node_filter != "ALL":
        detections = [d for d in detections if d.get("node_code") == node_filter]
    if status_filter and status_filter != "ALL":
        detections = [d for d in detections if d.get("verification_status") == status_filter]

    return jsonify({
        "success": True,
        "count": len(detections),
        "detections": detections,
    })


@app.route("/api/detections/latest_live", methods=["GET"])
def latest_live_detection():
    """
    Returns the most recent verified detection from the central database along with
    actual edge device connectivity and pending queue counts.
    """
    recent = get_recent_detections(limit=5)
    latest_verified = next((d for d in recent if d.get("verification_status") == "VERIFIED"), None)
    latest_any = recent[0] if recent else None
    target = latest_verified or latest_any

    latest_payload = None
    if target:
        latest_payload = {
            "id": target["id"],
            "event_id": target["event_id"],
            "species": target["species"],
            "scientific": target.get("scientific_name") or "",
            "confidence": target["confidence"],
            "edge_species": target.get("edge_species"),
            "edge_confidence": target.get("edge_confidence"),
            "verified_species": target.get("verified_species"),
            "verified_confidence": target.get("verified_confidence"),
            "verification_status": target.get("verification_status"),
            "verification_model": target.get("verification_model"),
            "verification_notes": target.get("verification_notes"),
            "siren_status": target.get("siren_status"),
            "threat_level": target.get("threat_level", "CRITICAL"),
            "image_path": target.get("image_snapshot_path"),
            "latitude": target.get("latitude"),
            "longitude": target.get("longitude"),
            "distance_meters": target.get("distance_meters"),
            "time": target.get("detected_at"),
            "detected_at": target.get("detected_at"),
            "reported_at": target.get("reported_at"),
            "latency_badge": target.get("latency_badge"),
            "is_delayed": target.get("is_delayed"),
            "node_code": target.get("node_code", "NODE-01"),
        }

    nodes = get_camera_nodes()
    online_nodes = [n for n in nodes if n.get("is_online")]
    pending_sms = get_pending_offline_alerts(limit=50)
    total_edge_queue = sum(int(n.get("pending_queue_count") or 0) for n in nodes)

    return jsonify({
        "success": True,
        "latest": latest_payload,
        "is_online": len(online_nodes) > 0,
        "online_nodes_count": len(online_nodes),
        "total_nodes_count": len(nodes),
        "queue_count": len(pending_sms) + total_edge_queue,
        "siren_status": siren_service.get_status(),
    })


# ==============================================================================
# SIREN CONTROLLER & ALERT POLICY APIS
# ==============================================================================

@app.route("/api/siren/status", methods=["GET"])
def api_siren_status():
    return jsonify({
        "success": True,
        "siren": siren_service.get_status(),
    })


@app.route("/api/siren/history", methods=["GET"])
def api_siren_history():
    limit = int(request.args.get("limit", 30))
    alerts = get_recent_siren_alerts(limit=limit)
    return jsonify({
        "success": True,
        "count": len(alerts),
        "alerts": alerts,
    })


@app.route("/api/siren/trigger", methods=["POST"])
def api_siren_trigger():
    """Triggers a safe test or hardware activation command on the Village Siren Controller."""
    data = request.get_json(silent=True) or {}
    node_code = data.get("node_code", "NODE-01")
    species = data.get("species", "Manual Siren Verification")
    mode = data.get("mode")
    duration = data.get("duration_sec", 10)

    outcome = siren_service.trigger_manual_or_test(
        node_code=node_code,
        species=species,
        mode_override=mode,
        duration_sec=duration,
    )
    status_code = 200 if outcome.get("triggered") else 400
    return jsonify({"success": outcome.get("triggered", False), "outcome": outcome}), status_code


@app.route("/api/siren/stop", methods=["POST"])
def api_siren_stop():
    cfg = load_system_config()
    key = os.environ.get("SIREN_API_KEY", cfg.get("siren_api_key", "indradhanu-siren-secret-key-2026"))
    res, code = siren_service.local_controller.stop(provided_key=key)
    return jsonify({"success": code == 200, "result": res}), code


@app.route("/api/siren/config", methods=["GET", "POST"])
def api_siren_config():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        updates = {}
        for k in (
            "siren_mode",
            "siren_controller_url",
            "siren_api_key",
            "siren_alert_conf_threshold",
            "siren_duration_sec",
            "siren_max_sync_delay_sec",
            "central_verify_conf_threshold",
            "edge_api_key",
        ):
            if k in data and data[k] is not None:
                updates[k] = data[k]
        cfg = save_system_config(updates)
        return jsonify({
            "success": True,
            "message": "Verification and Siren policy configuration updated.",
            "config": {
                "siren_mode": cfg.get("siren_mode"),
                "siren_controller_url": cfg.get("siren_controller_url"),
                "siren_alert_conf_threshold": cfg.get("siren_alert_conf_threshold"),
                "siren_duration_sec": cfg.get("siren_duration_sec"),
                "siren_max_sync_delay_sec": cfg.get("siren_max_sync_delay_sec"),
                "central_verify_conf_threshold": cfg.get("central_verify_conf_threshold"),
            },
        })

    cfg = load_system_config()
    return jsonify({
        "success": True,
        "config": {
            "siren_mode": cfg.get("siren_mode", "SAFE_TEST"),
            "siren_controller_url": cfg.get("siren_controller_url", ""),
            "siren_alert_conf_threshold": cfg.get("siren_alert_conf_threshold", 65.0),
            "siren_duration_sec": cfg.get("siren_duration_sec", 15),
            "siren_max_sync_delay_sec": cfg.get("siren_max_sync_delay_sec", 900),
            "central_verify_conf_threshold": cfg.get("central_verify_conf_threshold", 60.0),
        },
    })


# ==============================================================================
# MULTI-DEVICE EDGE NODE REGISTRY & TELEMETRY APIS
# ==============================================================================

@app.route("/api/nodes", methods=["GET", "POST"])
def manage_nodes():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        existing_nodes = get_camera_nodes()
        default_code = f"NODE-0{len(existing_nodes) + 1}"
        node_code = (data.get("node_code") or default_code).strip().upper()
        node_name = (data.get("node_name") or f"Edge Station {node_code}").strip()
        sector = (data.get("sector") or "Perimeter Buffer Sector").strip()
        lat = float(data.get("latitude", 21.1458))
        lon = float(data.get("longitude", 79.0882))
        cam_type = data.get("camera_type", "Raspberry Pi 3B+ Optical/IR Camera")

        node_id = register_camera_node(node_code, node_name, sector, lat, lon, cam_type)
        return jsonify({
            "success": True,
            "node_id": node_id,
            "node_code": node_code,
            "message": f"Edge device {node_code} registered (status: OFFLINE until first authenticated heartbeat).",
        }), 201

    nodes = get_camera_nodes()
    return jsonify({"success": True, "nodes": nodes})


@app.route("/api/nodes/<node_code>/diagnostics", methods=["GET", "POST"])
def node_diagnostics(node_code):
    """Returns actual database-backed telemetry for the specified edge node (zero simulated values)."""
    nodes = get_camera_nodes()
    matched = next((n for n in nodes if n["node_code"] == node_code), None)
    if not matched:
        return jsonify({"success": False, "message": f"Edge node {node_code} not found"}), 404

    node_detections = [d for d in get_recent_detections(limit=50) if d.get("node_code") == node_code]
    verified_cnt = sum(1 for d in node_detections if d.get("verification_status") == "VERIFIED")

    diagnostics = {
        "node_code": node_code,
        "node_name": matched.get("node_name"),
        "sector": matched.get("sector"),
        "status": matched.get("status", "OFFLINE"),
        "is_online": bool(matched.get("is_online")),
        "latitude": matched.get("latitude"),
        "longitude": matched.get("longitude"),
        "camera_type": matched.get("camera_type", "Raspberry Pi 3B+ Optical/IR Camera"),
        "firmware_version": matched.get("firmware_version", "2.0.0-pi3bplus"),
        "ip_address": matched.get("ip_address") or "Not connected",
        "battery_pct": matched.get("battery_pct", 0),
        "rotator_heading": matched.get("rotator_heading", 0),
        "pending_queue_count": matched.get("pending_queue_count", 0),
        "last_heartbeat": matched.get("last_heartbeat") or "Never",
        "heartbeat_age_seconds": matched.get("heartbeat_age_seconds"),
        "last_sync_at": matched.get("last_sync_at") or "Never",
        "sync_age_seconds": matched.get("sync_age_seconds"),
        "recent_detections_count": len(node_detections),
        "verified_detections_count": verified_cnt,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return jsonify({"success": True, "diagnostics": diagnostics})


# ==============================================================================
# SYSTEM STATUS, AI INFO, CONTACTS & SMS RETRY APIS
# ==============================================================================

@app.route("/api/ai/status", methods=["GET"])
def ai_status():
    return jsonify({
        "success": True,
        "central_verifier": central_verifier.get_info(),
        "edge_reference_detector": edge_detector_info.get_info(),
    })


@app.route("/api/system/status", methods=["GET"])
def system_status():
    cfg = load_system_config()
    nodes = get_camera_nodes()
    online_nodes = [n for n in nodes if n.get("is_online")]
    pending_sms = get_pending_offline_alerts(limit=50)
    total_edge_pending = sum(int(n.get("pending_queue_count") or 0) for n in nodes)
    db_info = get_db_status()
    siren_info = siren_service.get_status()

    state = {
        "node_id": nodes[0]["node_code"] if nodes else "NODE-01",
        "is_online": len(online_nodes) > 0,
        "online_nodes_count": len(online_nodes),
        "total_nodes_count": len(nodes),
        "battery_pct": online_nodes[0].get("battery_pct", 100) if online_nodes else (nodes[0].get("battery_pct", 0) if nodes else 0),
        "rotator_heading": online_nodes[0].get("rotator_heading", 145) if online_nodes else 145,
        "offline_queue_count": len(pending_sms) + total_edge_pending,
        "pending_sms_count": len(pending_sms),
        "pending_edge_events_count": total_edge_pending,
        "latitude": cfg.get("latitude", 21.1458),
        "longitude": cfg.get("longitude", 79.0882),
        "location_source": cfg.get("location_source", "DEFAULT"),
        "database": db_info,
        "central_verifier": central_verifier.get_info(),
        "siren": siren_info,
    }
    return jsonify({
        "success": True,
        "state": state,
        "nodes": nodes,
        "online_nodes": len(online_nodes),
        "total_nodes": len(nodes),
        "total_pending_edge_queue": total_edge_pending,
        "siren_controller": siren_info,
        "central_verifier_loaded": bool(central_verifier.is_loaded),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/offline/flush", methods=["POST"])
def flush_offline():
    metrics = flush_offline_queue(sms_gateway)
    pending_alerts = get_pending_offline_alerts(limit=50)
    return jsonify({
        "success": True,
        "metrics": metrics,
        "remaining_queued": len(pending_alerts),
        "message": (
            f"Processed {metrics['processed']} queued SMS alert(s): "
            f"{metrics['delivered']} delivered, {metrics['retrying']} retrying, "
            f"{metrics['failed_permanent']} permanently failed."
        ),
    })


@app.route("/api/contacts", methods=["GET", "POST"])
def manage_contacts():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("full_name") or data.get("name")
        phone = data.get("phone_number") or data.get("phone")
        village = data.get("village_name") or data.get("village", "Rampur")
        role = data.get("role", "villager")

        if not name or not phone:
            return jsonify({"success": False, "message": "Name and phone number are required"}), 400

        contact_id = add_contact(name.strip(), phone.strip(), village.strip(), role.strip())
        return jsonify({
            "success": True,
            "contact_id": contact_id,
            "message": f"Registered {name} in emergency SMS directory.",
        }), 201

    contacts = get_contacts()
    return jsonify({"success": True, "contacts": contacts})


@app.route("/api/contacts/<int:contact_id>", methods=["PUT", "DELETE"])
def modify_contact(contact_id):
    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        name = data.get("full_name") or data.get("name")
        phone = data.get("phone_number") or data.get("phone")
        village = data.get("village_name") or data.get("village", "Rampur")
        role = data.get("role", "villager")

        if not name or not phone:
            return jsonify({"success": False, "message": "Name and phone number are required"}), 400

        update_contact(contact_id, name.strip(), phone.strip(), village.strip(), role.strip())
        return jsonify({"success": True, "message": f"Updated contact #{contact_id} successfully."})

    delete_contact(contact_id)
    return jsonify({"success": True, "message": f"Deleted contact #{contact_id} from directory."})


@app.route("/api/system/location", methods=["GET", "POST"])
def system_location():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            lat = float(data["latitude"])
            lon = float(data["longitude"])
            accuracy = float(data.get("accuracy", 0.0))
            source = data.get("source", "GPS_BROWSER" if data.get("auto_gps") else "MANUAL")
            node_code = data.get("node_code", "NODE-01")

            save_system_config({
                "latitude": lat,
                "longitude": lon,
                "location_source": source,
                "location_accuracy_m": accuracy,
            })
            update_node_location(node_code, lat, lon)
            return jsonify({
                "success": True,
                "status": "ok",
                "latitude": lat,
                "longitude": lon,
                "source": source,
                "accuracy": accuracy,
                "message": f"Coordinates updated for {node_code}: {lat:.5f} N, {lon:.5f} E",
            })
        except Exception as e:
            return jsonify({"success": False, "message": f"Invalid coordinates: {e}"}), 400

    cfg = load_system_config()
    return jsonify({
        "success": True,
        "latitude": cfg.get("latitude", 21.1458),
        "longitude": cfg.get("longitude", 79.0882),
        "source": cfg.get("location_source", "DEFAULT"),
        "accuracy_m": cfg.get("location_accuracy_m", 0.0),
        "nodes": get_camera_nodes(),
    })


@app.route("/api/sms/dispatch-alert", methods=["POST"])
def manual_dispatch_sms():
    data = request.get_json(silent=True) or {}
    species = data.get("species", "Bengal Tiger")
    scientific = data.get("scientific_name", "Panthera tigris tigris")
    threat = data.get("threat_level", "CRITICAL")
    node_code = data.get("node_code", "NODE-01")
    sector = data.get("sector", "Sector 1 (Perimeter)")
    dist = int(data.get("distance_m", 280))

    contacts = get_contacts()
    if not contacts:
        return jsonify({"success": False, "message": "No emergency contacts registered in directory"}), 400

    sent_cnt, failed_list, alert_msg, reports = sms_gateway.broadcast_alert(
        contacts, species, scientific, threat, node_code, sector, dist
    )
    for fail in failed_list:
        queue_offline_alert(
            None,
            fail["phone"],
            fail["message"],
            name=fail.get("name", "Villager"),
            max_retries=3,
            error_msg=fail.get("error"),
        )

    return jsonify({
        "success": True,
        "sent_count": sent_cnt,
        "total_contacts": len(contacts),
        "failed": failed_list,
        "message": alert_msg,
        "reports": reports,
    })


@app.route("/api/sms/test", methods=["POST"])
def test_sms_dispatch():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone") or data.get("phone_number")
    if not phone:
        cfg = load_system_config()
        phone = cfg.get("test_mobile_number", "")
    if not phone:
        return jsonify({"success": False, "message": "Recipient phone number is required."}), 400

    custom_msg = data.get("message")
    res = sms_gateway.send_test_sms(phone.strip(), custom_msg)
    return jsonify({"success": res.get("success", False), "result": res})


@app.route("/api/sms/config", methods=["GET", "POST"])
def manage_sms_config():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        updates = {}
        for k in (
            "sms_mode",
            "fast2sms_api_key",
            "twilio_account_sid",
            "twilio_auth_token",
            "twilio_from_number",
            "test_mobile_number",
        ):
            if k in data and data[k] is not None:
                updates[k] = str(data[k]).strip()

        cfg = save_system_config(updates)
        sms_gateway.reload_config()
        return jsonify({
            "success": True,
            "message": "SMS Gateway settings updated.",
            "mode": cfg.get("sms_mode"),
            "has_fast2sms_key": bool(cfg.get("fast2sms_api_key")),
        })

    cfg = load_system_config()
    key = cfg.get("fast2sms_api_key", "")
    masked_key = (key[:4] + "*" * (len(key) - 8) + key[-4:]) if len(key) > 8 else ("****" if key else "")
    return jsonify({
        "success": True,
        "sms_mode": cfg.get("sms_mode", "FAST2SMS"),
        "has_fast2sms_key": bool(key),
        "fast2sms_key_masked": masked_key,
        "twilio_account_sid": cfg.get("twilio_account_sid", ""),
        "twilio_from_number": cfg.get("twilio_from_number", ""),
        "has_twilio_token": bool(cfg.get("twilio_auth_token")),
        "test_mobile_number": cfg.get("test_mobile_number", ""),
    })


def _start_central_retry_worker():
    def worker():
        while True:
            time.sleep(15)
            try:
                flush_offline_queue(sms_gateway)
            except Exception:
                pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()


_start_central_retry_worker()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 64)
    print(" PROJECT INDRADHANU - CENTRAL COORDINATION & VERIFICATION SERVER")
    print(f" Dashboard: http://127.0.0.1:{port}")
    print("=" * 64)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
