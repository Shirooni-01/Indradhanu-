"""
Master Headless Edge Daemon - Project Indradhanu
Runs autonomously on Raspberry Pi 3 Model B+ (Raspberry Pi OS Lite) edge camera stations.
Workflow:
  Camera Frame Capture -> Local 4-Species AI Detection (Tiger, Lion, Leopard, Bear)
  -> Snapshot Capture + Unique UUID event_id -> Local SQLite Buffer -> Authenticated Central Server Upload
"""

import sys
import os
import time
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")
import numpy as np

from edge.config import (
    NODE_CODE,
    SECTOR,
    LATITUDE,
    LONGITUDE,
    FIXED_HEADING_DEG,
    HQ_SERVER_URL,
    EDGE_API_KEY,
    PIR_ENABLED,
    CONFIDENCE_THRESHOLD,
    CAMERA_SOURCE,
)
from edge.database.edge_db import (
    init_edge_db,
    recover_pending_events_on_restart,
    log_local_detection,
    queue_sms_alert,
    get_local_contacts,
    log_edge_event,
    flush_edge_sms_queue,
)
from edge.hardware.pir_sensor import PIRSensor
from edge.hardware.thermal_camera import USBCamera
from edge.ml_engine.detector import WildlifeDetector
from edge.services.sms_service import SMSService
from edge.services.sync_client import SyncClient


SAMPLE_IMAGES_BY_SPECIES = {
    "tiger": "static/test_samples/bengal_tiger_og.jpg",
    "lion": "static/test_samples/asiatic_lion_og.jpg",
    "leopard": "static/test_samples/indian_leopard_og.jpg",
    "bear": "static/test_samples/sloth_bear_og.jpg",
}


class EdgeStationDaemon:
    def __init__(
        self,
        node_code=NODE_CODE,
        hq_url=HQ_SERVER_URL,
        api_key=EDGE_API_KEY,
        enable_pir=PIR_ENABLED,
        conf_thresh=CONFIDENCE_THRESHOLD,
        camera_source=None,
        init_camera=True,
    ):
        self.node_code = node_code
        self.hq_url = hq_url
        self.api_key = api_key
        self.enable_pir = enable_pir
        self.conf_thresh = float(conf_thresh)
        self.camera_source = str(camera_source).strip() if camera_source is not None else CAMERA_SOURCE
        self.fixed_heading = FIXED_HEADING_DEG

        print("=" * 68)
        print(f"[EDGE STATION] PROJECT INDRADHANU - NODE [{self.node_code}]")
        print(f"   Sector: {SECTOR}")
        print(f"   Location: {LATITUDE}, {LONGITUDE}")
        print(f"   Central Server: {self.hq_url}")
        print("   Target Hardware: Raspberry Pi 3 Model B+ (Raspberry Pi OS Lite)")
        print("   Supported Animals: Bengal Tiger, Asiatic Lion, Indian Leopard, Indian Sloth Bear")
        print(f"   Confidence Filter: >= {int(self.conf_thresh * 100)}%")
        print("=" * 68)

        # 1. Initialize local SQLite & recover any pending offline events from before restart
        init_edge_db()
        recovered = recover_pending_events_on_restart()
        print(f"[1/4] Local SQLite initialized (Pending unsynced events preserved: {recovered}).")

        # 2. Initialize Subsystems
        self.camera = USBCamera(source=self.camera_source) if init_camera else None
        self.ai_detector = WildlifeDetector(conf_thresh=self.conf_thresh)
        self.sms_service = SMSService()
        self.sync_client = SyncClient(hq_url=self.hq_url, node_code=self.node_code, api_key=self.api_key)

        # 3. Setup PIR Sensor if enabled, otherwise continuous loop
        self.is_busy = False
        if self.enable_pir:
            self.pir = PIRSensor(on_motion_callback=self.on_motion_detected)
            print("[2/4] PIR motion hardware interrupt armed.")
        else:
            self.pir = None
            print("[2/4] Operating in continuous monitoring mode.")

    def on_motion_detected(self):
        self.process_cycle(trigger_reason="PIR_WAKE")

    def process_cycle(self, trigger_reason="MANUAL_TRIGGER", input_image_path=None):
        """
        Core Edge Processing Loop:
        Capture Frame -> 4-Species AI Detection -> Snapshot & UUID event_id -> Local SQLite -> Central Upload.
        """
        if self.is_busy:
            return None

        self.is_busy = True
        try:
            log_edge_event(trigger_reason, f"Triggered on node {self.node_code}")

            if input_image_path:
                frame_data = {"frame": None, "snapshot_path": str(input_image_path)}
            else:
                frame_data = self.camera.capture_frame()
                if not frame_data or frame_data.get("frame") is None:
                    print(f"[Camera Warning] Frame capture failed on device {self.camera.source}.")
                    return None

            result = self.ai_detector.run_inference(frame_data)
            lat_ms = result.get("latency_ms", 0)

            if not result.get("detected"):
                print(f"[Edge AI] Scan complete ({lat_ms:.1f}ms). No target predator detected.")
                return result

            event_id = result["event_id"]
            species = result["species"]
            scientific = result["scientific_name"]
            threat = result["threat_level"]
            conf = result["confidence"]
            snapshot = result["snapshot_path"]
            bbox = result.get("bounding_box")
            dist = 280

            print(f"\n[EDGE DETECTION] {species.upper()} ({scientific}) | Event ID: {event_id}")
            print(f"   Confidence: {conf}% | Latency: {lat_ms:.1f}ms | Snapshot: {snapshot}")

            det_id, saved_event_id = log_local_detection(
                node_code=self.node_code,
                species=species,
                scientific_name=scientific,
                confidence=conf,
                threat_level=threat,
                lat=LATITUDE,
                lon=LONGITUDE,
                distance_m=dist,
                heading=self.fixed_heading,
                img_path=snapshot,
                event_id=event_id,
                bbox=bbox,
            )
            print(f"[Edge SQLite] Buffered detection #{det_id} (event_id={saved_event_id}) in edge.db")

            contacts = get_local_contacts()
            if contacts:
                _sent_cnt, failed_list, _alert_msg, _reports = self.sms_service.broadcast_alert(
                    contacts, species, scientific, threat, self.node_code, SECTOR, dist
                )
                for fail in failed_list:
                    queue_sms_alert(det_id, fail["phone"], fail["name"], fail["message"], max_retries=3, error_msg=fail.get("error"))

            print("[Sync] Uploading pending event & snapshot to Central Server for AI verification...")
            synced = self.sync_client.sync_pending_detections()
            if synced > 0:
                print(f"[Sync SUCCESS] Event {saved_event_id} uploaded and verified by Central Server!")
            else:
                print(f"[Sync OFFLINE] Central Server unreachable. Event {saved_event_id} preserved in local SQLite for retry.")

            return result
        except Exception as e:
            print(f"[Edge Daemon Error] {e}")
            return None
        finally:
            self.is_busy = False

    def test_sync(self, species="tiger"):
        """Runs real edge AI detection on a camera-trap test image for the specified species and syncs to Central Server."""
        root_dir = Path(__file__).resolve().parent.parent
        rel_sample = SAMPLE_IMAGES_BY_SPECIES.get(species.lower(), SAMPLE_IMAGES_BY_SPECIES["tiger"])
        sample_path = root_dir / rel_sample
        print(f"\n[TEST SYNC] Running Edge AI + Central Sync on {sample_path.name} ({species.upper()})...")
        return self.process_cycle(trigger_reason="TEST_SYNC", input_image_path=sample_path)

    def run(self, interval_sec=2.0):
        self.is_running = True
        self.sync_client.start_background_sync(interval_sec=5)

        def sms_retry_loop():
            while getattr(self, "is_running", False):
                try:
                    flush_edge_sms_queue(self.sms_service)
                except Exception:
                    pass
                time.sleep(10)

        import threading
        self.retry_thread = threading.Thread(target=sms_retry_loop, daemon=True)
        self.retry_thread.start()

        try:
            while self.is_running:
                if not self.enable_pir:
                    self.process_cycle(trigger_reason="CONTINUOUS_SCAN")
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            pass
        finally:
            self.is_running = False
            if self.pir:
                self.pir.stop()
            self.sync_client.stop()
            self.camera.release()
            print("[Edge] Station safely halted.")


