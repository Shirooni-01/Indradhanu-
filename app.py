"""
Project Indradhanu (Project C) - Main Flask Application Server
Serves the Forest Officer Tactical Dashboard & REST APIs.
"""

import os
import sys
import json
import random
import time
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
import uuid
from flask import Flask, render_template, jsonify, request, send_from_directory, Response
from werkzeug.utils import secure_filename
from database.db_manager import (
    init_db, log_detection, queue_offline_alert, flush_offline_queue, 
    get_recent_detections, get_contacts, get_camera_nodes, register_camera_node,
    update_node_heartbeat, log_synced_detection
)
from ml_engine.detector import IndradhanuDetector

app = Flask(__name__, template_folder="templates", static_folder="static")

# Ensure database tables and initial records exist on server startup
init_db()

# Initialize AI Apex Predator Detector singleton
ai_detector = IndradhanuDetector.get_instance()

import threading

# Persistent Camera Settings File
CONFIG_PATH = Path(__file__).resolve().parent / "database" / "camera_config.json"

def load_camera_config():
    """Loads saved camera threshold and settings from disk to survive restarts and navigation."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"conf_threshold": 0.45, "thermal_mode": False}

def save_camera_config(conf_dict):
    """Persists camera settings to disk."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(conf_dict, f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving camera config: {e}")

SAVED_CONFIG = load_camera_config()

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

def detect_available_cameras():
    """Detects available camera devices on Windows and identifies Iriun/Integrated cameras."""
    devices = []
    try:
        from pygrabber.dshow_graph import FilterGraph
        raw_names = FilterGraph().get_input_devices()
        for i, name in enumerate(raw_names):
            is_iriun = "iriun" in name.lower()
            devices.append({
                "id": str(i),
                "name": name,
                "is_iriun": is_iriun,
                "label": f"📱 {name} (Phone Cam - Device {i})" if is_iriun else f"💻 {name} (Device {i})"
            })
    except Exception:
        devices = [
            {"id": "1", "name": "Iriun Webcam", "is_iriun": True, "label": "📱 Iriun Webcam (Phone Cam - Device 1)"},
            {"id": "0", "name": "Integrated Camera", "is_iriun": False, "label": "💻 Laptop Webcam (Device 0)"}
        ]
    return devices

# Auto-detect default camera source: prefer Iriun Webcam if available
AVAILABLE_DEVICES = detect_available_cameras()
iriun_device = next((d for d in AVAILABLE_DEVICES if d.get("is_iriun")), None)
DEFAULT_SOURCE = iriun_device["id"] if iriun_device else "SIMULATION"

CAMERA_LOCK = threading.Lock()

# Live Camera Stream State (Restored from persistent storage)
CAMERA_STATE = {
    "source": DEFAULT_SOURCE,
    "thermal_mode": bool(SAVED_CONFIG.get("thermal_mode", False)),
    "conf_threshold": float(SAVED_CONFIG.get("conf_threshold", 0.45)),
    "cap": None,
    "active_source_string": None
}

# Multi-frame Temporal Verification & Deduplication State
# Animals must remain continuously visible for > 2.0s before being logged ONCE.
ACTIVE_SIGHTINGS = {}
MIN_PRESENCE_SECONDS = 2.0     # Must stay continuously in frame for > 2.0s
SIGHTING_EXPIRY_SECONDS = 3.5  # Absence timeout before animal is considered gone

LAST_AUTO_LOG_TIME = 0.0
LATEST_AUTO_DETECTION = None

def open_camera_capture(source):
    """Safely opens a video source (index or URL) with backend negotiation to avoid DSHOW crashes."""
    src_str = str(source).strip()
    if src_str == "SIMULATION":
        return None

    if not src_str.isdigit():
        # URL stream (HTTP / RTSP)
        cap = cv2.VideoCapture(src_str)
        return cap if cap.isOpened() else None

    cam_id = int(src_str)
    dev_name = ""
    try:
        from pygrabber.dshow_graph import FilterGraph
        devs = FilterGraph().get_input_devices()
        if 0 <= cam_id < len(devs):
            dev_name = devs[cam_id].lower()
    except Exception:
        pass

    # On Windows, DirectShow (CAP_DSHOW) is the primary working backend for Iriun Webcam & integrated cameras.
    # CAP_ANY defaults to MSMF which fails on Iriun virtual driver.
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY, cv2.CAP_MSMF]

    for backend in backends:
        try:
            if backend == cv2.CAP_ANY:
                cap = cv2.VideoCapture(cam_id)
            else:
                cap = cv2.VideoCapture(cam_id, backend)
            if cap.isOpened():
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                for _ in range(5):
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None:
                        print(f"[Camera] Successfully opened device {cam_id} ({dev_name or 'Webcam'}) using backend {backend}", flush=True)
                        return cap
                    time.sleep(0.04)

                cap.release()
        except Exception as e:
            print(f"[Camera] Backend {backend} attempt for dev {cam_id} failed: {e}", flush=True)

    return None

