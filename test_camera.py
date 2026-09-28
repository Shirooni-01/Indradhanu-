"""
Project Indradhanu - Real-Time Camera Surveillance & AI Detection HUD
Target: Real-time Tiger & Leopard detection using webcam / USB / thermal camera.
"""

import os
import sys
import time
import argparse
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPECIES_METADATA = {
    0: {"name": "Bengal Tiger", "color": (0, 140, 255), "threat": "CRITICAL"},      # Amber / Orange
    1: {"name": "Indian Leopard", "color": (0, 215, 255), "threat": "CRITICAL"}    # Yellow
}

def apply_simulated_thermal(frame):
    """Converts standard RGB webcam frame to thermal surveillance palette (Inferno/Ironbow)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    thermal = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
    return thermal

def draw_hud(frame, boxes, names, fps, infer_ms, thermal_mode, conf_thresh):
    """Renders the Indradhanu tactical surveillance HUD over the video frame."""
    h, w = frame.shape[:2]
    hud = frame.copy()

    # 1. Top Status Banner
    cv2.rectangle(hud, (0, 0), (w, 42), (18, 18, 18), -1)
    cv2.line(hud, (0, 42), (w, 42), (50, 50, 50), 1)

    # Title & Telemetry
    cv2.putText(hud, "INDRADHANU EDGE AI SURVEILLANCE", (16, 26), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2, cv2.LINE_AA)
    
    fps_text = f"FPS: {fps:4.1f} | INFER: {infer_ms:4.1f}ms | CONF: {conf_thresh:.2f}"
    cv2.putText(hud, fps_text, (w - 380, 26), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

    # 2. Threat Status
    detected_count = len(boxes)
    if detected_count > 0:
        alert_bg = (0, 0, 180)
        status_msg = f"⚠️ ALERT: {detected_count} THREAT(S) DETECTED"
        status_color = (255, 255, 255)
    else:
        alert_bg = (20, 60, 20)
        status_msg = "PERIMETER SECURE"
        status_color = (0, 255, 100)

    # Threat Badge (Top center)
    badge_w = 260
    bx1 = (w - badge_w) // 2
    cv2.rectangle(hud, (bx1, 4), (bx1 + badge_w, 36), alert_bg, -1)
    cv2.rectangle(hud, (bx1, 4), (bx1 + badge_w, 36), status_color, 1)
    (tw, _), _ = cv2.getTextSize(status_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(hud, status_msg, (bx1 + (badge_w - tw) // 2, 25), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 2, cv2.LINE_AA)

    # 3. Bottom Hotkey Help Bar
    cv2.rectangle(hud, (0, h - 30), (w, h), (18, 18, 18), -1)
    thermal_label = "ON" if thermal_mode else "OFF"
    help_text = f"[Q] Quit  |  [S] Save Snapshot  |  [T] Thermal Mode: {thermal_label}  |  [+/-] Conf Thresh"
    cv2.putText(hud, help_text, (16, h - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA)

    # 4. Target Bounding Boxes & Tactical Reticles
    for box in boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

        meta = SPECIES_METADATA.get(cls_id, {"name": names.get(cls_id, "Target"), "color": (0, 255, 0), "threat": "HIGH"})
        color = meta["color"]

        # Main box
        cv2.rectangle(hud, (x1, y1), (x2, y2), color, 2)

        # Tactical Corner Accents
        corner_len = min(22, (x2 - x1) // 4, (y2 - y1) // 4)
        thick = 4
        # Top-left
        cv2.line(hud, (x1, y1), (x1 + corner_len, y1), color, thick)
        cv2.line(hud, (x1, y1), (x1, y1 + corner_len), color, thick)
        # Top-right
        cv2.line(hud, (x2, y1), (x2 - corner_len, y1), color, thick)
        cv2.line(hud, (x2, y1), (x2, y1 + corner_len), color, thick)
        # Bottom-left
        cv2.line(hud, (x1, y2), (x1 + corner_len, y2), color, thick)
        cv2.line(hud, (x1, y2), (x1, y2 - corner_len), color, thick)
        # Bottom-right
        cv2.line(hud, (x2, y2), (x2 - corner_len, y2), color, thick)
        cv2.line(hud, (x2, y2), (x2, y2 - corner_len), color, thick)

        # Reticle Crosshair
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.circle(hud, (cx, cy), 5, color, 1)
        cv2.line(hud, (cx - 10, cy), (cx + 10, cy), color, 1)
        cv2.line(hud, (cx, cy - 10), (cx, cy + 10), color, 1)

        # Badge Label
        badge_text = f"{meta['name'].upper()} {conf:.1%} [{meta['threat']}]"
        (bw, bh), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        label_y1 = max(46, y1 - bh - 8)
        cv2.rectangle(hud, (x1, label_y1), (x1 + bw + 12, label_y1 + bh + 8), color, -1)
        cv2.putText(hud, badge_text, (x1 + 6, label_y1 + bh + 3), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

    return hud

def main():
    parser = argparse.ArgumentParser(description="Real-time Camera AI Vision for Project Indradhanu")
    parser.add_argument("--source", "--camera", type=str, default="0", help="Camera index (0, 1) or IP stream URL (http://192.168.x.x:8080/video)")
    parser.add_argument("--weights", type=str, default="ml_engine/weights/indradhanu_best.pt", help="Path to weights")
    parser.add_argument("--conf", type=float, default=0.45, help="Confidence threshold (default: 0.45)")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference resolution (default: 640)")
    parser.add_argument("--thermal", action="store_true", help="Start in simulated thermal camera mode")
    parser.add_argument("--device", type=str, default="0", help="CUDA device index or 'cpu'")
    args = parser.parse_args()

    # Determine if source is an integer index or a URL / stream
    is_cam_idx = args.source.isdigit()
    camera_source = int(args.source) if is_cam_idx else args.source

    print("=" * 70)
    print(" 🐅 PROJECT INDRADHANU — LIVE REAL-TIME CAMERA AI MONITOR")
    print(f" Video Source  : {camera_source}")
    print(f" Model Weights : {args.weights}")
    print("=" * 70)

    # 1. Load YOLO Model
    weights_path = Path(args.weights)
    if not weights_path.exists():
        print(f"❌ Error: Model weights '{args.weights}' not found!")
        sys.exit(1)

    print(f"[+] Loading model into memory...")
    model = YOLO(str(weights_path))

    # 2. Open Camera
    print(f"[+] Connecting to video source: {camera_source} ...")
    if is_cam_idx:
        # On Windows, cv2.CAP_DSHOW provides fast startup for USB/webcams
        cap = cv2.VideoCapture(camera_source, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print("[!] DirectShow failed, attempting standard VideoCapture...")
            cap = cv2.VideoCapture(camera_source)
    else:
        # Stream URL (e.g. HTTP, RTSP) or video file
        cap = cv2.VideoCapture(camera_source)

    if not cap.isOpened():
        print(f"\n❌ Error: Could not connect to source: {camera_source}")
        if is_cam_idx:
            print("   Tips:")
            print("   1. Check webcam connections and privacy permissions in Windows Settings.")
            print("   2. If using DroidCam / Iriun, verify the client app is running on PC.")
        else:
            print("   Tips:")
            print("   1. Verify your phone and laptop are on the same Wi-Fi network.")
            print("   2. Make sure the streaming app on your phone (e.g., 'IP Webcam') is running.")
            print("   3. Check the exact URL shown on your phone screen (e.g., http://192.168.1.X:8080/video).")
        sys.exit(1)

    if is_cam_idx:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[+] Camera active! Resolution: {actual_w}x{actual_h}")
    print("\n[💡 HOW TO TEST]:")
    print("  👉 Point your camera at a picture or YouTube video of a TIGER or LEOPARD (e.g. on your phone).")
    print("  👉 Press [T] to toggle Thermal Vision Mode (Ironbow/Inferno palette).")
    print("  👉 Press [S] to capture and save a high-res verified snapshot.")
    print("  👉 Press [Q] or [ESC] to exit.\n")

    snapshots_dir = Path("static/snapshots")
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    thermal_mode = args.thermal
    conf_thresh = args.conf
    prev_time = time.time()
    fps_smooth = 30.0

    window_name = "Indradhanu Edge AI - Live Tactical Feed"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1024, 576)

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[-] Warning: Failed to read frame from camera.")
                time.sleep(0.05)
                continue

            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            if dt > 0:
                fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt)

            # Optional: Thermal mode preprocessing
            display_frame = apply_simulated_thermal(frame) if thermal_mode else frame

            # Run YOLO Inference
            infer_start = time.time()
            results = model.predict(
                frame, 
                conf=conf_thresh, 
                imgsz=args.imgsz, 
                device=args.device,
                verbose=False
            )
            infer_ms = (time.time() - infer_start) * 1000.0

            boxes = results[0].boxes
            annotated = draw_hud(display_frame, boxes, model.names, fps_smooth, infer_ms, thermal_mode, conf_thresh)

            cv2.imshow(window_name, annotated)

            # Keyboard controls
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # Q or ESC
                print("[+] Exiting camera stream...")
                break
            elif key == ord('t') or key == ord('T'):
                thermal_mode = not thermal_mode
                print(f"[+] Thermal Vision Mode: {'ACTIVE 🔥' if thermal_mode else 'OFF'}")
            elif key == ord('s') or key == ord('S'):
                snap_id = int(time.time())
                snap_path = snapshots_dir / f"live_detection_{snap_id}.jpg"
                cv2.imwrite(str(snap_path), annotated)
                print(f"[📸 SNAPSHOT SAVED]: {snap_path.resolve()}")
            elif key == ord('+') or key == ord('='):
                conf_thresh = min(0.95, conf_thresh + 0.05)
                print(f"[+] Confidence threshold increased to: {conf_thresh:.2f}")
            elif key == ord('-') or key == ord('_'):
                conf_thresh = max(0.15, conf_thresh - 0.05)
                print(f"[+] Confidence threshold decreased to: {conf_thresh:.2f}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[+] Camera released. Clean shutdown complete.")

if __name__ == "__main__":
    main()
