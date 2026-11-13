# 🐅 PROJECT INDRADHANU — ARCHITECTURE & DEVELOPER BRIEFING

## 1. Strict Target Species (4 Classes Only)
Both the Edge Detection model (`edge/ml_engine/detector.py`) and Central Verification model (`ml_engine/verifier.py`) strictly classify:
1. `tiger` (*Panthera tigris*) — `CRITICAL`
2. `lion` (*Panthera leo persica*) — `CRITICAL`
3. `leopard` (*Panthera pardus*) — `CRITICAL`
4. `bear` (*Melursus ursinus*) — `HIGH`

All non-target animals, humans, livestock, and background objects are rejected (`REJECTED_FALSE_POSITIVE`).

## 2. Data Flow
```text
[Edge Camera (Pi 3 B+)]
   │
   ▼
[Edge AI Detector (YOLOv8n + MobileNetV3, imgsz=320, 2 threads)]
   │  Generates UUIDv4 event_id + saves edge/snapshots/<event_id>.jpg
   ▼
[Edge Local SQLite (edge/database/edge.db)]
   │  Crash-safe pending buffer (survives offline outages & restarts)
   ▼
[Authenticated Upload: POST /api/sync/detection (X-Device-ID, X-API-Key)]
   │
   ▼
[Central AI Verifier (EfficientNet-B0 + High-Res YOLOv8)]
   │  Exclusively verifies edge-submitted snapshots
   ▼
[Central PostgreSQL Database (event_id UNIQUE)]
   │
   ├──► [Alert Policy & Siren Service] ──► [Authenticated Siren Controller (X-Siren-Key)]
   └──► [Central Dashboard UI (Live Edge Status, Verification Dossier, Siren Audit Log)]
```
