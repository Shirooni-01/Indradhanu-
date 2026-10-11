"""
Authenticated Edge-to-Central Sync Client - Project Indradhanu
Runs on each Raspberry Pi edge unit to:
1. Send periodic authenticated heartbeats with pending queue count & telemetry
2. Upload pending SQLite detection events and snapshots to the Central Server
3. Preserve events during network outages and retry safely with backoff
"""

import json
import time
import threading
from pathlib import Path
import requests

from edge.config import (
    HQ_SERVER_URL,
    EDGE_API_KEY,
    NODE_CODE,
    NODE_NAME,
    SECTOR,
    LATITUDE,
    LONGITUDE,
    FIRMWARE_VERSION,
)
from edge.database.edge_db import (
    get_unsynced_detections,
    get_pending_sync_count,
    mark_detection_synced,
    record_sync_failure,
    log_edge_event,
)


class SyncClient:
    def __init__(self, hq_url=HQ_SERVER_URL, node_code=NODE_CODE, api_key=EDGE_API_KEY, db_path=None):
        self.hq_url = str(hq_url).rstrip("/")
        self.node_code = node_code
        self.api_key = api_key
        self.db_path = db_path
        self.is_running = False
        self.sync_thread = None
        self.is_connected = False
        self._last_log_state = None
        self.last_sync_response = None

    def _auth_headers(self):
        return {
            "X-Device-ID": self.node_code,
            "X-API-Key": self.api_key,
        }

    def send_heartbeat(self, battery_pct=100, solar_charging=True, heading=145, status="ONLINE_ACTIVE", lat=None, lon=None):
        """Sends authenticated station health & sync queue heartbeat to the Central Server."""
        url = f"{self.hq_url}/api/sync/heartbeat"
        pending_cnt = get_pending_sync_count(db_path=self.db_path)
        payload = {
            "node_code": self.node_code,
            "node_name": f"Perimeter Edge Unit ({self.node_code})" if self.node_code != NODE_CODE else NODE_NAME,
            "sector": SECTOR,
            "latitude": float(lat if lat is not None else LATITUDE),
            "longitude": float(lon if lon is not None else LONGITUDE),
            "battery_pct": battery_pct,
            "solar_charging": solar_charging,
            "rotator_heading": heading,
            "pending_queue_count": pending_cnt,
            "firmware_version": FIRMWARE_VERSION,
            "status": status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            resp = requests.post(url, json=payload, headers=self._auth_headers(), timeout=4)
            self.is_connected = resp.status_code == 200
            if self._last_log_state is not True and self.is_connected:
                print(f"[Sync Client] [ONLINE] Authenticated heartbeat accepted by Central Server ({self.hq_url})")
                self._last_log_state = True
            elif resp.status_code == 401:
                print(f"[Sync Client Error] Authentication rejected (HTTP 401) by Central Server for {self.node_code}")
            return self.is_connected
        except Exception as e:
            if self._last_log_state is not False:
                print(f"[Sync Client Warning] Central Server unreachable at {self.hq_url} ({e})")
                self._last_log_state = False
            self.is_connected = False
            return False

    def sync_pending_detections(self, respect_backoff=False):
        """
        Uploads unsynced local SQLite detections and their snapshots to the Central Server.
        Preserves records on network or server failure and marks synced only on HTTP 200/201.
        """
        pending = get_unsynced_detections(limit=15, respect_backoff=respect_backoff, db_path=self.db_path)
        if not pending:
            return 0

        synced_count = 0
        url = f"{self.hq_url}/api/sync/detection"
        root_dir = Path(__file__).resolve().parent.parent.parent

        for det in pending:
            event_id = det["event_id"]
            payload = {
                "event_id": event_id,
                "node_code": det.get("node_code", self.node_code),
                "species": det["species"],
                "scientific_name": det.get("scientific_name") or "",
                "confidence": str(det["confidence"]),
                "threat_level": det["threat_level"],
                "latitude": str(det["latitude"]),
                "longitude": str(det["longitude"]),
                "distance_meters": str(det.get("distance_meters") or 280),
                "rotator_heading": str(det.get("rotator_heading") or 145),
                "bbox_json": det.get("bbox_json") or "",
                "image_snapshot_path": det.get("image_snapshot_path") or "",
                "detected_at": str(det["detected_at"]),
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
                        resp = requests.post(url, data=payload, files=files, headers=self._auth_headers(), timeout=12)
                else:
                    resp = requests.post(url, json=payload, headers=self._auth_headers(), timeout=8)

                if resp.status_code in (200, 201):
                    self.last_sync_response = resp.json() if resp.content else {}
                    mark_detection_synced(det["id"], db_path=self.db_path)
                    synced_count += 1
                    self.is_connected = True
                    log_edge_event(
                        "SYNC_SUCCESS",
                        f"Synced event {event_id} ({det['species']}) to Central Server.",
                        db_path=self.db_path,
                    )
                else:
                    err_msg = f"Central Server returned HTTP {resp.status_code}: {resp.text[:160]}"
                    record_sync_failure(det["id"], err_msg, db_path=self.db_path)
                    log_edge_event("SYNC_FAIL", err_msg, db_path=self.db_path)
            except Exception as e:
                err_msg = f"Network unreachable during upload of {event_id}: {e}"
                record_sync_failure(det["id"], err_msg, db_path=self.db_path)
                log_edge_event("SYNC_OFFLINE", err_msg, db_path=self.db_path)
                self.is_connected = False
                break

        return synced_count

    def start_background_sync(self, interval_sec=5):
        """Starts background synchronization worker thread."""
        self.is_running = True

        def worker():
            while self.is_running:
                try:
                    self.send_heartbeat()
                    self.sync_pending_detections(respect_backoff=False)
                except Exception:
                    pass
                time.sleep(interval_sec)

        self.sync_thread = threading.Thread(target=worker, daemon=True)
        self.sync_thread.start()
        print(f"[Sync Client] Authenticated background sync worker started -> {self.hq_url}")

    def stop(self):
        self.is_running = False
