"""
Project Indradhanu (Project C) - Main Flask Application Server
Serves the Forest Officer Tactical Dashboard & REST APIs.
"""

import os
import random
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
from database.db_manager import (
    init_db, log_detection, queue_offline_alert, flush_offline_queue, 
    get_recent_detections, get_contacts, get_camera_nodes, register_camera_node,
    update_node_heartbeat, log_synced_detection
)

app = Flask(__name__, template_folder="templates", static_folder="static")

# Ensure database tables and initial records exist on server startup
init_db()

# System in-memory state
SYSTEM_STATE = {
    "node_id": "NODE-01",
    "is_online": True,
    "battery_pct": 88,
    "solar_charging": True,
    "pir_status": "STANDBY",  # 'STANDBY', 'WAKE_ACTIVE'
    "rotator_heading": 145,
    "offline_queue_count": 0
}

@app.route("/")
def index():
    return render_template("index.html", active_page="map")

@app.route("/history")
def history_page():
    return render_template("history.html", active_page="history")

@app.route("/contacts")
def contacts_page():
    return render_template("contacts.html", active_page="contacts")

@app.route("/nodes")
def nodes_page():
    return render_template("nodes.html", active_page="nodes")

@app.route("/system")
def system_page():
    nodes = get_camera_nodes()
    return render_template("system.html", active_page="system", nodes=nodes)

@app.route("/api/nodes", methods=["GET", "POST"])
def manage_nodes():
    if request.method == "POST":
        data = request.get_json() or {}
        node_code = data.get("node_code", f"NODE-0{random.randint(4, 9)}")
        node_name = data.get("node_name", "Perimeter Station")
        sector = data.get("sector", "Sector 1")
        lat = float(data.get("latitude", 21.1450))
        lon = float(data.get("longitude", 79.0880))
        cam_type = data.get("camera_type", "Thermal IR (MLX90640)")
        
        node_id = register_camera_node(node_code, node_name, sector, lat, lon, cam_type)
        return jsonify({"success": True, "node_id": node_id, "message": "Node deployed successfully"})
    
    nodes = get_camera_nodes()
    return jsonify({"success": True, "nodes": nodes})