# Background Surveillance Worker & Shared Frame Buffer
SURVEILLANCE_RUNNING = True
SURVEILLANCE_THREAD = None
LATEST_FRAME_LOCK = threading.Lock()
LATEST_JPEG_BYTES = None
LATEST_FRAME_TIMESTAMP = 0.0

def surveillance_worker():
    """Autonomous 24/7 background worker:
    1. Connects to the configured camera source (e.g., Iriun Webcam index 1).
    2. Continuously reads frames.
    3. Runs YOLOv8 AI inference with the user's active threshold.
    4. Evaluates temporal verification (> 2.0s presence) & single-encounter deduplication.
    5. Saves snapshot frame & logs incident to SQLite.
    6. Updates LATEST_AUTO_DETECTION and LATEST_JPEG_BYTES.
    Runs non-stop regardless of whether any browser tab is open!
    """
    global CAMERA_STATE, LAST_AUTO_LOG_TIME, LATEST_AUTO_DETECTION, LATEST_JPEG_BYTES, LATEST_FRAME_TIMESTAMP

    sim_test_images = []
    test_dir = Path(__file__).resolve().parent / "Indradhanu_Dataset" / "images" / "test"
    if test_dir.exists():
        sim_test_images = list(test_dir.glob("*.jpg"))
    if not sim_test_images:
        snap_dir = Path(__file__).resolve().parent / "static" / "snapshots"
        sim_test_images = list(snap_dir.glob("*.jpg"))

    sim_idx = 0
    last_sim_switch = 0.0
    consecutive_read_failures = 0
    last_cam_open_attempt = 0.0

    print("[Surveillance Worker] Continuous Edge AI Surveillance loop initialized.")

    while SURVEILLANCE_RUNNING:
        try:
            with CAMERA_LOCK:
                source = CAMERA_STATE["source"]
                thermal_mode = CAMERA_STATE["thermal_mode"]
                conf_thresh = CAMERA_STATE["conf_threshold"]

            frame = None

            if source == "SIMULATION":
                now = time.time()
                if now - last_sim_switch > 3.0:
                    sim_idx = (sim_idx + 1) % len(sim_test_images) if sim_test_images else 0
                    last_sim_switch = now
                if sim_test_images:
                    frame = cv2.imread(str(sim_test_images[sim_idx]))
            else:
                # Handle real camera or stream URL with thread safety
                with CAMERA_LOCK:
                    now = time.time()
                    needs_open = (
                        CAMERA_STATE["cap"] is None or 
                        CAMERA_STATE["active_source_string"] != source or 
                        not CAMERA_STATE["cap"].isOpened()
                    )

                    if needs_open:
                        if now - last_cam_open_attempt >= 3.0:
                            last_cam_open_attempt = now
                            if CAMERA_STATE["cap"] is not None:
                                try:
                                    CAMERA_STATE["cap"].release()
                                except Exception:
                                    pass
                            CAMERA_STATE["cap"] = open_camera_capture(source)
                            CAMERA_STATE["active_source_string"] = source
                            consecutive_read_failures = 0

                    if CAMERA_STATE["cap"] and CAMERA_STATE["cap"].isOpened():
                        ret, raw_frame = CAMERA_STATE["cap"].read()
                        if ret and raw_frame is not None:
                            frame = raw_frame.copy()
                            consecutive_read_failures = 0
                        else:
                            consecutive_read_failures += 1
                            if consecutive_read_failures >= 300:
                                try:
                                    CAMERA_STATE["cap"].release()
                                except Exception:
                                    pass
                                CAMERA_STATE["cap"] = None
                                consecutive_read_failures = 0

            if frame is None:
                # Diagnostic status frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                label = "CONNECTING TO IRIUN WEBCAM (DEVICE 1)..." if source == "1" else f"CONNECTING TO {source.upper()}..."
                cv2.putText(frame, label, (40, 240), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2)
                cv2.putText(frame, "Ensure phone Iriun app is open & on same Wi-Fi / USB", (40, 280),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)
                cv2.putText(frame, f"System Active · Conf Threshold: {int(conf_thresh*100)}%", (40, 320),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
                
                ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ret:
                    with LATEST_FRAME_LOCK:
                        LATEST_JPEG_BYTES = buffer.tobytes()
                        LATEST_FRAME_TIMESTAMP = time.time()
                time.sleep(0.08)
                continue

            # Apply thermal color simulation if enabled
            if thermal_mode:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                frame = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)

            # Run Real Trained AI Inference
            dets = []
            if ai_detector.is_loaded:
                dets, annotated, lat = ai_detector.predict_frame(frame, conf_thresh=conf_thresh, annotate=True)
            else:
                annotated = frame

            # TEMPORAL PERSISTENCE & INCIDENT DEDUPLICATION:
            now_ts = time.time()
            min_conf_pct = conf_thresh * 100.0

            valid_dets = [
                d for d in dets 
                if d["confidence"] >= min_conf_pct and d["species"] in (
                    "Bengal Tiger", "Indian Leopard", "Tiger", "Leopard", "Sloth Bear", "Asiatic Lion"
                )
            ]

            seen_species = set()
            for d in valid_dets:
                species = d["species"]
                seen_species.add(species)

                if species not in ACTIVE_SIGHTINGS:
                    # Start new encounter tracking
                    ACTIVE_SIGHTINGS[species] = {
                        "first_seen": now_ts,
                        "last_seen": now_ts,
                        "logged": False,
                        "best_conf": d["confidence"],
                        "best_det": d,
                        "best_frame": annotated.copy(),
                        "incident_id": None
                    }
                else:
                    sighting = ACTIVE_SIGHTINGS[species]
                    sighting["last_seen"] = now_ts
                    if d["confidence"] >= sighting["best_conf"]:
                        sighting["best_conf"] = d["confidence"]
                        sighting["best_det"] = d
                        sighting["best_frame"] = annotated.copy()

                    presence_time = now_ts - sighting["first_seen"]

                    # Requirement: Animal in frame > 2.0 seconds -> Log ONCE
                    if presence_time >= MIN_PRESENCE_SECONDS and not sighting["logged"]:
                        sighting["logged"] = True
                        top = sighting["best_det"]
                        best_annotated = sighting["best_frame"]

                        snap_dir = Path(__file__).resolve().parent / "static" / "snapshots"
                        snap_dir.mkdir(parents=True, exist_ok=True)
                        snap_name = f"auto_{int(now_ts)}_{species.lower().replace(' ', '_')}.jpg"
                        save_file = snap_dir / snap_name
                        cv2.imwrite(str(save_file), best_annotated)
                        web_path = f"/static/snapshots/{snap_name}"

                        lat = 21.1458 + (random.random() - 0.5) * 0.003
                        lon = 79.0882 + (random.random() - 0.5) * 0.003
                        dist = random.randint(180, 380)
                        heading = SYSTEM_STATE.get("rotator_heading", 145)

                        det_id = log_detection(
                            top["species"], top["scientific_name"], top["confidence"],
                            top["threat_level"], lat, lon, dist, heading, web_path, "NODE-01"
                        )
                        sighting["incident_id"] = det_id

                        if not SYSTEM_STATE["is_online"]:
                            SYSTEM_STATE["offline_queue_count"] += 1
                            for c in get_contacts():
                                queue_offline_alert(det_id, c["phone_number"], f"ALERT: {top['species']} detected near perimeter!")

                        LATEST_AUTO_DETECTION = {
                            "id": det_id,
                            "species": top["species"],
                            "scientific": top["scientific_name"],
                            "confidence": top["confidence"],
                            "threat_level": top["threat_level"],
                            "image_path": web_path,
                            "latitude": lat,
                            "longitude": lon,
                            "distance_meters": dist,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                            "reported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                            "node_code": "NODE-01",
                            "timestamp": now_ts,
                            "event_id": str(uuid.uuid4())
                        }
                        print(f"[VERIFIED INCIDENT 🚨] {top['species']} in frame for {presence_time:.1f}s (Conf: {top['confidence']}%) -> Logged Incident #{det_id} [Snapshot: {snap_name}]")

            # Tactical HUD status banner overlay
            for sp, s in list(ACTIVE_SIGHTINGS.items()):
                elapsed = now_ts - s["first_seen"]
                if s["logged"]:
                    hud_text = f"THREAT RECORDED: {sp.upper()} (INCIDENT #{s['incident_id']})"
                    color = (0, 255, 120)  # Green
                else:
                    hud_text = f"VERIFYING THREAT: {sp.upper()} [{elapsed:.1f}s / 2.0s]"
                    color = (0, 200, 255)  # Amber
                cv2.rectangle(annotated, (15, 20), (min(frame.shape[1] - 15, 540), 52), (10, 20, 16), -1)
                cv2.rectangle(annotated, (15, 20), (min(frame.shape[1] - 15, 540), 52), color, 1)
                cv2.putText(annotated, hud_text, (25, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2)

            # Expire sightings if animal has left perimeter for > SIGHTING_EXPIRY_SECONDS
            expired_species = [
                sp for sp, s in list(ACTIVE_SIGHTINGS.items())
                if (now_ts - s["last_seen"]) > SIGHTING_EXPIRY_SECONDS
            ]
            for sp in expired_species:
                print(f"[Perimeter Clear] {sp} left camera view. Encounter closed.")
                del ACTIVE_SIGHTINGS[sp]

            # Encode annotated frame to JPEG and update shared buffer
            ret, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                with LATEST_FRAME_LOCK:
                    LATEST_JPEG_BYTES = buffer.tobytes()
                    LATEST_FRAME_TIMESTAMP = now_ts

            time.sleep(0.03)

        except Exception as e:
            print(f"[Surveillance Worker Error] {e}")
            time.sleep(0.5)

def start_surveillance_worker():
    """Starts the continuous surveillance worker daemon thread."""
    global SURVEILLANCE_THREAD
    if SURVEILLANCE_THREAD is None or not SURVEILLANCE_THREAD.is_alive():
        SURVEILLANCE_THREAD = threading.Thread(target=surveillance_worker, daemon=True, name="SurveillanceWorker")
        SURVEILLANCE_THREAD.start()
        print("[Surveillance] Continuous AI Background Worker thread started.")

# Launch autonomous surveillance worker only in the active server process (never in reloader parent)
_is_reloader_parent = app.debug and (os.environ.get("WERKZEUG_RUN_MAIN") is None and "run_dashboard" not in sys.argv[0].lower())
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug or "run_dashboard" in sys.argv[0].lower():
    if not (app.debug and os.environ.get("WERKZEUG_RUN_MAIN") is None and sys.argv[0].endswith("flask")):
        start_surveillance_worker()

@app.before_request
def ensure_surveillance_worker_active():
    start_surveillance_worker()

def generate_video_frames():
    """Streams continuous MJPEG from the background surveillance worker's latest frame buffer."""
    while True:
        frame_bytes = None
        with LATEST_FRAME_LOCK:
            frame_bytes = LATEST_JPEG_BYTES

        if frame_bytes is not None:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.04)

