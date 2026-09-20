# Project Indradhanu (Project C) — Phase-Wise Roadmap & TODO List

> **Project Identity:** Edge-AI early warning perimeter system on Raspberry Pi 4 with thermal vision, pan-tilt rotator, zero-loss offline SQLite fallback, and instant SMS alerts for 4 wild species (Tiger, Leopard, Indian Bear, Lion).

---

## 📊 Summary of Phases

| Phase | Description | Status |
|---|---|:---:|
| **Phase 1** | Foundation: Database, Dashboard, & Core Backend APIs | **Completed** ✅ |
| **Phase 2** | SMS Dispatch Engine & Offline Auto-Recovery Service | **Up Next** 🚀 |
| **Phase 3** | Hardware Control: Rotator & PIR Sensor Drivers | **Planned** ⏳ |
| **Phase 4** | Edge AI Model Pipeline & Thermal Vision Integration | **Planned** ⏳ |
| **Phase 5** | Autonomous Edge Loop & Low-Power Standby Mode | **Planned** ⏳ |
| **Phase 6** | Field Testing, Simulation Stress Tests & UI Polish | **Planned** ⏳ |

---

## Phase 1: Foundation Architecture & Dashboard Core
*Status: Completed ✅*

- [x] **Database Architecture**:
  - [x] Create `database/schema.sql` for detections, village contacts, and alert fallback queue.
  - [x] Implement `database/db_manager.py` with transactional queuing and flush mechanics.
  - [x] Pre-populate initial dummy contacts (Forest officers, village heads, patrol units).
- [x] **Tactical Web Dashboard**:
  - [x] Interactive Leaflet.js GIS map with base station, forest perimeter, and safety buffer zones.
  - [x] Dynamic radar cone synchronized with pan-tilt camera heading angle.
  - [x] Thermal HUD monitor simulation displaying bounding boxes and species telemetry.
  - [x] Sighting history carousel and recent detection list.
  - [x] Villagers & authorities directory interface (add/delete/list).
- [x] **Backend REST APIs (`app.py`)**:
  - [x] API endpoints for telemetry, rotator heading, and manual angle control.
  - [x] API endpoint for manual trigger / simulated detection.
  - [x] "Simulate Offline" toggle to demonstrate offline queuing.
- [x] **Sample Thermal Data**:
  - [x] Implement `ml_engine/sample_generator.py` for Tiger, Leopard, Bear, and Lion test snapshots.

---

## Phase 2: Alert Dispatch & Offline Resilience Service
*Status: In Progress / Next Priority 🚀*

- [ ] **SMS Notification Gateway (`services/sms_service.py`)**:
  - [ ] Implement dual-mode SMS sender:
    - Mode A: Real hardware GSM/LTE HAT (SIM800 / SIM7600 via serial AT commands).
    - Mode B: Cloud SMS API fallback (Twilio / Fast2SMS / MSG91) for development and testing.
  - [ ] Standardize alert SMS message template:
    - Species name, danger level, time, camera sector/heading, and recommended precaution.
- [ ] **Proximity & Sector-Based Alert Targeting**:
  - [ ] Filter contacts based on proximity to the camera's detected heading/distance (alert only affected sectors first).
  - [ ] High-priority broadcast for critical threat species (Tiger, Leopard, Lion).
- [ ] **Network Connectivity Monitor (`services/network_monitor.py`)**:
  - [ ] Background thread pinging DNS/gateway to reliably detect online/offline state transitions.
  - [ ] Automatic trigger of queue flush as soon as network returns.
- [ ] **Background Queue Sync Daemon**:
  - [ ] Transactional worker to drain `alert_fallback_queue` safely with retry counts and status logging.

---

## Phase 3: Hardware Drivers & Edge Subsystems (`hardware/`)
*Status: Planned ⏳*

- [ ] **Pan-Tilt Rotator Controller (`hardware/rotator.py`)**:
  - [ ] Driver for dual servo (pan-tilt) or stepper motor via RPi GPIO / PWM (e.g., PCA9685).
  - [ ] Automatic sweep mode (continuous 0°–180° / 360° perimeter scan).
  - [ ] Telemetry publisher feeding the actual hardware angle to `app.py` in real time.
- [ ] **PIR Motion Sensor Interrupt (`hardware/pir_sensor.py`)**:
  - [ ] GPIO pin interrupt listener on Raspberry Pi.
  - [ ] Trigger wake-up sequence on motion: activate rotator sweep and camera capture.
- [ ] **Thermal Camera Interface (`hardware/thermal_cam.py`)**:
  - [ ] Support thermal sensor capture (MLX90640 I2C / FLIR Lepton / Seek Thermal / UVC night cam).
  - [ ] Temperature array to thermal colormap image rendering (Ironbow / Rainbow palette).

---

## Phase 4: Edge AI/ML Inference Pipeline (`ml_engine/`)
*Status: Planned (Collaborating with Teammate 1 - ML Engineer) ⏳*

- [ ] **Model Integration Contract with Teammate 1**:
  - [ ] Enforce 4 target animal classes: `0: tiger`, `1: leopard`, `2: bear`, `3: lion`.
  - [ ] Accept quantized model format (`.tflite` or `.onnx`) sized for Raspberry Pi 4 CPU/NPU.
- [ ] **Edge Inference Engine (`ml_engine/detector.py`)**:
  - [ ] Frame pre-processing (resizing to 320x320/416x416, normalization).
  - [ ] Inference execution using TFLite Runtime or ONNXRuntime.
  - [ ] Post-processing: Non-Maximum Suppression (NMS) and confidence threshold filtering (e.g. >0.65).
  - [ ] Snapshot bounding box overlay and auto-saving to `static/snapshots/`.
- [ ] **Strict Species Scope Filter**:
  - [ ] Immediately reject non-target classifications (dogs, cows, birds, humans) to eliminate false alarms.

---

## Phase 5: Autonomous Edge Loop & Power Optimization
*Status: Planned ⏳*

- [ ] **Master Edge Daemon (`main.py` / system orchestrator)**:
  - [ ] State Machine:
    1. **SLEEP / STANDBY**: Low power, waiting for PIR motion interrupt.
    2. **WAKE & SCAN**: Motion detected, activate rotator and camera.
    3. **INFERENCE**: Capture frame and evaluate ML model.
    4. **DISPATCH**: If target species confirmed, write detection to DB, send SMS (or queue in SQLite).
    5. **RETURN TO STANDBY**: Timeout if no further motion.
- [ ] **Power Management & Auto-Boot Setup**:
  - [ ] Systemd service configuration for Raspberry Pi auto-start on power reboot.
  - [ ] Graceful SQLite shutdown on low battery / power loss.

---

## Phase 6: Field Simulation, Stress Testing & UI Polish
*Status: Planned (Collaborating with Teammate 2 - UI Designer) ⏳*

- [ ] **Offline Resilience Stress Test**:
  - [ ] Disconnect network -> trigger multiple animal detections -> verify SQLite queue integrity -> reconnect network -> verify 100% alert delivery.
- [ ] **PIR Wake-up Latency Verification**:
  - [ ] Ensure time from PIR interrupt to first inference frame is under 1.5 seconds.
- [ ] **UI/UX Polish**:
  - [ ] Teammate 2 design improvements (typography, high-contrast dark theme, mobile responsiveness for patrolling forest guards).
- [ ] **Field Deployment Manual & Hardware Pinout Diagram**:
  - [ ] Wiring diagrams (RPi 4 GPIO pinout for PIR, servos, thermal sensor).
