# 🐅 PROJECT INDRADHANU (PROJECT C) - MASTER AI AGENT BRIEFING & SCOPE DIRECTIVE

> 🚨 **CRITICAL DIRECTIVE FOR ANY AI ASSISTANT (ANTIGRAVITY, GEMINI, CLAUDE, COPILOT, ETC.) WORKING ON THIS CODEBASE**:
>
> 1. **STRICT SCOPE ENFORCEMENT**: You MUST strictly adhere to the baseline specifications in this document and in `PROJECT_SCOPE.md`.
> 2. **NO SCOPE CREEP**: DO NOT add unsolicited features, extra microservices, new database tables, non-target animal classes, or speculative frameworks unless explicitly instructed by the repository owner.
> 3. **RESPECT TEAM ROLE BOUNDARIES**: Work ONLY within the boundaries of the teammate you are assisting (AI/ML Engineer vs. UI Designer vs. Backend Lead). Do NOT modify or refactor other teammates' components.

---

## 1. Project Identity & Problem Statement

* **Project Name:** Project C / Indradhanu
* **Problem Statement:** Due to deforestation and human encroachment into forest perimeters, wild predators frequently enter agricultural and village settlements, resulting in severe human-wildlife conflict, livestock loss, and human casualties.
* **Mission:** An integrated hardware + software edge early warning system deployed along forest perimeters. It uses thermal vision and motion detection on a Raspberry Pi 4 to spot dangerous wild animals and instantly dispatches emergency SMS alerts to nearby villagers and forest rangers, with central tactical GIS monitoring at Forest Headquarters.

---

## 2. STRICT Animal Scope (Zero Deviation Allowed)

The AI model and detection pipeline **ONLY** monitors the following **four (4) apex predators**:

| Class ID | Target Wild Animal | Scientific Name | Danger Rating | Action Protocol |
|:---:|---|---|:---:|---|
| **0** | **Bengal Tiger** | *Panthera tigris* | `CRITICAL` | Instant SMS Broadcast + Red GIS Beacon |
| **1** | **Indian Leopard** | *Panthera pardus* | `CRITICAL` | Instant SMS Broadcast + Red GIS Beacon |
| **2** | **Indian Sloth Bear** | *Melursus ursinus* | `HIGH` | Instant SMS Broadcast + Amber GIS Beacon |
| **3** | **Asiatic Lion** | *Panthera leo persica* | `CRITICAL` | Instant SMS Broadcast + Red GIS Beacon |

> ⚠️ **STRICT REJECTION RULE:** All other entities (livestock, cows, bulls, stray dogs, deer, monkeys, birds, humans, vehicle headlights) **MUST BE REJECTED** by the AI engine as background noise to prevent false alarms and community panic.

---

## 3. High-Level System Architecture

The project is decoupled into two clean subsystems:

```
 🌲 JUNGLE BOUNDARY (Headless Edge Unit)            ☁️ FOREST HQ / CLOUD (Tactical Command)
 ───────────────────────────────────────            ───────────────────────────────────────
 
 📷 Camera Station (Raspberry Pi 4)
 ├── PIR Sensor (Hardware wake interrupt)
 ├── Pan-Tilt Gimbal (0°-360° perimeter sweep)
 ├── Thermal Camera (MLX90640 / Seek Lepton)
 ├── Edge AI Engine (Quantized TFLite Model)
 ├── Local SQLite DB (Immediate persistent log)
 └── GSM/LTE HAT (Instant local SMS alerts)
                     │
                     │  (When 4G / Wi-Fi is available)
                     ▼
             POST /api/sync/detection
             POST /api/sync/heartbeat
                     │
                     ▼
         🖥️ Central Flask Web Server
         ├── Dual Database (PostgreSQL / Central SQLite)
         │   └── Measures: reported_at - detected_at (Sync Latency)
         └── Multi-Camera Tactical GIS Dashboard
             ├── Leaflet.js Satellite Map
             ├── Synchronized Animated Radar Sweep
             ├── Multi-Camera Station Selector (NODE-01, 02, 03)
             └── Villager & Forest Ranger Directory
```