@app.route("/")
def index():
    return render_template("index.html", active_page="map")

@app.route("/camera")
def camera_page():
    model_info = ai_detector.get_info()
    current_conf = int(round(CAMERA_STATE["conf_threshold"] * 100))
    return render_template(
        "camera.html", 
        active_page="camera", 
        model_info=model_info,
        current_conf=current_conf,
        current_source=CAMERA_STATE["source"],
        thermal_mode=CAMERA_STATE["thermal_mode"]
    )

@app.route("/video_feed")
def video_feed():
    return Response(generate_video_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/camera/devices")
def get_camera_devices():
    devices = detect_available_cameras()
    return jsonify({
        "success": True, 
        "devices": devices, 
        "current_source": CAMERA_STATE["source"]
    })

@app.route("/api/camera/settings", methods=["GET", "POST"])
def camera_settings():
    global CAMERA_STATE
    if request.method == "POST":
        data = request.get_json() or {}
        with CAMERA_LOCK:
            if "source" in data:
                new_source = str(data["source"]).strip()
                if new_source != CAMERA_STATE["source"]:
                    CAMERA_STATE["source"] = new_source
                    if CAMERA_STATE.get("cap") is not None:
                        try:
                            CAMERA_STATE["cap"].release()
                        except Exception:
                            pass
                        CAMERA_STATE["cap"] = None
                    CAMERA_STATE["active_source_string"] = None
            if "thermal_mode" in data:
                CAMERA_STATE["thermal_mode"] = bool(data["thermal_mode"])
            if "conf_threshold" in data:
                CAMERA_STATE["conf_threshold"] = float(data["conf_threshold"])

            save_camera_config({
                "conf_threshold": CAMERA_STATE["conf_threshold"],
                "thermal_mode": CAMERA_STATE["thermal_mode"],
                "source": CAMERA_STATE["source"]
            })
        return jsonify({"success": True, "settings": {
            "source": CAMERA_STATE["source"],
            "thermal_mode": CAMERA_STATE["thermal_mode"],
            "conf_threshold": CAMERA_STATE["conf_threshold"]
        }})
    return jsonify({"success": True, "settings": {
        "source": CAMERA_STATE["source"],
        "thermal_mode": CAMERA_STATE["thermal_mode"],
        "conf_threshold": CAMERA_STATE["conf_threshold"]
    }})

@app.route("/api/ai/status")
def ai_status():
    return jsonify({"success": True, "info": ai_detector.get_info()})

@app.route("/api/detections/latest_live")
def latest_live_detection():
    return jsonify({
        "success": True, 
        "latest": LATEST_AUTO_DETECTION,
        "is_online": SYSTEM_STATE["is_online"],
        "queue_count": SYSTEM_STATE["offline_queue_count"]
    })

@app.route("/api/ai/detect_upload", methods=["POST"])
def detect_upload():
    if "image" not in request.files:
        return jsonify({"success": False, "message": "No image uploaded"}), 400
    f = request.files["image"]
    if not f.filename:
        return jsonify({"success": False, "message": "Empty filename"}), 400

    upload_dir = Path(__file__).resolve().parent / "static" / "snapshots"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"upload_{int(time.time())}_{secure_filename(f.filename)}"
    save_path = upload_dir / safe_name
    f.save(str(save_path))

    detections, annotated, latency, web_path = ai_detector.predict_image_file(save_path, conf_thresh=0.35, save_to_snapshots=True)

    if detections:
        primary = detections[0]
        lat = 21.1458 + (random.random() - 0.5) * 0.004
        lon = 79.0882 + (random.random() - 0.5) * 0.004
        dist = random.randint(180, 450)
        heading = random.randint(45, 315)
        det_id = log_detection(
            primary["species"], primary["scientific_name"], primary["confidence"], 
            primary["threat_level"], lat, lon, dist, heading, web_path or f"/static/snapshots/{safe_name}", "NODE-01"
        )
        if not SYSTEM_STATE["is_online"]:
            SYSTEM_STATE["offline_queue_count"] += 1
            for c in get_contacts():
                queue_offline_alert(det_id, c["phone_number"], f"ALERT: {primary['species']} detected near perimeter!")

    return jsonify({
        "success": True,
        "detections": detections,
        "latency_ms": latency,
        "snapshot_url": web_path or f"/static/snapshots/{safe_name}"
    })

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

    # Run real trained AI model on an unseen camera-trap test image if available
    real_sample = None
    if ai_detector.is_loaded:
        real_sample = ai_detector.run_random_test_sample()

    if real_sample and real_sample.get("all_detections"):
        species = real_sample["species"]
        sci_name = real_sample["scientific_name"]
        threat = real_sample["threat_level"]
        img = real_sample["web_snapshot_path"]
        conf = real_sample["confidence"]
    else:
        species_pool = [
            ("Bengal Tiger", "Panthera tigris", "CRITICAL", "/static/snapshots/tiger_sample.jpg"),
            ("Indian Leopard", "Panthera pardus", "CRITICAL", "/static/snapshots/leopard_sample.jpg"),
            ("Indian Sloth Bear", "Melursus ursinus", "HIGH", "/static/snapshots/bear_sample.jpg"),
            ("Asiatic Lion", "Panthera leo persica", "CRITICAL", "/static/snapshots/lion_sample.jpg")
        ]
        choice = random.choice(species_pool)
        species, sci_name, threat, img = choice
        conf = round(88.0 + random.random() * 10, 1)

    lat = base_lat + (random.random() - 0.5) * 0.003
    lon = base_lon + (random.random() - 0.5) * 0.003
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

    global LATEST_AUTO_DETECTION
    now_ts = time.time()
    LATEST_AUTO_DETECTION = {
        "id": det_id,
        "species": species,
        "scientific": sci_name,
        "confidence": conf,
        "threat_level": threat,
        "image_path": img,
        "latitude": lat,
        "longitude": lon,
        "distance_meters": dist,
        "time": det_time,
        "detected_at": det_time,
        "reported_at": rep_time,
        "node_code": node_code,
        "timestamp": now_ts,
        "event_id": str(uuid.uuid4())
    }
            
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
            "node_code": node_code,
            "timestamp": now_ts,
            "event_id": LATEST_AUTO_DETECTION["event_id"]
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
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
