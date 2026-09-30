"""
Sync Client - Project Indradhanu (Project C)
Runs as a background daemon on the Edge unit.
Pushes unsynced local SQLite detections and hardware telemetry to Central HQ when network is reachable.
"""

import os
import time
import threading
from pathlib import Path
import requests
from edge.config import HQ_SERVER_URL, NODE_CODE, NODE_NAME, SECTOR, LATITUDE, LONGITUDE
from edge.database.edge_db import (
    get_unsynced_detections, 
    mark_detection_synced, 
    log_edge_event
)

class SyncClient:
    def __init__(self, hq_url=HQ_SERVER_URL, node_code=NODE_CODE):
        self.hq_url = hq_url.rstrip("/")
        self.node_code = node_code
        self.is_running = False
        self.sync_thread = None
        self.is_connected = False
        self._last_log_state = None

    def send_heartbeat(self, battery_pct=88, solar_charging=True, heading=145, status="ONLINE_ACTIVE"):
        """Sends periodic station health heartbeat to Central HQ."""
        url = f"{self.hq_url}/api/sync/heartbeat"
        payload = {
            "node_code": self.node_code,
            "node_name": NODE_NAME,
            "sector": SECTOR,
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "battery_pct": battery_pct,
            "solar_charging": solar_charging,
            "rotator_heading": heading,
            "status": status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            resp = requests.post(url, json=payload, timeout=3)
            self.is_connected = resp.status_code == 200
            if self._last_log_state != True and self.is_connected:
                print(f"[Sync Client] [ONLINE] Heartbeat synced with Central HQ at {self.hq_url}")
                self._last_log_state = True
            return self.is_connected
        except Exception as e:
            if self._last_log_state != False:
                print(f"[Sync Client Warning] Cannot connect to HQ at {self.hq_url} ({e})")
                self._last_log_state = False
            self.is_connected = False
            return False

    def sync_pending_detections(self):
        """Flushes unsynced local detections to Central HQ."""
        pending = get_unsynced_detections(limit=10)
        if not pending:
            return 0

        synced_count = 0
        url = f"{self.hq_url}/api/sync/detection"

        root_dir = Path(__file__).resolve().parent.parent.parent

        for det in pending:
            payload = {
                "node_code": det.get("node_code", self.node_code),
                "species": det["species"],
                "scientific_name": det.get("scientific_name") or "",
                "confidence": str(det["confidence"]),
                "threat_level": det["threat_level"],
                "latitude": str(det["latitude"]),
                "longitude": str(det["longitude"]),
                "distance_meters": str(det.get("distance_meters") or 300),
                "rotator_heading": str(det.get("rotator_heading") or 145),
                "image_snapshot_path": det.get("image_snapshot_path") or "",
                "detected_at": str(det["detected_at"])  # Crucial: Preserves original forest detection time!
            }

            img_path = det.get("image_snapshot_path")
            file_to_send = None
            if img_path:
                p = Path(img_path)
                if not p.is_absolute():
                    clean_rel = img_path.lstrip("/\\")
                    p = root_dir / clean_rel
                if p.exists() and p.is_file():
                    file_to_send = p

            try:
                if file_to_send:
                    with open(file_to_send, "rb") as f:
                        files = {"snapshot": (file_to_send.name, f, "image/jpeg")}
                        resp = requests.post(url, data=payload, files=files, timeout=6)
                else:
                    resp = requests.post(url, json=payload, timeout=4)

                if resp.status_code in (200, 201):
                    mark_detection_synced(det["id"])
                    synced_count += 1
                    log_edge_event("SYNC_SUCCESS", f"Synced detection #{det['id']} ({det['species']}) to HQ.")
                else:
                    log_edge_event("SYNC_FAIL", f"HQ responded with HTTP {resp.status_code} for detection #{det['id']}")
            except Exception as e:
                # Network unreachable - will safely retry on next cycle
                log_edge_event("SYNC_OFFLINE", f"Sync failed: {e}. Record #{det['id']} safely retained in SQLite.")
                break

        return synced_count

    def start_background_sync(self, interval_sec=5):
        """Starts background worker thread."""
        self.is_running = True
        def worker():
            while self.is_running:
                try:
                    self.send_heartbeat()
                    self.sync_pending_detections()
                except Exception as e:
                    pass
                time.sleep(interval_sec)

        self.sync_thread = threading.Thread(target=worker, daemon=True)
        self.sync_thread.start()
        print(f"[Sync Client] Upstream sync worker started targeting Central HQ at {self.hq_url}")

    def stop(self):
        self.is_running = False
