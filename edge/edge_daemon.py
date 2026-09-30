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
    FIXED_HEADING_DEG, SIMULATION_MODE, HQ_SERVER_URL
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
    def __init__(self, node_code=NODE_CODE, hq_url=HQ_SERVER_URL):
        self.node_code = node_code
        self.hq_url = hq_url
        self.fixed_heading = FIXED_HEADING_DEG
        print("=" * 65)
        print(f"[EDGE STATION] PROJECT INDRADHANU - NODE [{self.node_code}]")
        print(f"   Sector: {SECTOR}")
        print(f"   Location: {LATITUDE}, {LONGITUDE}")
        print(f"   Heading: {self.fixed_heading}° (Fixed Direction)")
        print(f"   HQ Server: {self.hq_url}")
        print(f"   Hardware: Raspberry Pi 3 B+ (USB Optical Surveillance)")
        print("=" * 65)

        # 1. Initialize local SQLite
        init_edge_db()
        print("[1/5] Local SQLite database verified.")

        # 2. Initialize Subsystems
        self.camera = USBCamera()
        self.ai_detector = WildlifeDetector()
        self.sms_service = SMSService()
        self.sync_client = SyncClient(hq_url=self.hq_url, node_code=self.node_code)

        # 3. Setup PIR Sensor with wake callback
        self.pir = PIRSensor(on_motion_callback=self.on_motion_detected)
        self.is_busy = False

    def on_motion_detected(self):
        """Autonomous Edge Processing Loop triggered by PIR motion interrupt."""
        if self.is_busy:
            print("[Edge] Busy processing previous event. Skipping duplicate interrupt.")
            return

        self.is_busy = True
        try:
            print("\n[EVENT] >>> PIR MOTION DETECTED! Waking camera & AI subsystem...")
            log_edge_event("PIR_WAKE", f"Motion interrupt detected at fixed heading {self.fixed_heading}°")

            # A. USB Camera Frame Capture
            frame_data = self.camera.capture_frame()
            if not frame_data or frame_data.get("frame") is None:
                print("[Camera Warning] Frame capture failed. Aborting detection cycle.")
                return

            # B. Real AI Model Inference (Strictly Tiger & Leopard)
            print("[AI Engine] Running inference for target species (Bengal Tiger, Indian Leopard)...")
            result = self.ai_detector.run_inference(frame_data)

            if not result.get("detected"):
                print("[AI Engine] Frame clear. Non-target animal or no predator detected.")
                return

            species = result["species"]
            scientific = result["scientific_name"]
            threat = result["threat_level"]
            conf = result["confidence"]
            snapshot = result["web_snapshot_path"]
            dist = 280  # Estimated perimeter distance

            print(f"\n[ALERT - CRITICAL] Confirmed {species.upper()} ({scientific})!")
            print(f"   Confidence: {conf}% | Threat: {threat} | Heading: {self.fixed_heading}°")

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
                print("[Sync] [SUCCESS] Sighting synced to Central HQ successfully!")
            else:
                print("[Sync] [OFFLINE] Central HQ unreachable. Saved in SQLite for background sync.")

        except Exception as e:
            print(f"[Edge Daemon Error] {e}")
        finally:
            self.is_busy = False
            print("[Edge] Returning to standby mode. Waiting for PIR interrupt...\n")

    def run(self):
        """Starts the edge station daemon."""
        self.is_running = True
        self.sync_client.start_background_sync(interval_sec=5)

        # Autonomous Edge SMS Retry Worker
        def sms_retry_loop():
            while getattr(self, "is_running", False):
                try:
                    res = flush_edge_sms_queue(self.sms_service)
                    if res["processed"] > 0:
                        print(f"[SMS Retry Engine] Processed {res['processed']} items: {res['delivered']} delivered, {res['retrying']} scheduled backoff, {res['failed_permanent']} permanently failed.")
                except Exception:
                    pass
                time.sleep(10)

        import threading
        self.retry_thread = threading.Thread(target=sms_retry_loop, daemon=True)
        self.retry_thread.start()

        print("\n[ACTIVE] Edge Station is fully active and monitoring perimeter.")
        print("Press Ctrl+C to stop.\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Edge] Shutting down station...")
            self.is_running = False
            self.pir.stop()
            self.sync_client.stop()
            self.camera.release()
            print("[Edge] Station safely halted.")

def main():
    parser = argparse.ArgumentParser(description="Project Indradhanu Headless Edge Station")
    parser.add_argument("--node", default=NODE_CODE, help="Station Node Code (e.g. NODE-01)")
    parser.add_argument("--hq", default=HQ_SERVER_URL, help="Central HQ server URL")
    parser.add_argument("--trigger-once", action="store_true", help="Trigger single camera capture and inference cycle immediately")
    args = parser.parse_args()

    daemon = EdgeStationDaemon(node_code=args.node, hq_url=args.hq)

    if args.trigger_once:
        daemon.on_motion_detected()
        daemon.sync_client.sync_pending_detections()
    else:
        daemon.run()

if __name__ == "__main__":
    main()
