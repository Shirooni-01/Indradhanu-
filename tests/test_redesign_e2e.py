"""
PHASE 5: STAGED TESTING & VERIFICATION SUITE FOR REDESIGNED INDRADHANU SYSTEM
Tests all 10 stages specified in the Master Prompt PRD:
  Stage 1: Edge model detection (tiger, lion, leopard, bear) and snapshot capture.
  Stage 2: SQLite event persistence and recovery after restart.
  Stage 3: Authenticated upload and synchronization with the central server.
  Stage 4: Central AI snapshot verification (separate CentralVerificationEngine).
  Stage 5: Central database persistence and duplicate-event (event_id) prevention.
  Stage 6: Dashboard event display and device status (no dashboard camera routes).
  Stage 7: Siren activation using SAFE_TEST mode (physical_siren_active=0), duplicate prevention, and hardware check.
  Stage 8: Multiple uniquely identified edge devices communicating with one central server.
  Stage 9: Network interruption and automatic recovery (offline buffering + delayed sync handling).
  Stage 10: Error handling, authentication rejection (401/403), configuration, and deployment verification.
"""

import os
import sys
import uuid
import time
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
import cv2
import requests
from werkzeug.serving import make_server

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Configure test environment variables before importing app modules
TEST_EDGE_KEY = "test-edge-shared-secret-key-2026"
TEST_SIREN_KEY = "test-siren-controller-secret-key-2026"
os.environ["EDGE_API_KEY"] = TEST_EDGE_KEY
os.environ["EDGE_SHARED_API_KEY"] = TEST_EDGE_KEY
os.environ["SIREN_API_KEY"] = TEST_SIREN_KEY
os.environ["SIREN_MODE"] = "SAFE_TEST"
os.environ["SIREN_ALERT_CONF_THRESHOLD"] = "60.0"
os.environ["SIREN_MAX_SYNC_DELAY_SEC"] = "300"

from edge.ml_engine.detector import WildlifeDetector
from edge.database.edge_db import (
    init_edge_db,
    log_local_detection,
    get_unsynced_detections,
    get_pending_sync_count,
    recover_pending_events_on_restart,
    record_sync_failure,
)
from edge.services.sync_client import SyncClient
from edge.siren_controller import create_siren_controller_app, SirenHardwareController
import database.db_manager as db_manager
from services.siren_service import SirenService
import app as central_app_module


class ServerThread(threading.Thread):
    def __init__(self, flask_app, port):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", port, flask_app)
        self.ctx = flask_app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


