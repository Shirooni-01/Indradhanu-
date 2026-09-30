"""
Master Headless Edge Daemon - Project Indradhanu (Project C)
Runs autonomously on Raspberry Pi 3 Model B+ edge camera stations.
Workflow:
  PIR Wake Interrupt -> USB Camera Capture -> Real AI Inference -> Local SQLite -> SMS Alert -> Central HQ Sync
"""

import sys
import os
import time
import argparse

# Ensure root workspace is on python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure stdout handles UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Preload OpenBLAS globally to resolve Linux aarch64 PyTorch 'undefined symbol: sbgemm_'
if sys.platform.startswith("linux"):
    import ctypes
    for lib in [
        "/usr/lib/aarch64-linux-gnu/libopenblas.so.0",
        "/usr/lib/aarch64-linux-gnu/libopenblas.so",
        "/usr/lib/arm-linux-gnueabihf/libopenblas.so.0",
        "/usr/lib/libopenblas.so.0",
        "/usr/lib/libopenblas.so"
    ]:
        if os.path.exists(lib):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                break
            except Exception:
                pass

from edge.config import (
    NODE_CODE, NODE_NAME, SECTOR, LATITUDE, LONGITUDE, 
    FIXED_HEADING_DEG, SIMULATION_MODE, HQ_SERVER_URL, PIR_ENABLED
)
from edge.database.edge_db import (
    init_edge_db, log_local_detection, queue_sms_alert, 
    get_local_contacts, log_edge_event, flush_edge_sms_queue
)
from edge.hardware.pir_sensor import PIRSensor
from edge.hardware.thermal_camera import USBCamera
from edge.ml_engine.detector import WildlifeDetector
from edge.services.sms_service import SMSService
from edge.services.sync_client import SyncClient

