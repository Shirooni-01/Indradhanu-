"""
USB Camera Driver for Edge Station - Project Indradhanu
Hardware: Standard USB Webcam on Raspberry Pi 3 B+ (/dev/video0) or Central PC.
Captures live frames via OpenCV for real AI inference. Zero simulation fallbacks.
"""

import os
import sys
import time
from pathlib import Path
import cv2
from edge.config import CAMERA_SOURCE, SNAPSHOTS_DIR

class USBCamera:
    """Production USB Webcam capture driver for Raspberry Pi and PC."""
    def __init__(self, source=CAMERA_SOURCE):
        self.source = str(source).strip()
        self.cap = None
        self.is_connected = False
        self._init_camera()

    def _init_camera(self):
        """Initializes OpenCV VideoCapture for the configured camera source."""
        cam_idx = int(self.source) if self.source.isdigit() else self.source
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") and isinstance(cam_idx, int) else cv2.CAP_ANY

        try:
            self.cap = cv2.VideoCapture(cam_idx, backend)
            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ret, test_frame = self.cap.read()
                if ret and test_frame is not None:
                    self.is_connected = True
                    print(f"[Camera] Successfully initialized USB camera (Device: {self.source}).")
                    return
        except Exception as e:
            print(f"[Camera Error] Failed to initialize camera device {self.source}: {e}")

        print(f"[Camera Warning] USB camera device {self.source} not currently available.")
        self.is_connected = False

    def capture_frame(self):
        """
        Captures a live frame from the USB camera.
        Returns dict containing 'frame' (numpy array) and 'snapshot_path', or None on capture failure.
        """
        if not self.is_connected or not self.cap or not self.cap.isOpened():
            # Attempt to re-initialize once
            self._init_camera()

        if self.is_connected and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
                snap_filename = f"capture_{int(time.time())}.jpg"
                full_path = os.path.join(SNAPSHOTS_DIR, snap_filename)
                cv2.imwrite(full_path, frame)

                return {
                    "frame": frame,
                    "snapshot_path": full_path,
                    "web_snapshot_path": f"/static/snapshots/{snap_filename}"
                }
            else:
                print("[Camera Warning] Frame grab returned empty frame.")

        return {
            "frame": None,
            "snapshot_path": None,
            "web_snapshot_path": None
        }

    def release(self):
        """Safely releases the camera device handle."""
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            self.is_connected = False

# Backward-compatibility alias for edge daemon
ThermalCamera = USBCamera
