# PROJECT C (INDRADHANU) - CORE SCOPE & BASELINE SPECIFICATION

> **IMPORTANT ENFORCEMENT RULE**:
> If any feature is requested in the future that is NOT in this core baseline document, the AI assistant MUST explicitly alert the user that the requested feature is outside the original project scope before proceeding.

---

## 1. Project Identity
- **Project Name:** Project C / Indradhanu
- **Problem Statement:** Due to deforestation and human interference in their habitat, wild animals are entering human settlements, killing livestock and humans.
- **Core Mission:** A combined hardware + software edge system that detects dangerous wild animals using thermal vision and instantly dispatches SMS alerts to nearby villagers and village authorities.

---

## 2. Target Animals (Strict Scope)
Only the following four (4) wild animals:
1. **Lion**
2. **Tiger**
3. **Indian Bear** (Melursus ursinus / Sloth Bear)
4. **Leopard**

---

## 3. Hardware Requirements (Strict Scope)
- **Raspberry Pi 4** (Edge computing unit)
- **Thermal Camera** (Primary imaging sensor)
- **Camera Rotator** (Pan-tilt mechanism to sweep perimeter)
- Essential edge accessories (PIR motion wake trigger, power subsystem)

---

## 4. Critical Offline Bottleneck & Dual-Layer Data Storage
- **The Bottleneck:** Zero internet / Cellular network outages in remote forest fringe villages.
- **The Dual-Layer Architecture:** 
  1. **Edge Storage (SQLite):**
     - On every edge unit, upon AI detection of a target animal, the complete detection payload (`species`, `latitude`, `longitude`, `confidence`, `threat_level`, `detected_at` timestamp, and `image_snapshot_path`) is stored **immediately** in local SQLite, regardless of network availability.
     - Handles SMS alert queuing during network blackouts to guarantee zero alert loss.
  2. **Central / Cloud Storage (PostgreSQL):**
     - When network connectivity is available, data is shifted/synchronized from edge SQLite to central PostgreSQL.
     - **`reported_at` Column:** In PostgreSQL, records include a dedicated `reported_at` timestamp marking the exact time data was transferred from SQLite, allowing operators to measure network sync latency (`reported_at` - `detected_at`) and distinguish real-time alerts from delayed historical logs.

---

## 5. Technology Stack
- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python (Flask)
- **Edge Database:** SQLite (immediate local persistent storage and offline fallback queue)
- **Central / Cloud Database:** PostgreSQL (centralized repository with `reported_at` sync tracking)
- **AI/ML:** Dedicated animal detection model trained by the AI/ML teammate
- **Dashboard:** Live tactical map and monitoring interface

---

## 6. Team Division of Roles
- **User (Backend Developer):** Backend development, API architecture, database, dashboard integration.
- **Teammate 1 (AI/ML Engineer):** Training and optimizing the animal detection model.
- **Teammate 2 (UI Designer):** Visual styling and UI polish (joining later).
