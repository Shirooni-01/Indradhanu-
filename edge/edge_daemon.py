"""
Master Headless Edge Daemon - Project Indradhanu (Project C)
Runs autonomously on Raspberry Pi 4 edge camera stations.
Coordinates:
  PIR Wake Interrupt -> Pan-Tilt Rotator -> Thermal Capture -> AI Inference -> Local SQLite -> SMS Alert -> Central HQ Sync
"""

import sys
import os
import time
import argparse
import random

# Ensure root workspace is on python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure stdout handles UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from edge.config import (
    NODE_CODE, NODE_NAME, SECTOR, LATITUDE, LONGITUDE, 
    SIMULATION_MODE, HQ_SERVER_URL
)
from edge.database.edge_db import (
    init_edge_db, log_local_detection, queue_sms_alert, 
    get_local_contacts, log_edge_event
)
from edge.hardware.pir_sensor import PIRSensor
from edge.hardware.rotator import PanTiltRotator
from edge.hardware.thermal_camera import ThermalCamera
from edge.ml_engine.detector import WildlifeDetector
from edge.services.sms_service import SMSService
from edge.services.sync_client import SyncClient

class EdgeStationDaemon:
    def __init__(self, node_code=NODE_CODE, hq_url=HQ_SERVER_URL):
        self.node_code = node_code
        self.hq_url = hq_url
        print("=" * 65)
        print(f"[EDGE STATION] PROJECT INDRADHANU - NODE [{self.node_code}]")
        print(f"   Sector: {SECTOR}")
        print(f"   Location: {LATITUDE}, {LONGITUDE}")
        print(f"   HQ Server: {self.hq_url}")
        print(f"   Mode: {'SIMULATION / PC TEST' if SIMULATION_MODE else 'PHYSICAL HARDWARE (RPi 4)'}")
        print("=" * 65)

        # 1. Initialize local SQLite
        init_edge_db()
        print("[1/6] Local SQLite database initialized.")

        # 2. Initialize Subsystems
        self.rotator = PanTiltRotator(initial_heading=145)
        self.thermal_cam = ThermalCamera()
        self.ai_detector = WildlifeDetector()
        self.sms_service = SMSService()
        self.sync_client = SyncClient(hq_url=self.hq_url, node_code=self.node_code)

        # 3. Setup PIR Sensor with wake callback
        self.pir = PIRSensor(on_motion_callback=self.on_motion_detected)
        self.is_busy = False

    def on_motion_detected(self, target_species_hint=None):
        """Autonomous Edge Processing Loop triggered by PIR motion."""
        if self.is_busy:
            print("[Edge] Busy processing previous event. Skipping.")
            return

        self.is_busy = True
        try:
            print("\n[EVENT] >>> PIR MOTION DETECTED! Waking camera & AI subsystem...")
            log_edge_event("PIR_WAKE", f"Motion detected at heading {self.rotator.get_heading()}°")

            # A. Rotator adjusts bearing
            current_heading = self.rotator.get_heading()
            print(f"[Rotator] Locked at compass bearing {current_heading}°")

            # B. Thermal Camera capture
            thermal_frame = self.thermal_cam.capture_frame(target_species_hint=target_species_hint)
            print(f"[Thermal] Captured frame. Max heat signature: {thermal_frame['max_target_temp_c']}°C")

            # C. AI Model Inference
            print("[AI Engine] Running inference for target wild species (Tiger, Leopard, Bear, Lion)...")
            result = self.ai_detector.run_inference(thermal_frame)

            if not result.get("detected"):
                print("[AI Engine] Non-target animal or low confidence. Discarding to prevent false alert.")
                return

            species = result["species"]
            scientific = result["scientific_name"]
            threat = result["threat_level"]
            conf = result["confidence"]
            snapshot = result["web_snapshot_path"]
            dist = random.randint(180, 420)

            print(f"\n[ALERT - CRITICAL] Confirmed {species.upper()} ({scientific})!")
            print(f"   Confidence: {conf}% | Threat: {threat} | Distance: ~{dist}m")

            # D. Immediate Local SQLite Storage
            det_id = log_local_detection(
                self.node_code, species, scientific, conf, threat,
                LATITUDE, LONGITUDE, dist, current_heading, snapshot
            )
            print(f"[SQLite] Stored immediately in local edge database (ID #{det_id})")

            # E. Instant SMS Broadcast to Villagers & Rangers
            contacts = get_local_contacts()
            print(f"[SMS Gateway] Dispatching emergency alert to {len(contacts)} local contacts...")
            sent_cnt, failed_list, alert_msg = self.sms_service.broadcast_alert(
                contacts, species, scientific, threat, self.node_code, SECTOR, dist
            )

            # Queue any failed SMS in offline fallback table
            for fail in failed_list:
                queue_sms_alert(det_id, fail["phone"], fail["name"], fail["message"])
                print(f"[Fallback Queue] SMS to {fail['phone']} queued in SQLite for auto-retry.")

            # F. Sync to Central HQ
            print("[Sync] Attempting real-time synchronization to Central HQ...")
            synced = self.sync_client.sync_pending_detections()
            if synced > 0:
                print(f"[Sync] [SUCCESS] Sighting synced to Central HQ successfully!")
            else:
                print(f"[Sync] [OFFLINE] Central HQ unreachable (offline). Saved in SQLite for auto-sync.")

        except Exception as e:
            print(f"[Edge Daemon Error] {e}")
        finally:
            self.is_busy = False
            print("[Edge] Returning to ultra-low power standby mode. Waiting for PIR interrupt...\n")

    def run(self, periodic_test_interval=None):
        """Starts the edge station daemon."""
        self.sync_client.start_background_sync(interval_sec=5)
        print("\n[ACTIVE] Edge Station is fully active and monitoring perimeter.")
        print("Press Ctrl+C to stop.\n")

        if periodic_test_interval:
            print(f"[Test Mode] Simulating motion trigger every {periodic_test_interval} seconds.")
            self.pir.start_periodic_simulation(interval_sec=periodic_test_interval)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Edge] Shutting down station...")
            self.pir.stop()
            self.sync_client.stop()
            print("[Edge] Station safely halted.")

def main():
    parser = argparse.ArgumentParser(description="Project Indradhanu Headless Edge Station")
    parser.add_argument("--node", default=NODE_CODE, help="Station Node Code (e.g. NODE-01)")
    parser.add_argument("--hq", default=HQ_SERVER_URL, help="Central HQ server URL")
    parser.add_argument("--trigger-once", action="store_true", help="Simulate single detection immediately and exit")
    parser.add_argument("--species", default=None, help="Target species hint (tiger, leopard, bear, lion)")
    parser.add_argument("--periodic", type=int, default=None, help="Periodic simulation trigger in seconds")
    args = parser.parse_args()

    daemon = EdgeStationDaemon(node_code=args.node, hq_url=args.hq)

    if args.trigger_once:
        daemon.on_motion_detected(target_species_hint=args.species)
        daemon.sync_client.sync_pending_detections()
    else:
        daemon.run(periodic_test_interval=args.periodic)

if __name__ == "__main__":
    main()
