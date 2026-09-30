"""
Edge AI Inference Engine - Project Indradhanu (Project C)
Detects target species (Bengal Tiger & Indian Leopard) on edge CPU.
Zero fake/random detection generation. If no target predator is detected, returns detected = False.
"""

import os
import sys
import time
from pathlib import Path
from edge.config import CONFIDENCE_THRESHOLD

try:
    from ml_engine.detector import IndradhanuDetector
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from ml_engine.detector import IndradhanuDetector

class WildlifeDetector:
    def __init__(self, model_path=None, conf_thresh=CONFIDENCE_THRESHOLD):
        self.conf_thresh = float(conf_thresh)
        self.detector = IndradhanuDetector.get_instance()
        self.is_real_model_loaded = self.detector.is_loaded
        if self.is_real_model_loaded:
            info = self.detector.get_info()
            print(f"[Edge AI] Active Model: {info['model_name']} ({info['size_mb']} MB, Device: {info['device']}, Conf Thresh: {int(self.conf_thresh * 100)}%)")
        else:
            print("[Edge AI Error] Model weights not loaded. Detections will report negative.")

    def run_inference(self, frame_data):
        """
        Runs object detection on the captured camera frame.
        frame_data: dict containing 'frame' (numpy array) or 'snapshot_path'.
        Returns detection result dict if target animal detected above threshold, else detected=False.
        """
        if not frame_data:
            return {"detected": False, "species": None, "confidence": 0.0}

        frame_arr = frame_data.get("frame")
        snap_path = frame_data.get("snapshot_path")

        # 1. Inference on raw memory frame
        if self.is_real_model_loaded and frame_arr is not None:
            detections, annotated, latency = self.detector.predict_frame(
                frame_arr, conf_thresh=self.conf_thresh, annotate=True
            )
            if detections:
                top = detections[0]
                snap_dir = Path(__file__).resolve().parent.parent.parent / "static" / "snapshots"
                snap_dir.mkdir(parents=True, exist_ok=True)
                snap_filename = f"edge_live_{int(time.time())}_{top['species'].lower().replace(' ', '_')}.jpg"
                save_path = str(snap_dir / snap_filename)
                import cv2
                cv2.imwrite(save_path, annotated)
                web_path = f"/static/snapshots/{snap_filename}"

                return {
                    "detected": True,
                    "species": top["species"],
                    "scientific_name": top["scientific_name"],
                    "threat_level": top["threat_level"],
                    "confidence": top["confidence"],
                    "bounding_box": top["bbox_norm"],
                    "latency_ms": latency,
                    "snapshot_path": save_path,
                    "web_snapshot_path": web_path
                }
            else:
                return {
                    "detected": False,
                    "species": None,
                    "confidence": 0.0,
                    "latency_ms": latency,
                    "snapshot_path": None,
                    "web_snapshot_path": None
                }

        # 2. Inference on saved image path
        if self.is_real_model_loaded and snap_path and os.path.exists(snap_path):
            detections, annotated, latency, web_path = self.detector.predict_image_file(
                snap_path, conf_thresh=self.conf_thresh, save_to_snapshots=True
            )
            if detections:
                top = detections[0]
                return {
                    "detected": True,
                    "species": top["species"],
                    "scientific_name": top["scientific_name"],
                    "threat_level": top["threat_level"],
                    "confidence": top["confidence"],
                    "bounding_box": top["bbox_norm"],
                    "latency_ms": latency,
                    "snapshot_path": snap_path,
                    "web_snapshot_path": web_path or frame_data.get("web_snapshot_path")
                }
            else:
                return {
                    "detected": False,
                    "species": None,
                    "confidence": 0.0,
                    "latency_ms": latency,
                    "snapshot_path": snap_path,
                    "web_snapshot_path": None
                }

        # No fake fallback: clean false result
        return {
            "detected": False,
            "species": None,
            "confidence": 0.0,
            "latency_ms": 0.0,
            "snapshot_path": None,
            "web_snapshot_path": None
        }