@app.route("/api/nodes/<node_code>/diagnostics", methods=["GET", "POST"])
def node_diagnostics(node_code):
    nodes = get_camera_nodes()
    matched = next((n for n in nodes if n["node_code"] == node_code), None)
    if not matched:
        return jsonify({"success": False, "message": f"Node {node_code} not found"}), 404
        
    battery = matched.get("battery_pct", 88)
    diagnostics = {
        "node_code": node_code,
        "node_name": matched.get("node_name"),
        "sector": matched.get("sector"),
        "status": matched.get("status", "ONLINE_ACTIVE"),
        "latitude": matched.get("latitude"),
        "longitude": matched.get("longitude"),
        "thermal_sensor": {
            "model": matched.get("camera_type", "Thermal IR (MLX90640)"),
            "status": "OPERATIONAL",
            "bus": "I2C Fast Mode (400 kHz)",
            "core_temp_c": round(30.8 + random.random() * 2.8, 1),
            "frame_rate": "16 Hz",
            "active_pixels": "768 / 768 (100% OK)",
            "noise_equivalent_temp_diff": "0.1°C (Optimal)"
        },
        "rotator": {
            "status": "CALIBRATED & READY",
            "current_bearing": matched.get("rotator_heading", 145),
            "sweep_limits": "0° to 360° Continuous",
            "servo_supply_v": "5.04V",
            "step_precision": "0.45°",
            "gear_backlash": "< 0.15°"
        },
        "pir_interrupt": {
            "gpio_pin": 18,
            "status": "ARMED & WARM",
            "trigger_mode": "RISING_EDGE (Hardware IRQ)",
            "wake_to_infer_latency_ms": random.randint(172, 194),
            "false_positives_24h": 0
        },
        "power": {
            "battery_pct": battery,
            "voltage": round(12.2 + (battery / 100.0) * 1.0, 2),
            "solar_input_v": round(18.1 + random.random() * 0.6, 1),
            "solar_charging": True if battery < 98 else False,
            "power_draw_w": round(2.6 + random.random() * 0.4, 1),
            "estimated_autonomy_hrs": 72
        },
        "comm_link": {
            "primary": "GSM 4G LTE (Quectel EC25)",
            "offline_channel": "LoRa 868MHz Fallback",
            "signal_rssi_dbm": random.randint(-72, -60),
            "roundtrip_latency_ms": random.randint(26, 42),
            "packet_loss_pct": 0.0
        },
        "overall_health": "OPTIMAL (100%)",
        "last_diagnostic_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    }
    return jsonify({"success": True, "diagnostics": diagnostics})

@app.route("/api/nodes/<node_code>/calibrate", methods=["POST"])
def calibrate_node(node_code):
    nodes = get_camera_nodes()
    matched = next((n for n in nodes if n["node_code"] == node_code), None)
    if not matched:
        return jsonify({"success": False, "message": f"Node {node_code} not found"}), 404
    return jsonify({
        "success": True, 
        "node_code": node_code,
        "message": f"Pan-Tilt zero-point bearing calibrated for {node_code}.",
        "heading": matched.get("rotator_heading", 145)
    })

@app.route("/api/system/status")
def system_status():
    return jsonify({
        "success": True,
        "state": SYSTEM_STATE,
        "server_time": datetime.now().strftime("%H:%M:%S")
    })

@app.route("/api/offline/toggle", methods=["POST"])
def toggle_offline():
    SYSTEM_STATE["is_online"] = not SYSTEM_STATE["is_online"]
    flushed_count = 0
    if SYSTEM_STATE["is_online"]:
        # If back online, flush SQLite fallback queue
        flushed_count = flush_offline_queue()
        SYSTEM_STATE["offline_queue_count"] = 0
    
    return jsonify({
        "success": True,
        "is_online": SYSTEM_STATE["is_online"],
        "flushed_count": flushed_count
    })

@app.route("/api/rotator/heading", methods=["POST"])
def set_rotator_heading():
    data = request.get_json() or {}
    angle = int(data.get("heading", 145))
    SYSTEM_STATE["rotator_heading"] = angle % 360
    return jsonify({
        "success": True,
        "heading": SYSTEM_STATE["rotator_heading"]
    })

@app.route("/api/detections", methods=["GET"])
def list_detections():
    node_filter = request.args.get("node_code")
    detections = get_recent_detections(limit=30)
    if node_filter and node_filter != "ALL":
        detections = [d for d in detections if d.get("node_code") == node_filter]
    return jsonify({
        "success": True,
        "count": len(detections),
        "detections": detections
    })

@app.route("/api/sync/detection", methods=["POST"])
def sync_detection():
    """Endpoint for edge camera stations to push detections."""
    data = request.get_json() or {}
    species = data.get("species", "Tiger")
    scientific_name = data.get("scientific_name", "Panthera tigris")
    confidence = float(data.get("confidence", 90.0))
    threat_level = data.get("threat_level", "CRITICAL")
    lat = float(data.get("latitude", 21.1458))
    lon = float(data.get("longitude", 79.0882))
    distance_m = int(data.get("distance_meters", 300))
    heading = int(data.get("rotator_heading", 145))
    img_path = data.get("image_snapshot_path", "/static/snapshots/tiger_sample.jpg")
    node_code = data.get("node_code", "NODE-01")
    detected_at = data.get("detected_at")

    det_id = log_synced_detection(
        species, scientific_name, confidence, threat_level,
        lat, lon, distance_m, heading, img_path, node_code, detected_at
    )
    return jsonify({
        "success": True,
        "detection_id": det_id,
        "reported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": f"Detection from {node_code} ingested into Central HQ."
    }), 201

@app.route("/api/sync/heartbeat", methods=["POST"])
def sync_heartbeat():
    """Endpoint for edge camera stations to report station telemetry."""
    data = request.get_json() or {}
    node_code = data.get("node_code", "NODE-01")
    battery = data.get("battery_pct")
    heading = data.get("rotator_heading")
    status = data.get("status", "ONLINE_ACTIVE")
    lat = data.get("latitude")
    lon = data.get("longitude")

    update_node_heartbeat(node_code, battery, heading, status, lat, lon)
    return jsonify({"success": True, "message": f"Heartbeat recorded for {node_code}"})

@app.route("/api/detections/simulate", methods=["POST"])
def simulate_detection():
    data = request.get_json() or {}
    node_code = data.get("node_code") or SYSTEM_STATE.get("node_id", "NODE-01")
    if node_code == "ALL":
        node_code = random.choice(["NODE-01", "NODE-02", "NODE-03"])

    # Coordinate mapping per node
    node_coords = {
        "NODE-01": (21.1458, 79.0882, 145),
        "NODE-02": (21.1410, 79.0940, 210),
        "NODE-03": (21.1495, 79.0790, 90)
    }
    base_lat, base_lon, default_heading = node_coords.get(node_code, (21.1440, 79.0870, 145))

    species_pool = [
        ("Tiger", "Panthera tigris", "CRITICAL", "/static/snapshots/tiger_sample.jpg"),
        ("Leopard", "Panthera pardus", "CRITICAL", "/static/snapshots/leopard_sample.jpg"),
        ("Indian Sloth Bear", "Melursus ursinus", "HIGH", "/static/snapshots/bear_sample.jpg"),
        ("Lion", "Panthera leo persica", "CRITICAL", "/static/snapshots/lion_sample.jpg")
    ]
    
    choice = random.choice(species_pool)
    species, sci_name, threat, img = choice
    
    lat = base_lat + (random.random() - 0.5) * 0.003
    lon = base_lon + (random.random() - 0.5) * 0.003
    conf = round(88.0 + random.random() * 10, 1)
    dist = random.randint(180, 420)
    heading = default_heading
    now = datetime.now()
    det_time = now.strftime("%Y-%m-%d %H:%M:%S IST")
    rep_time = now.strftime("%Y-%m-%d %H:%M:%S IST")
    
    det_id = log_detection(species, sci_name, conf, threat, lat, lon, dist, heading, img, node_code)
    
    # Check if network is offline
    sms_status = "DELIVERED"
    if not SYSTEM_STATE["is_online"]:
        sms_status = "QUEUED_OFFLINE"
        SYSTEM_STATE["offline_queue_count"] += 1
        contacts = get_contacts()
        for c in contacts:
            msg = f"EMERGENCY WARNING: {species} detected near village perimeter. Stay indoors!"
            queue_offline_alert(det_id, c["phone_number"], msg)
            
    return jsonify({
        "success": True,
        "detection": {
            "id": det_id,
            "species": species,
            "scientific": sci_name,
            "threat_level": threat,
            "confidence": conf,
            "latitude": lat,
            "longitude": lon,
            "distance_meters": dist,
            "image_path": img,
            "sms_status": sms_status,
            "time": det_time,
            "detected_at": det_time,
            "reported_at": rep_time,
            "node_code": node_code
        }
    })

@app.route("/api/contacts", methods=["GET"])
def list_contacts():
    contacts = get_contacts()
    return jsonify({"success": True, "contacts": contacts})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(" PROJECT INDRADHANU (PROJECT C) - MONITORING STATION")
    print(f" Dashboard: http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=True)