---

## 4. Team Division of Roles & Explicit Boundaries

Every teammate has a clearly defined responsibility. If you are an AI assistant helping one of the teammates, **STAY WITHIN YOUR LANE**:

### Role A: The User (Backend Developer & System Lead)
* **Scope of Work:** API architecture, edge daemon loop (`edge/edge_daemon.py`), local and central databases, multi-station sync engine, hardware abstraction layer (HAL), and Leaflet GIS integration.
* **Status:** Fully functional with simulation support and ready for model/UI drop-in.

---

### Role B: Teammate 1 (AI/ML Engineer)
* **Goal:** Train, validate, and optimize the 4-class animal detection model.
* **Allowed Workspace:**
  * Directory: [`edge/ml_engine/`](file:///d:/Ashutosh_01/Indhradhanu/edge/ml_engine/)
  * Model Drop-in Path: `edge/ml_engine/indradhanu_wildlife_v1.tflite`
  * Test Script: `edge/ml_engine/verify_model.py`
* **Strict Technical Requirements:**
  1. **Model Format:** TensorFlow Lite (`.tflite`) quantized (INT8 or FP16) or ONNX format. Must execute on a **Raspberry Pi 4 CPU** with $<200\text{ms}$ inference latency.
  2. **Input Dimensions:** $320 \times 320 \times 3$ or $416 \times 416 \times 3$ (Thermal false-color colormap or normalized grayscale).
  3. **Output Format:** Standard object detection tensors: `[boxes, classes, scores, num_detections]`.
  4. **Strict 4-Class Mapping:** `0: Tiger`, `1: Leopard`, `2: Bear`, `3: Lion`.
* ⛔ **FORBIDDEN FOR AI ASSISTANT ASSISTING TEAMMATE 1:**
  * Do **NOT** modify `app.py`, `database/`, `templates/`, or `static/`.
  * Do **NOT** add 10 new animal classes.
  * Do **NOT** delete simulation fallbacks in `detector.py`.
  * Verify model using: `python edge/ml_engine/verify_model.py --model your_model.tflite`

---

### Role C: Teammate 2 (UI / Frontend Designer)
* **Goal:** Polish visual aesthetics, typography, animations, and responsiveness.
* **Allowed Workspace:**
  * Directory: [`static/css/`](file:///d:/Ashutosh_01/Indhradhanu/static/css/) (Styling)
  * Directory: [`static/js/`](file:///d:/Ashutosh_01/Indhradhanu/static/js/) (UI interactions)
  * Directory: [`templates/`](file:///d:/Ashutosh_01/Indhradhanu/templates/) (HTML templates)
* **Design Philosophy (Bugatti / Tactical Surveillance):**
  * Canvas: Deep obsidian/black (`#000000`, `#0d0d0d`, `#141414`).
  * Accents: Crisp glowing amber (`#f59e0b`), ice blue (`#c3d9f3`), signal green (`#10b981`), critical red (`#ef4444`).
  * Typography: Display headings (Saira Condensed), Monospace data/telemetry (JetBrains Mono).
* ⛔ **FORBIDDEN FOR AI ASSISTANT ASSISTING TEAMMATE 2:**
  * Do **NOT** remove or rename existing HTML element IDs (e.g. `#camera-node-selector`, `#gis-map`, `#snapshot-modal`, `#system-clock`, `#telemetry-battery`) — JavaScript logic depends on these exact IDs!
  * Do **NOT** delete Jinja2 template tags (e.g. `{{ active_page }}`, `{% block content %}`, `{{ detections }}`).
  * Do **NOT** replace Leaflet.js with heavy external map frameworks.

---

## 5. Offline Bottleneck & Dual-Layer Data Storage (Section 4 of Scope)

Remote forest fringe villages frequently suffer cellular network blackouts. The system handles this through a **two-tier data architecture**:

1. **Edge Storage (SQLite - `edge/database/edge.db`):**
   * Instant local write upon detection ($< 5\text{ms}$).
   * Offline SMS queue (`alert_fallback_queue`): If cellular is dead, alerts sit in SQLite and automatically flush the moment signal returns.
2. **Central / Cloud Storage (PostgreSQL - `database/schema_postgres.sql`):**
   * Synchronized whenever edge units reach the central server.
   * **`reported_at` vs `detected_at`:** Records the exact time difference to measure network latency (`sync_latency = reported_at - detected_at`).
   * Dashboard displays:
     * ⚡ **`Real-time (< 2s sync)`** — when internet was live.
     * ⚠️ **`Offline Delayed (+Xm Ys)`** — when the alert was recovered after a network blackout.

---

## 6. Directory Layout & File Roles

```text
d:/Ashutosh_01/Indhradhanu/
│
├── 🌲 edge/                          # HEADLESS EDGE SUBSYSTEM (Raspberry Pi 4)
│   ├── config.py                     # Station identity, hardware pins, and simulation settings
│   ├── edge_daemon.py                # Autonomous event loop (PIR -> Rotator -> Cam -> AI -> SQLite -> SMS -> Sync)
│   ├── hardware/                     # Hardware abstraction layer (HAL)
│   │   ├── pir_sensor.py             # PIR motion wake driver (GPIO interrupt or mock)
│   │   ├── rotator.py                # Pan-tilt stepper/servo rotator driver
│   │   └── thermal_camera.py         # Thermal camera interface (I2C MLX90640 or thermal generator)
│   ├── ml_engine/                    # Edge AI inference engine (Teammate 1 Workspace)
│   │   ├── detector.py               # TFLite/ONNX quantized model runner & fallback simulator
│   │   ├── sample_generator.py       # Thermal test snapshot generator (Tiger, Leopard, Bear, Lion)
│   │   ├── verify_model.py           # Automated validator script for Teammate 1
│   │   └── indradhanu_wildlife_v1.tflite # Target drop-in path for trained model
│   ├── services/                     # Edge background services
│   │   ├── sms_service.py            # Dual-mode SMS gateway (GSM AT commands / Fast2SMS / Twilio)
│   │   └── sync_client.py            # Upstream HTTP sync client (pushes SQLite records to HQ)
│   └── database/                     # Local Edge SQLite Storage
│       ├── schema_edge.sql           # Local tables (local_detections, alert_fallback_queue, edge_logs)
│       └── edge_db.py                # SQLite manager with transactional offline fallback queue
│
├── 🖥️ dashboard/ & root               # CENTRAL TACTICAL HQ SUBSYSTEM (Teammate 2 Workspace for styling)
│   ├── app.py                        # Central Flask server with multi-camera ingestion APIs
│   ├── database/                     # Central database management
│   │   ├── schema.sql                # Central SQLite schema
│   │   ├── schema_postgres.sql       # Central PostgreSQL schema (Section 4.2)
│   │   └── db_manager.py             # Dual-engine database adapter with sync latency calculation
│   ├── templates/                    # Web templates (base.html, index.html, history.html, nodes.html, system.html)
│   └── static/                       # Dark tactical CSS, Leaflet JS, radar cone, thermal snapshots
│
├── run_edge.py                       # Root runner for Headless Edge Station
├── run_dashboard.py                  # Root runner for Central HQ Dashboard
├── PROJECT_SCOPE.md                  # Authoritative project requirements contract
└── TEAMMATE_AGENT_BRIEF.md           # This document
```

---

## 7. How to Run & Test (Quick Reference)

### Start the Central Tactical Dashboard:
```bash
python run_dashboard.py
```
Open `http://127.0.0.1:5000` in a browser.

### Run an Edge Station in Simulation Mode:
```bash
# Continuous monitoring:
python run_edge.py --node NODE-01

# Trigger a single test sighting:
python run_edge.py --node NODE-01 --trigger-once --species tiger
python run_edge.py --node NODE-02 --trigger-once --species leopard
python run_edge.py --node NODE-03 --trigger-once --species bear
```

### Validate a New Trained Model (Teammate 1):
```bash
python edge/ml_engine/verify_model.py --model edge/ml_engine/indradhanu_wildlife_v1.tflite
```
