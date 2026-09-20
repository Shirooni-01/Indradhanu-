"""
Sync Client - Project Indradhanu (Project C)
Runs as a background daemon on the Edge unit.
Pushes unsynced local SQLite detections and hardware telemetry to Central HQ when network is reachable.
"""

import time
import threading
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
            return self.is_connected
        except Exception:
            self.is_connected = False
            return False

    def sync_pending_detections(self):
        """Flushes unsynced local detections to Central HQ."""
        pending = get_unsynced_detections(limit=10)
        if not pending:
            return 0

        synced_count = 0
        url = f"{self.hq_url}/api/sync/detection"

        for det in pending:
            payload = {
                "node_code": det.get("node_code", self.node_code),
                "species": det["species"],
                "scientific_name": det.get("scientific_name"),
                "confidence": det["confidence"],
                "threat_level": det["threat_level"],
                "latitude": det["latitude"],
                "longitude": det["longitude"],
                "distance_meters": det.get("distance_meters"),
                "rotator_heading": det.get("rotator_heading"),
                "image_snapshot_path": det.get("image_snapshot_path"),
                "detected_at": det["detected_at"]  # Crucial: Preserves original forest detection time!
            }
            try:
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
