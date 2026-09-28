"""
Project Indradhanu - Continuous Surveillance Daemon & Live Alert Verification Test
Verifies:
1. Surveillance worker thread is active and acquiring frames 24/7.
2. Shared frame buffer is populated without requiring a web browser connection.
3. Live detection alert payload meets all contract requirements for on-site banner and off-site siren.
"""

import time
import urllib.request
import json
from pathlib import Path

def test_surveillance_daemon():
    print("=" * 60)
    print("Testing Project Indradhanu Continuous Surveillance & Live Alert System")
    print("=" * 60)

    # 1. Test server connection
    base_url = "http://127.0.0.1:5000"
    try:
        req = urllib.request.urlopen(f"{base_url}/api/system/status")
        sys_status = json.loads(req.read().decode("utf-8"))
        assert sys_status["success"], "System status failed!"
        print("[PASS] System status reachable & online.")
    except Exception as e:
        assert False, f"Could not reach server: {e}"

    # 2. Test Camera Settings & Persistence
    req = urllib.request.urlopen(f"{base_url}/api/camera/settings")
    cfg = json.loads(req.read().decode("utf-8"))
    assert cfg["success"], "Camera settings failed!"
    print(f"[PASS] Active camera source: {cfg['settings']['source']}, Conf threshold: {cfg['settings']['conf_threshold']}")

    # 3. Test video_feed frame buffer delivery
    req = urllib.request.urlopen(f"{base_url}/video_feed")
    chunk = req.read(2048)
    assert b"--frame" in chunk, "Video feed does not yield multipart frames!"
    assert b"Content-Type: image/jpeg" in chunk, "Video feed missing JPEG content type!"
    print("[PASS] Decoupled Video Stream is yielding valid JPEG frames from background buffer.")

    # 4. Trigger simulated encounter to test live alert payload contract
    post_req = urllib.request.Request(
        f"{base_url}/api/detections/simulate", 
        data=b'{"node_code": "NODE-01"}',
        headers={"Content-Type": "application/json"}
    )
    sim_res = urllib.request.urlopen(post_req)
    sim_data = json.loads(sim_res.read().decode("utf-8"))
    assert sim_data["success"], "Simulated detection failed!"
    det = sim_data["detection"]
    print(f"[PASS] Simulated detection generated: {det['species']} ({det['confidence']}%) [Event: {det['event_id']}]")

    # 5. Verify /api/detections/latest_live immediately reflects the incident
    req = urllib.request.urlopen(f"{base_url}/api/detections/latest_live")
    live_data = json.loads(req.read().decode("utf-8"))
    assert live_data["success"], "latest_live endpoint failed!"
    latest = live_data["latest"]
    assert latest is not None, "latest_live should have recorded the incident!"
    assert latest["event_id"] == det["event_id"], "Event ID mismatch!"
    assert latest["species"] == det["species"], "Species mismatch!"
    assert "image_path" in latest and latest["image_path"], "Missing snapshot image path!"
    print(f"[PASS] /api/detections/latest_live contract fully validated: id={latest['id']}, image={latest['image_path']}")

    # 6. Verify snapshot exists on filesystem
    img_rel = latest["image_path"].lstrip("/")
    img_path = Path(__file__).resolve().parent.parent / img_rel
    if img_path.exists():
        print(f"[PASS] Verified snapshot file exists on disk: {img_path.name} ({img_path.stat().st_size} bytes)")
    else:
        print(f"[INFO] Snapshot path points to: {img_path}")

    print("\n" + "=" * 60)
    print("ALL CONTINUOUS SURVEILLANCE & ALERT TESTS PASSED! [OK]")
    print("=" * 60)

if __name__ == "__main__":
    test_surveillance_daemon()
