"""
Edge AI Inference Engine - Project Indradhanu
Detects the 4 target species (Bengal Tiger, Asiatic Lion, Indian Leopard, Indian Sloth Bear)
locally on the Raspberry Pi 3 Model B+ edge device, captures a local snapshot to edge/snapshots/,
and generates a unique UUIDv4 event_id for offline persistence and central synchronization.
"""

import os
import sys
import uuid
from pathlib import Path
import cv2
from edge.config import CONFIDENCE_THRESHOLD, SNAPSHOT_DIR

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
            print(
                f"[Edge AI] Active Model: {info['model_name']} ({info['size_mb']} MB, Device: {info['device']}, Conf Thresh: {int(self.conf_thresh * 100)}%)"
            )
        else:
            print("[Edge AI Error] Model weights not loaded. Detections will report negative.")

    def run_inference(self, frame_data, event_id=None):
        """
        Runs local 4-species object detection on a captured camera frame or image file.
        When a target animal (tiger, lion, leopard, bear) is detected above threshold:
        - Generates a unique UUIDv4 event_id
        - Saves the captured snapshot to edge/snapshots/<event_id>.jpg
        - Returns complete detection metadata for local SQLite storage and central upload.
        """
        if not frame_data:
            return {"detected": False, "event_id": None, "species": None, "confidence": 0.0}

        frame_arr = frame_data.get("frame")
        snap_path = frame_data.get("snapshot_path")
        evt_uid = str(event_id).strip() if event_id else str(uuid.uuid4())

        # Case 1: Inference on in-memory BGR camera frame
        if self.is_real_model_loaded and frame_arr is not None:
            detections, _annotated, latency = self.detector.predict_frame(
                frame_arr, conf_thresh=self.conf_thresh, annotate=False
            )
            if detections:
                top = detections[0]
                os.makedirs(SNAPSHOT_DIR, exist_ok=True)
                snap_filename = f"edge_{evt_uid}.jpg"
                save_path = os.path.join(SNAPSHOT_DIR, snap_filename)
                cv2.imwrite(save_path, frame_arr)

                return {
                    "detected": True,
                    "event_id": evt_uid,
                    "species_key": top["species_key"],
                    "species": top["species"],
                    "scientific_name": top["scientific_name"],
                    "threat_level": top["threat_level"],
                    "confidence": top["confidence"],
                    "bounding_box": top["bbox_norm"],
                    "bbox_pixels": top["bbox"],
                    "latency_ms": latency,
                    "snapshot_path": save_path,
                }
            return {
                "detected": False,
                "event_id": None,
                "species": None,
                "confidence": 0.0,
                "latency_ms": latency,
                "snapshot_path": None,
            }

        # Case 2: Inference on saved image path on disk
        if self.is_real_model_loaded and snap_path and os.path.exists(snap_path):
            im = cv2.imread(str(snap_path))
            if im is not None:
                detections, _annotated, latency = self.detector.predict_frame(
                    im, conf_thresh=self.conf_thresh, annotate=False
                )
                if detections:
                    top = detections[0]
                    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
                    snap_filename = f"edge_{evt_uid}.jpg"
                    save_path = os.path.join(SNAPSHOT_DIR, snap_filename)
                    cv2.imwrite(save_path, im)

                    return {
                        "detected": True,
                        "event_id": evt_uid,
                        "species_key": top["species_key"],
                        "species": top["species"],
                        "scientific_name": top["scientific_name"],
                        "threat_level": top["threat_level"],
                        "confidence": top["confidence"],
                        "bounding_box": top["bbox_norm"],
                        "bbox_pixels": top["bbox"],
                        "latency_ms": latency,
                        "snapshot_path": save_path,
                    }
                return {
                    "detected": False,
                    "event_id": None,
                    "species": None,
                    "confidence": 0.0,
                    "latency_ms": latency,
                    "snapshot_path": None,
                }

        return {
            "detected": False,
            "event_id": None,
            "species": None,
            "confidence": 0.0,
            "latency_ms": 0.0,
            "snapshot_path": None,
        }
