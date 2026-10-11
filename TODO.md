# Project Indradhanu — Redesign Implementation Checklist

- [x] **Phase 1: Full Project Audit & Migration Plan** (`audit_and_migration_plan.md`)
- [x] **Phase 2: Remove Obsolete Functionality**
  - [x] Removed dashboard-connected webcam/IP camera detection pipeline (`/camera`, `/video_feed`, `/api/camera/*`, `/api/detections/simulate`).
  - [x] Removed hardcoded network IPs (`10.88.240.180`) and personal phone numbers from source code and configs.
- [x] **Phase 3: Implement the New Indradhanu PRD**
  - [x] **A. Edge Detection System**: 4-species detector (`tiger`, `lion`, `leopard`, `bear`), snapshot capture, UUIDv4 `event_id`, local SQLite persistence, offline retry, and multi-device support.
  - [x] **B. Central Server & Dashboard**: Authenticated edge ingestion (`/api/sync/detection`, `/api/sync/heartbeat`), dedicated Central AI Verification model (`ml_engine/verifier.py`), and real-state dashboard UI.
  - [x] **C. Database Architecture**: Edge SQLite (`edge/database/edge_db.py`) + Central PostgreSQL (`database/db_manager.py`, `database/schema_postgres.sql`) with `event_id UNIQUE` deduplication and strict error propagation.
  - [x] **D. Verification & Siren Activation**: Policy-driven `SirenService` (`services/siren_service.py`) and authenticated `SirenHardwareController` (`edge/siren_controller.py`) distinguishing `COMMAND_SENT`, `ACKNOWLEDGED_ACTIVE`, and `TEST_MODE_VERIFIED`.
  - [x] **E. Networking & Multi-Device Support**: Environment-configured URLs/keys, dynamic `ONLINE_ACTIVE`/`OFFLINE` heartbeat computation, and delayed event handling.
  - [x] **F. Hardware & Deployment**: Raspberry Pi 3 Model B+ CPU/RAM optimizations (`setup_pi.sh`, `imgsz=320`, 2 threads) and optocoupler-isolated GPIO siren controller.
- [x] **Phase 4: Database & Architecture Migration**
- [x] **Phase 5: Staged Testing & Verification (Stages 1–10)**