def main():
    parser = argparse.ArgumentParser(description="Project Indradhanu Headless Edge Station")
    parser.add_argument("--node", default=NODE_CODE, help="Station Node Code (e.g. NODE-01, NODE-02)")
    parser.add_argument("--hq", default=HQ_SERVER_URL, help="Central Server URL (e.g. http://127.0.0.1:5000)")
    parser.add_argument("--api-key", default=EDGE_API_KEY, help="Edge authentication API key")
    parser.add_argument("--trigger-once", action="store_true", help="Trigger single camera capture and inference cycle")
    parser.add_argument("--image", default=None, help="Run single edge detection cycle on a specific image file")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between scans in continuous mode")
    parser.add_argument("--conf", type=float, default=CONFIDENCE_THRESHOLD, help="Confidence threshold 0.0-1.0")
    parser.add_argument("--pir", action="store_true", help="Enable physical PIR motion sensor interrupt")
    parser.add_argument("--camera", "--source", default=None, help="Camera device index")
    parser.add_argument(
        "--species",
        choices=["tiger", "lion", "leopard", "bear"],
        default=None,
        help="Target animal sample (tiger, lion, leopard, bear) when using --trigger-once without a camera",
    )
    parser.add_argument(
        "--test-sync",
        choices=["tiger", "lion", "leopard", "bear"],
        nargs="?",
        const="tiger",
        help="Run real edge detection on a test sample image (tiger, lion, leopard, bear) and sync to Central Server",
    )
    args = parser.parse_args()

    needs_camera = not (args.test_sync or args.species or args.image)
    daemon = EdgeStationDaemon(
        node_code=args.node,
        hq_url=args.hq,
        api_key=args.api_key,
        enable_pir=args.pir,
        conf_thresh=args.conf,
        camera_source=args.camera,
        init_camera=needs_camera,
    )

    if args.test_sync:
        daemon.test_sync(species=args.test_sync)
    elif args.species:
        daemon.test_sync(species=args.species)
    elif args.image:
        daemon.process_cycle(trigger_reason="IMAGE_INPUT", input_image_path=args.image)
    elif args.trigger_once:
        daemon.process_cycle(trigger_reason="TRIGGER_ONCE")
        daemon.sync_client.sync_pending_detections()
    else:
        daemon.run(interval_sec=args.interval)


if __name__ == "__main__":
    main()