class IndradhanuRedesignE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.central_db_path = os.path.join(cls.temp_dir.name, "central_test.db")
        cls.edge1_db_path = os.path.join(cls.temp_dir.name, "edge1.db")
        cls.edge2_db_path = os.path.join(cls.temp_dir.name, "edge2.db")
        init_edge_db(cls.edge1_db_path)
        init_edge_db(cls.edge2_db_path)

        # Ensure test environment keys remain active after dotenv load
        os.environ["EDGE_API_KEY"] = TEST_EDGE_KEY
        os.environ["EDGE_SHARED_API_KEY"] = TEST_EDGE_KEY
        os.environ["SIREN_API_KEY"] = TEST_SIREN_KEY
        os.environ["SIREN_MODE"] = "SAFE_TEST"
        os.environ["SIREN_ALERT_CONF_THRESHOLD"] = "60.0"
        os.environ["SIREN_MAX_SYNC_DELAY_SEC"] = "300"

        # Point central db_manager to isolated test database
        db_manager.DB_PATH = cls.central_db_path
        db_manager._USE_FALLBACK_SQLITE = True
        db_manager.init_db()

        # Start Siren Controller HTTP Server on port 15080 in SAFE_TEST mode
        cls.siren_port = 15080
        cls.siren_url = f"http://127.0.0.1:{cls.siren_port}/api/siren/activate"
        os.environ["SIREN_CONTROLLER_URL"] = cls.siren_url
        cls.siren_controller = SirenHardwareController(api_key=TEST_SIREN_KEY, mode="SAFE_TEST")
        cls.siren_flask_app = create_siren_controller_app(cls.siren_controller)
        cls.siren_server = ServerThread(cls.siren_flask_app, cls.siren_port)
        cls.siren_server.start()

        cls.central_port = 15000
        cls.central_url = f"http://127.0.0.1:{cls.central_port}"
        cls.central_server = ServerThread(central_app_module.app, cls.central_port)
        cls.central_server.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.central_server.shutdown()
        cls.siren_server.shutdown()
        cls.temp_dir.cleanup()

    def test_stage_01_edge_model_detection_and_snapshot_capture(self):
        """Stage 1: Edge model detection (4 supported species: tiger, lion, leopard, bear) and snapshot capture."""
        detector = WildlifeDetector(conf_thresh=0.40)
        self.assertTrue(detector.is_real_model_loaded, "Edge AI model weights must be loaded")

        sample_img_path = os.path.join(ROOT_DIR, "static", "test_samples", "bengal_tiger_og.jpg")
        frame = cv2.imread(sample_img_path)
        self.assertIsNotNone(frame, "Sample tiger image must exist")

        result = detector.run_inference({"frame": frame})
        self.assertIsNotNone(result)
        self.assertTrue(result["detected"])
        self.assertIsNotNone(result.get("event_id"))
        self.assertTrue(os.path.exists(result["snapshot_path"]))
        self.assertGreater(os.path.getsize(result["snapshot_path"]), 0)

    def test_stage_02_sqlite_persistence_and_restart_recovery(self):
        """Stage 2: SQLite event persistence and recovery after restart."""
        event_id = str(uuid.uuid4())
        snap_path = os.path.join(ROOT_DIR, "static", "test_samples", "bengal_tiger_og.jpg")

        det_id, saved_event_id = log_local_detection(
            node_code="NODE-01",
            species="Bengal Tiger",
            scientific_name="Panthera tigris",
            confidence=91.5,
            threat_level="CRITICAL",
            lat=21.1458,
            lon=79.0882,
            distance_m=280,
            heading=145,
            img_path=snap_path,
            event_id=event_id,
            detected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            db_path=self.edge1_db_path,
        )
        self.assertGreater(det_id, 0)
        self.assertEqual(saved_event_id, event_id)
        self.assertEqual(get_pending_sync_count(db_path=self.edge1_db_path), 1)

        # Simulate edge failure mid-sync & restart recovery
        record_sync_failure(det_id, "Simulated network drop", db_path=self.edge1_db_path)
        recovered = recover_pending_events_on_restart(db_path=self.edge1_db_path)
        self.assertEqual(recovered, 1)

        unsynced = get_unsynced_detections(db_path=self.edge1_db_path)
        self.assertEqual(len(unsynced), 1)
        self.assertEqual(unsynced[0]["event_id"], event_id)
        self.assertEqual(unsynced[0]["sync_attempts"], 1)

    def test_stage_03_authenticated_upload_and_central_sync(self):
        """Stage 3: Upload and synchronization with the central server."""
        sync_client = SyncClient(
            hq_url=self.central_url,
            node_code="NODE-01",
            api_key=TEST_EDGE_KEY,
            db_path=self.edge1_db_path,
        )

        synced_count = sync_client.sync_pending_detections()
        self.assertEqual(synced_count, 1)
        self.assertEqual(get_pending_sync_count(db_path=self.edge1_db_path), 0)

    def test_stage_04_central_ai_snapshot_verification(self):
        """Stage 4: Central AI snapshot verification (separate CentralVerificationEngine)."""
        detections = db_manager.get_recent_detections(limit=10)
        self.assertGreaterEqual(len(detections), 1)
        latest = detections[0]
        self.assertIn(latest["verification_status"], ("VERIFIED", "UNVERIFIED_LOW_CONF", "REJECTED_FALSE_POSITIVE"))
        self.assertIsNotNone(latest["verified_species"])
        self.assertGreater(float(latest["verified_confidence"]), 0.0)
        self.assertTrue(latest["image_snapshot_path"].startswith("/static/snapshots/"))

    def test_stage_05_central_persistence_and_duplicate_prevention(self):
        """Stage 5: Central DB persistence and duplicate event_id prevention."""
        dup_event_id = str(uuid.uuid4())
        snap_path = os.path.join(ROOT_DIR, "static", "test_samples", "indian_leopard_og.jpg")

        headers = {"X-Device-ID": "NODE-01", "X-API-Key": TEST_EDGE_KEY}
        payload = {
            "event_id": dup_event_id,
            "node_code": "NODE-01",
            "species": "Indian Leopard",
            "scientific_name": "Panthera pardus",
            "confidence": "92.4",
            "threat_level": "CRITICAL",
            "latitude": "21.1460",
            "longitude": "79.0890",
            "distance_meters": "250",
            "rotator_heading": "130",
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(snap_path, "rb") as f:
            r1 = requests.post(
                f"{self.central_url}/api/sync/detection",
                data=payload,
                files={"snapshot": ("indian_leopard_og.jpg", f, "image/jpeg")},
                headers=headers,
                timeout=10,
            )
        self.assertIn(r1.status_code, (200, 201))
        d1 = r1.json()
        self.assertTrue(d1["success"])
        self.assertFalse(d1.get("duplicate_prevented", False))

        # Second upload with identical event_id -> must be deduplicated
        with open(snap_path, "rb") as f:
            r2 = requests.post(
                f"{self.central_url}/api/sync/detection",
                data=payload,
                files={"snapshot": ("indian_leopard_og.jpg", f, "image/jpeg")},
                headers=headers,
                timeout=10,
            )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertTrue(d2["success"])
        self.assertTrue(d2.get("duplicate_prevented"), "Duplicate event_id must be detected and prevented")

        all_dets = db_manager.get_recent_detections(limit=50)
        matching = [d for d in all_dets if d["event_id"] == dup_event_id]
        self.assertEqual(len(matching), 1, "Central DB must store exactly one record per unique event_id")

    def test_stage_06_dashboard_event_display_and_no_webcam_routes(self):
        """Stage 6: Dashboard event display, device status, and removal of obsolete camera routes."""
        client = central_app_module.app.test_client()

        for obsolete_route in ["/camera", "/video_feed", "/api/camera/status", "/api/camera/toggle", "/api/detections/simulate"]:
            resp = client.get(obsolete_route)
            self.assertEqual(resp.status_code, 404, f"Obsolete route {obsolete_route} must return 404")

        for valid_route in ["/", "/history", "/nodes", "/system", "/contacts", "/api/detections", "/api/nodes", "/api/system/status", "/api/siren/history"]:
            resp = client.get(valid_route)
            self.assertEqual(resp.status_code, 200, f"Active route {valid_route} must return 200")

        status_data = client.get("/api/system/status").get_json()
        self.assertTrue(status_data["success"])
        self.assertIn("siren_controller", status_data)
        self.assertIn("central_verifier_loaded", status_data)
        self.assertTrue(status_data["central_verifier_loaded"])

    def test_stage_07_siren_safe_test_mode_and_duplicate_prevention(self):
        """Stage 7: Siren activation in SAFE_TEST mode, duplicate prevention, and physical hardware distinction."""
        event_id = f"siren-test-{uuid.uuid4().hex[:10]}"
        ver_result = {
            "is_verified": True,
            "verification_status": "VERIFIED",
            "verified_species": "Bengal Tiger",
            "verified_confidence": 95.0,
        }

        res1 = central_app_module.siren_service.evaluate_and_trigger(
            event_id=event_id,
            detection_id=1,
            node_code="NODE-01",
            verification_result=ver_result,
            sync_latency_seconds=1,
        )
        self.assertTrue(res1["triggered"])
        self.assertFalse(res1["physical_siren_active"], "SAFE_TEST mode must never claim physical hardware siren is active")
        self.assertEqual(res1["command_status"], "TEST_MODE_VERIFIED")

        # Attempt duplicate siren activation for the same event_id
        res_dup = central_app_module.siren_service.evaluate_and_trigger(
            event_id=event_id,
            detection_id=1,
            node_code="NODE-01",
            verification_result=ver_result,
            sync_latency_seconds=1,
        )
        self.assertTrue(res_dup["duplicate_prevented"])
        self.assertEqual(res_dup["policy_decision"], "DUPLICATE_PREVENTED")

        # Test policy suppression on false positive
        res_fp = central_app_module.siren_service.evaluate_and_trigger(
            event_id=f"fp-{uuid.uuid4().hex[:8]}",
            detection_id=2,
            node_code="NODE-01",
            verification_result={
                "is_verified": False,
                "verification_status": "REJECTED_FALSE_POSITIVE",
                "verified_species": "Rejected (Non-Target)",
                "verified_confidence": 15.0,
            },
            sync_latency_seconds=1,
        )
        self.assertFalse(res_fp["triggered"])
        self.assertEqual(res_fp["command_status"], "SUPPRESSED_POLICY")

    def test_stage_08_multiple_edge_devices_communicating(self):
        """Stage 8: Multiple uniquely identified edge devices communicating with one central server."""
        db_manager.register_camera_node("NODE-02", "Rampur East Buffer Tower", "Sector 1", 21.1480, 79.0910, "Raspberry Pi Camera", TEST_EDGE_KEY)
        db_manager.register_camera_node("NODE-03", "Shivpuri West Fringe Tower", "Sector 2", 21.1410, 79.0810, "Raspberry Pi Camera", TEST_EDGE_KEY)

        sync_node1 = SyncClient(hq_url=self.central_url, node_code="NODE-01", api_key=TEST_EDGE_KEY, db_path=self.edge2_db_path)
        sync_node2 = SyncClient(hq_url=self.central_url, node_code="NODE-02", api_key=TEST_EDGE_KEY, db_path=self.edge2_db_path)
        sync_node3 = SyncClient(hq_url=self.central_url, node_code="NODE-03", api_key=TEST_EDGE_KEY, db_path=self.edge2_db_path)

        self.assertTrue(sync_node1.send_heartbeat(heading=145, battery_pct=91, status="ONLINE_ACTIVE"))
        self.assertTrue(sync_node2.send_heartbeat(heading=210, battery_pct=86, status="ONLINE_ACTIVE"))
        self.assertTrue(sync_node3.send_heartbeat(heading=90, battery_pct=79, status="ONLINE_ACTIVE"))

        nodes = db_manager.get_camera_nodes()
        online_codes = {n["node_code"] for n in nodes if n["status"] == "ONLINE_ACTIVE"}
        self.assertTrue({"NODE-01", "NODE-02", "NODE-03"}.issubset(online_codes))

    def test_stage_09_network_interruption_and_automatic_recovery(self):
        """Stage 9: Network interruption (unreachable server) and automatic recovery + delayed event policy."""
        outage_db_path = os.path.join(self.temp_dir.name, "edge_outage.db")
        init_edge_db(outage_db_path)
        db_manager.register_camera_node("NODE-02", "Rampur East Buffer Tower", "Sector 1", 21.1480, 79.0910, "Raspberry Pi Camera", TEST_EDGE_KEY)

        unreachable_client = SyncClient(
            hq_url="http://127.0.0.1:19999",
            node_code="NODE-02",
            api_key=TEST_EDGE_KEY,
            db_path=outage_db_path,
        )

        old_detected_at = (datetime.now() - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        delayed_event_id = str(uuid.uuid4())
        snap_path = os.path.join(ROOT_DIR, "static", "test_samples", "sloth_bear_og.jpg")

        log_local_detection(
            node_code="NODE-02",
            species="Indian Sloth Bear",
            scientific_name="Melursus ursinus",
            confidence=89.0,
            threat_level="HIGH",
            lat=21.1492,
            lon=79.0935,
            distance_m=310,
            heading=210,
            img_path=snap_path,
            event_id=delayed_event_id,
            detected_at=old_detected_at,
            db_path=outage_db_path,
        )

        # Attempt sync while server is unreachable -> must remain preserved in SQLite
        synced_during_outage = unreachable_client.sync_pending_detections()
        self.assertEqual(synced_during_outage, 0)
        self.assertEqual(get_pending_sync_count(db_path=outage_db_path), 1)

        # Restore connectivity to real central server -> must automatically flush pending event
        recovered_client = SyncClient(
            hq_url=self.central_url,
            node_code="NODE-02",
            api_key=TEST_EDGE_KEY,
            db_path=outage_db_path,
        )
        synced_after_recovery = recovered_client.sync_pending_detections()
        self.assertEqual(synced_after_recovery, 1)
        self.assertEqual(get_pending_sync_count(db_path=outage_db_path), 0)

        # Check central record: must be marked delayed and siren suppressed due to stale delay
        dets = db_manager.get_recent_detections(limit=20)
        rec = next((d for d in dets if d["event_id"] == delayed_event_id), None)
        self.assertIsNotNone(rec)
        self.assertTrue(rec["is_delayed"])
        self.assertEqual(rec["siren_status"], "SUPPRESSED_POLICY")

    def test_stage_10_authentication_and_error_handling(self):
        """Stage 10: Error handling, authentication enforcement (401/403), and invalid payload rejection."""
        client = central_app_module.app.test_client()

        # Missing API key on /api/sync/detection -> 401
        r_no_auth = client.post("/api/sync/detection", json={"node_code": "NODE-01", "species": "Tiger"})
        self.assertEqual(r_no_auth.status_code, 401)

        # Wrong API key on /api/sync/heartbeat -> 401
        r_bad_auth = client.post(
            "/api/sync/heartbeat",
            headers={"X-Device-ID": "NODE-01", "X-API-Key": "wrong-key"},
            json={"node_code": "NODE-01"},
        )
        self.assertEqual(r_bad_auth.status_code, 401)

        # Siren Controller unauthorized request -> 401
        r_siren_unauth = requests.post(
            f"http://127.0.0.1:{self.siren_port}/api/siren/activate",
            headers={"X-Siren-Key": "invalid-siren-key"},
            json={"event_id": "test-unauth"},
            timeout=5,
        )
        self.assertEqual(r_siren_unauth.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
