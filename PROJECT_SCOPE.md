# PROJECT INDRADHANU — AUTHORITATIVE PRD & ARCHITECTURE SCOPE

## 1. System Architecture
Indradhanu is an **edge-detection and central-verification** wildlife early warning system:
- **Edge Devices (Raspberry Pi 3 Model B+, Raspberry Pi OS Lite)**:
  - Run a lightweight local AI model (`YOLOv8n` + `MobileNetV3-Small`) connected to the edge camera.
  - Detect the 4 target species locally: `tiger`, `lion`, `leopard`, and `bear`.
  - Capture a snapshot, assign a unique UUIDv4 `event_id`, store the pending event in local SQLite (`edge/database/edge.db`), and synchronize with the central server over authenticated HTTP (`X-Device-ID`, `X-API-Key`).
- **Central Server & Dashboard (`app.py`)**:
  - Coordinates multiple registered edge devices.
  - Runs a separate Central AI Verification model (`ml_engine/verifier.py` — `EfficientNet-B0` + high-res `YOLOv8`) exclusively on snapshots uploaded by edge devices.
  - Never performs independent camera detection from a dashboard-connected webcam or IP stream.
  - Persists verified events in PostgreSQL (`DATABASE_URL`) with strict `event_id` deduplication.
- **Village Siren Activation (`services/siren_service.py` & `edge/siren_controller.py`)**:
  - Triggers the village siren only when Central AI verification satisfies the configured alert policy.
  - Prevents duplicate siren activations per `event_id` and distinguishes between `COMMAND_SENT`, `ACKNOWLEDGED_ACTIVE` (physical GPIO relay), and `TEST_MODE_VERIFIED` (`SAFE_TEST` mode).