class EdgeStationDaemon:
    def __init__(self, node_code=NODE_CODE, hq_url=HQ_SERVER_URL, enable_pir=PIR_ENABLED):
        self.node_code = node_code
        self.hq_url = hq_url
        self.enable_pir = enable_pir
        self.fixed_heading = FIXED_HEADING_DEG
        print("=" * 65)
        print(f"[EDGE STATION] PROJECT INDRADHANU - NODE [{self.node_code}]")
        print(f"   Sector: {SECTOR}")
        print(f"   Location: {LATITUDE}, {LONGITUDE}")
        print(f"   Heading: {self.fixed_heading}° (Fixed Direction)")
        print(f"   HQ Server: {self.hq_url}")
        print(f"   Hardware: Raspberry Pi (USB Optical Surveillance Camera)")
        print(f"   Motion Sensor (PIR): {'ENABLED' if self.enable_pir else 'DISABLED (Continuous Surveillance)'}")
        print("=" * 65)

        # 1. Initialize local SQLite
        init_edge_db()
        print("[1/5] Local SQLite database verified.")

        # 2. Initialize Subsystems
        self.camera = USBCamera()
        self.ai_detector = WildlifeDetector()
        self.sms_service = SMSService()
        self.sync_client = SyncClient(hq_url=self.hq_url, node_code=self.node_code)

        # 3. Setup PIR Sensor if enabled, otherwise continuous loop
        self.is_busy = False
        if self.enable_pir:
            self.pir = PIRSensor(on_motion_callback=self.on_motion_detected)
            print("[2/5] PIR motion hardware interrupt armed.")
        else:
            self.pir = None
            print("[2/5] Operating in continuous monitoring mode (no motion sensor required).")

    def on_motion_detected(self):
        """Callback for PIR motion interrupt."""
        self.process_cycle(trigger_reason="PIR_WAKE")

    def process_cycle(self, trigger_reason="MANUAL_TRIGGER"):
        """Core Edge Processing Loop: Capture -> AI Model -> SQLite -> SMS -> HQ Sync."""
        if self.is_busy:
            return

        self.is_busy = True
        try:
            log_edge_event(trigger_reason, f"Triggered at heading {self.fixed_heading}°")

            # A. USB Camera Frame Capture
            frame_data = self.camera.capture_frame()
            if not frame_data or frame_data.get("frame") is None:
                print(f"[Camera Warning] Frame capture failed on device {self.camera.source}.")
                return

            frame = frame_data["frame"]
            snap_path = frame_data.get("snapshot_path")
            h, w = frame.shape[:2]
            print(f"[Camera] Captured frame: {w}x{h} px | Stored: {snap_path}")

            # B. Real AI Model Inference (Strictly Tiger & Leopard)
            print(f"[AI Engine] Running inference for Bengal Tiger & Indian Leopard...")
            result = self.ai_detector.run_inference(frame_data)
            lat_ms = result.get("latency_ms", 0)

            if not result.get("detected"):
                print(f"[AI Engine] Scan complete ({lat_ms:.1f}ms). Perimeter clear (no Tiger/Leopard detected).")
                return

            species = result["species"]
            scientific = result["scientific_name"]
            threat = result["threat_level"]
            conf = result["confidence"]
            snapshot = result["web_snapshot_path"]
            dist = 280  # Estimated perimeter distance

            print(f"\n[ALERT - CRITICAL] CONFIRMED {species.upper()} ({scientific})!")
            print(f"   Confidence: {conf}% | Threat: {threat} | Latency: {lat_ms:.1f}ms | Heading: {self.fixed_heading}°")

            # C. Immediate Local SQLite Storage
            det_id = log_local_detection(
                self.node_code, species, scientific, conf, threat,
                LATITUDE, LONGITUDE, dist, self.fixed_heading, snapshot
            )
            print(f"[SQLite] Stored immediately in local edge database (ID #{det_id})")

            # D. Instant SMS Broadcast to Villagers & Rangers
            contacts = get_local_contacts()
            print(f"[SMS Gateway] Dispatching emergency alert to {len(contacts)} local contacts...")
            sent_cnt, failed_list, alert_msg, reports = self.sms_service.broadcast_alert(
                contacts, species, scientific, threat, self.node_code, SECTOR, dist
            )

            # Queue any failed SMS in offline fallback table
            for fail in failed_list:
                queue_sms_alert(det_id, fail["phone"], fail["name"], fail["message"], max_retries=3, error_msg=fail.get("error"))
                print(f"[Fallback Queue] SMS to {fail['phone']} queued in SQLite for auto-retry.")

            # E. Sync to Central HQ
            print("[Sync] Attempting real-time synchronization to Central HQ...")
            synced = self.sync_client.sync_pending_detections()
            if synced > 0:
                print(f"[Sync] [SUCCESS] Sighting #{det_id} synced to Central HQ successfully!")
            else:
                print("[Sync] [OFFLINE] Central HQ unreachable. Record safely queued in SQLite.")

        except Exception as e:
            print(f"[Edge Daemon Error] {e}")
        finally:
            self.is_busy = False

    def test_sync(self, species="tiger"):
        """Directly injects a test sighting to verify Edge DB -> Central HQ sync end-to-end."""
        print("\n" + "=" * 65)
        print(f"[TEST SYNC] Injecting verified test detection for: {species.upper()}")
        print("=" * 65)

        spec_map = {
            "tiger": ("Bengal Tiger", "Panthera tigris", "CRITICAL"),
            "leopard": ("Indian Leopard", "Panthera pardus", "CRITICAL")
        }
        common_name, scientific, threat = spec_map.get(species.lower(), ("Bengal Tiger", "Panthera tigris", "CRITICAL"))
        conf = 94.5
        dist = 250
        snapshot = "/static/snapshots/tiger_sample.jpg"

        det_id = log_local_detection(
            self.node_code, common_name, scientific, conf, threat,
            LATITUDE, LONGITUDE, dist, self.fixed_heading, snapshot
        )
        print(f"1. [SQLite] Inserted record #{det_id} into local edge.db (local_detections)")

        print(f"2. [Sync] Pushing record #{det_id} to Central HQ ({self.hq_url})...")
        synced = self.sync_client.sync_pending_detections()
        if synced > 0:
            print(f"3. [SUCCESS] Successfully synced record #{det_id} to Central HQ Dashboard!")
            print(f"   -> Check your browser dashboard at: {self.hq_url} to see the alert beacon!")
        else:
            print(f"3. [FAILED] Sync failed. Central HQ at {self.hq_url} did not accept the record.")
            print("   -> Make sure app.py is running and HQ URL is reachable.")

    def run(self, interval_sec=2.0):
        """Starts the edge station daemon."""
        self.is_running = True
        self.sync_client.start_background_sync(interval_sec=5)

        # Autonomous Edge SMS Retry Worker
        def sms_retry_loop():
            while getattr(self, "is_running", False):
                try:
                    res = flush_edge_sms_queue(self.sms_service)
                    if res["processed"] > 0:
                        print(f"[SMS Retry Engine] Processed {res['processed']} items: {res['delivered']} delivered.")
                except Exception:
                    pass
                time.sleep(10)

        import threading
        self.retry_thread = threading.Thread(target=sms_retry_loop, daemon=True)
        self.retry_thread.start()

        if self.enable_pir and self.pir:
            print("\n[ACTIVE] Edge Station is active in PIR WAKE MODE.")
            print("Press Ctrl+C to stop.\n")
            try:
                while self.is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            print(f"\n[ACTIVE] Edge Station is active in CONTINUOUS SURVEILLANCE MODE (Interval: {interval_sec}s).")
            print("Press Ctrl+C to stop.\n")
            try:
                while self.is_running:
                    self.process_cycle(trigger_reason="CONTINUOUS_SCAN")
                    time.sleep(interval_sec)
            except KeyboardInterrupt:
                pass

        print("\n[Edge] Shutting down station...")
        self.is_running = False
        if self.pir:
            self.pir.stop()
        self.sync_client.stop()
        self.camera.release()
        print("[Edge] Station safely halted.")

def main():
    parser = argparse.ArgumentParser(description="Project Indradhanu Headless Edge Station")
    parser.add_argument("--node", default=NODE_CODE, help="Station Node Code (e.g. NODE-01)")
    parser.add_argument("--hq", default=HQ_SERVER_URL, help="Central HQ server URL (e.g. http://127.0.0.1:5000)")
    parser.add_argument("--trigger-once", action="store_true", help="Trigger single camera capture and inference cycle immediately")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between camera scans in continuous mode (default: 2.0s)")
    parser.add_argument("--pir", action="store_true", help="Enable physical PIR motion sensor interrupt instead of continuous mode")
    parser.add_argument("--test-sync", choices=["tiger", "leopard"], nargs="?", const="tiger", help="Inject test detection into edge.db and sync to HQ")
    args = parser.parse_args()

    daemon = EdgeStationDaemon(node_code=args.node, hq_url=args.hq, enable_pir=args.pir)

    if args.test_sync:
        daemon.test_sync(species=args.test_sync)
    elif args.trigger_once:
        daemon.process_cycle(trigger_reason="TRIGGER_ONCE")
        daemon.sync_client.sync_pending_detections()
    else:
        daemon.run(interval_sec=args.interval)

if __name__ == "__main__":
    main()
