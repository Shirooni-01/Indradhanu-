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
        """Initializes OpenCV VideoCapture, auto-detecting the USB camera index if default fails."""
        initial_target = int(self.source) if self.source.isdigit() else self.source
        
        # Build candidate sources list: user configured first, then common Pi indices
        candidates = [initial_target]
        preferred = [1, 0, 2, 3] if sys.platform.startswith("linux") else [0, 1, 2, 3]
        if isinstance(initial_target, int):
            for fallback_idx in preferred:
                if fallback_idx not in candidates:
                    candidates.append(fallback_idx)

        for candidate in candidates:
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY] if sys.platform.startswith("linux") and isinstance(candidate, int) else [cv2.CAP_ANY]
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(candidate, backend) if isinstance(candidate, int) else cv2.VideoCapture(candidate)
                    if cap and cap.isOpened():
                        # Set buffer size to 1 to prevent V4L2 queue overflow on Raspberry Pi
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        # Warm up sensor and flush stale frame
                        ret = False
                        test_frame = None
                        for _ in range(2):
                            ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            self.cap = cap
                            self.source = str(candidate)
                            self.is_connected = True
                            print(f"[Camera] Successfully initialized USB camera (Device: {self.source}).")
                            return
                        cap.release()
                except Exception:
                    pass

        print(f"[Camera Warning] USB camera device {self.source} not currently available.")
        self.is_connected = False

    def capture_frame(self):
        """
        Captures a live frame from the USB camera into memory.
        Does NOT write to disk on every frame - snapshots are only saved upon animal detection!
        """
        if not self.is_connected or not self.cap or not self.cap.isOpened():
            self._init_camera()

        if self.is_connected and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            # If frame read fails or queue hung, attempt flush and reconnect
            if not ret or frame is None:
                for _ in range(2):
                    ret, frame = self.cap.read()
                if not ret or frame is None:
                    print(f"[Camera Warning] Frame grab returned empty frame on device {self.source}. Resetting camera stream...")
                    self.release()
                    self._init_camera()
                    if self.is_connected and self.cap and self.cap.isOpened():
                        ret, frame = self.cap.read()

            if ret and frame is not None:
                return {
                    "frame": frame,
                    "snapshot_path": None,
                    "web_snapshot_path": None
                }

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
