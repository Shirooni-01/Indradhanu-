# Project Indradhanu (Project C) 🐅
### Wildlife Early Warning & Perimeter Surveillance System

An integrated edge-AI system designed to prevent human-wildlife conflict along forest borders and agricultural fringes. Built for deployment on **Raspberry Pi 4** with thermal imaging, pan-tilt scanning, offline SQLite fallback queuing, and emergency SMS alerts to villagers and forest authorities.

---

## 🌟 Key Features

1. **Wildlife Species Focus**:
   - **Bengal Tiger** (*Panthera tigris*) - Threat: Critical
   - **Indian Leopard** (*Panthera pardus*) - Threat: Critical
   - **Indian Sloth Bear** (*Melursus ursinus*) - Threat: High
   - **Asiatic Lion** (*Panthera leo persica*) - Threat: Critical

2. **Tactical Forest Officer Dashboard**:
   - **Interactive GIS Map (Leaflet.js)**: Displays base station, forest perimeter, village safety buffer rings, and real-time animal threat markers with coordinates.
   - **Synchronized Radar Scan Cone**: The visual radar cone on the map rotates dynamically matching the physical pan-tilt camera's compass heading.
   - **Thermal HUD Feed**: Live video monitor with target species bounding box, confidence score, and thermal palette.
   - **Detection History Carousel**: Real-time sighting archive showing high-res snapshots, GPS coordinates, village distance, and SMS delivery receipts.
   - **Villagers & Authorities Directory**: Register and manage phone numbers for automated SMS dispatch.

3. **Intelligent Power Saving (PIR Wake-on-Movement)**:
   - Preserves battery by running in ultra-low power standby mode when no motion is detected.
   - Wakes up via GPIO interrupt in milliseconds to snap frames and run inference only when movement occurs.

4. **Zero-Loss Offline SQLite Fallback**:
   - In remote jungle fringes with zero cellular data or network outages, alerts are safely transactionalized in local SQLite (`alert_fallback_queue`).
   - A background synchronization worker flushes and dispatches all queued SMS alerts the instant connectivity is restored.
   - Features a **"Simulate Offline"** toggle in the UI for live demonstration and testing.

---

## 📁 Project Structure

```
d:/Ashutosh_01/Indhradhanu/
├── app.py                      # Flask web server and REST APIs
├── requirements.txt            # Python dependencies
├── database/
│   ├── schema.sql              # Database schema (detections, contacts, alert_queue)
│   ├── db_manager.py           # SQLite manager and fallback queue handler
│   └── indradhanu.db           # SQLite database
├── ml_engine/
│   └── sample_generator.py     # Thermal snapshot generator (Tiger, Leopard, Bear, Lion)
├── templates/
│   └── index.html              # Tactical monitoring dashboard UI
└── static/
    ├── css/
    │   └── style.css           # Custom dark surveillance dashboard styling
    ├── js/
    │   ├── app.js              # Application logic, telemetry, and rotator controls
    │   └── map.js              # Leaflet GIS map and dynamic radar cone
    └── snapshots/              # Thermal verification snapshots
        ├── tiger_sample.jpg
        ├── leopard_sample.jpg
        ├── bear_sample.jpg
        └── lion_sample.jpg
```

---

## 🚀 How to Run the Dashboard

1. **Activate Python environment & install requirements**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Flask server**:
   ```bash
   python app.py
   ```

3. **Open in your web browser**:
   ```
   http://127.0.0.1:5000
   ```

---

## 📋 Specifications for Your AI/ML Teammate

Send these exact parameters to your team's ML engineer:

- **Target Architecture**: Lightweight model optimized for Raspberry Pi 4 CPU (Recommended: **YOLOv8-Nano** or **MobileNetV4**).
- **Target Export**: `.onnx` or `.tflite` (Quantized INT8 or FP16).
- **Input Dimensions**: `320x320` or `416x416` (RGB and thermal/IR nighttime frames).
- **Class Labels (4 Classes)**:
  - `0`: `tiger`
  - `1`: `leopard`
  - `2`: `bear`
  - `3`: `lion`
- **Output**: Bounding boxes `[x1, y1, x2, y2, confidence, class_id]`.
