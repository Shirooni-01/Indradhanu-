# Project Indradhanu (Project C) 🐅
### Edge-Detected & Central-Verified Wildlife Early Warning System

An integrated edge-detection and central-verification wildlife early warning system designed to prevent human-wildlife conflict along forest perimeters. Built for headless deployment on **Raspberry Pi 3 Model B+ (Raspberry Pi OS Lite)** edge camera nodes with local SQLite offline buffering, authenticated synchronization to a **Central Coordination Server (PostgreSQL + Central AI Verification)**, and an authenticated **Village Siren Controller**.

---

## 🌟 Core Architecture (Redesigned PRD)

1. **Edge Detection System (`edge/` — Raspberry Pi 3 Model B+)**:
   - Runs a lightweight local AI detector (`YOLOv8n` + offline `MobileNetV3-Small`, optimized for Pi 3 B+ CPU with `imgsz=320` and `torch.set_num_threads(2)`).
   - Strictly detects 4 supported apex predators locally: **Tiger**, **Lion**, **Leopard**, and **Bear**.
   - Captures a snapshot (`edge/snapshots/<event_id>.jpg`), generates a globally unique `event_id` (UUIDv4), and persists the pending event in local SQLite (`edge/database/edge.db`).
   - Uploads events and multipart snapshots via authenticated HTTP (`X-Device-ID`, `X-API-Key`) to the central server, preserving unsynced events across network outages and restarts.

2. **Central Server & Verification Dashboard (`app.py`, `ml_engine/verifier.py`)**:
   - Single coordination point for multiple registered edge devices (`NODE-01`, `NODE-02`, `NODE-03`, etc.).
   - **Never** uses a dashboard-connected webcam or IP camera for independent AI detection.
   - Runs a separate **Central AI Verification Model** (`EfficientNet-B0` + high-resolution `YOLOv8` spatial verifier) exclusively on snapshots submitted by edge devices.
   - Displays verified snapshots, edge vs. central classifications, verification status (`VERIFIED`, `REJECTED_FALSE_POSITIVE`, `UNVERIFIED_LOW_CONF`), live edge connectivity (`ONLINE_ACTIVE` / `OFFLINE`), `last_heartbeat`, `last_sync_at`, and siren status.

3. **Dual-Tier Database Architecture (`edge/database/` & `database/`)**:
   - **Edge Storage**: Local SQLite (`edge/database/edge.db`) with crash-safe recovery (`recover_pending_events_on_restart()`).
   - **Central Storage**: PostgreSQL (`DATABASE_URL`, schema in `database/schema_postgres.sql`, with local dev fallback to `database/indradhanu.db`) enforcing `event_id UNIQUE` to prevent duplicate events and raising explicit errors on database failures.

4. **Verification Policy & Authenticated Village Siren Controller (`services/siren_service.py`, `edge/siren_controller.py`)**:
   - Evaluates Central AI verification results against the configured alert policy (`VERIFIED`, confidence $\ge$ `SIREN_MIN_CONFIDENCE`, and sync delay $\le$ `SIREN_MAX_DELAY_SECONDS`).
   - Sends an authenticated command (`X-Siren-Key`) to the Siren Controller daemon (`edge/siren_controller.py`) with optocoupler-isolated GPIO relay control and hardware watchdog cutoff.
   - Strictly distinguishes between:
     - `COMMAND_SENT` (command transmitted, awaiting acknowledgement)
     - `ACKNOWLEDGED_ACTIVE` (`physical_siren_active=1`, real GPIO relay energized on Raspberry Pi)
     - `TEST_MODE_VERIFIED` (`physical_siren_active=0`, verified in `SAFE_TEST` mode)
     - `SUPPRESSED_POLICY` / `SUPPRESSED_DELAYED_EVENT` / `CONTROLLER_UNREACHABLE`

---

## 🚀 Quick Start

### 1. Central Server & Dashboard
```bash
pip install -r requirements.txt
# Configure .env (see .env.example for DATABASE_URL, EDGE_SHARED_API_KEY, SIREN_CONTROLLER_URL, etc.)
python run_dashboard.py
```
Open `http://127.0.0.1:5000`.

### 2. Village Siren Controller Daemon
```bash
# Safe test mode (default) or hardware GPIO mode on Raspberry Pi (SIREN_CONTROLLER_MODE=HARDWARE_GPIO)
python -m edge.siren_controller
```

### 3. Edge Device Daemon (Raspberry Pi 3 Model B+)
```bash
# Continuous camera-connected edge monitoring:
python run_edge.py --node NODE-01

# Single test capture & central sync:
python run_edge.py --node NODE-01 --trigger-once --species tiger
```
