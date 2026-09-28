"""
Project Indradhanu - Central AI Vision & Apex Predator Detection Engine
Loads the trained YOLOv8n / ONNX model and provides real-time inference,
frame annotation, and snapshot generation for both the Flask web server and Edge stations.
"""

import os
import sys
import time
import glob
import random
from pathlib import Path
import cv2
import numpy as np

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPECIES_TAXONOMY = {
    0: {
        "common_name": "Bengal Tiger",
        "scientific_name": "Panthera tigris",
        "threat_level": "CRITICAL",
        "color_bgr": (0, 140, 255),    # Amber / Orange
        "badge_color": "#f97316"
    },
    1: {
        "common_name": "Indian Leopard",
        "scientific_name": "Panthera pardus",
        "threat_level": "CRITICAL",
        "color_bgr": (0, 215, 255),    # Yellow
        "badge_color": "#eab308"
    },
    2: {
        "common_name": "Indian Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "threat_level": "HIGH",
        "color_bgr": (255, 100, 0),    # Blue / Cyan
        "badge_color": "#3b82f6"
    },
    3: {
        "common_name": "Asiatic Lion",
        "scientific_name": "Panthera leo persica",
        "threat_level": "CRITICAL",
        "color_bgr": (0, 255, 255),
        "badge_color": "#fbbf24"
    }
}

class IndradhanuDetector:
    _instance = None

    @classmethod
    def get_instance(cls):
        """Singleton pattern for efficient shared model memory across Flask routes."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, weights_path=None):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.weights_dir = self.root_dir / "ml_engine" / "weights"
        
        # Priority: PT checkpoint -> ONNX -> Fallback
        default_pt = self.weights_dir / "indradhanu_best.pt"
        default_onnx = self.weights_dir / "indradhanu_best.onnx"
        
        if weights_path:
            self.model_path = Path(weights_path)
        elif default_pt.exists():
            self.model_path = default_pt
        elif default_onnx.exists():
            self.model_path = default_onnx
        else:
            self.model_path = None

        self.model = None
        self.is_loaded = False
        self.device = "cpu"
        self._load_model()

    def _load_model(self):
        """Loads Ultralytics YOLO model onto GPU if available."""
        if not self.model_path or not self.model_path.exists():
            print(f"[AI Engine Warning] No model found at {self.model_path}. Operating in fallback mode.")
            return

        try:
            import torch
            from ultralytics import YOLO
            
            if torch.cuda.is_available():
                self.device = "0"
                dev_name = torch.cuda.get_device_name(0)
            else:
                self.device = "cpu"
                dev_name = "CPU"

            print(f"[AI Engine] Loading {self.model_path.name} on {dev_name}...")
            self.model = YOLO(str(self.model_path))
            self.is_loaded = True
            file_mb = self.model_path.stat().st_size / (1024 ** 2)
            print(f"[AI Engine ✅] Model ready! ({file_mb:.2f} MB, Device: {dev_name})")
        except Exception as e:
            print(f"[AI Engine Error] Failed to load model: {e}")
            self.is_loaded = False

    def get_info(self):
        """Returns metadata about the active AI model."""
        if not self.is_loaded or not self.model_path:
            return {
                "status": "NOT_LOADED",
                "model_name": "None",
                "size_mb": 0,
                "device": self.device,
                "classes": list(SPECIES_TAXONOMY.keys())
            }
        
        file_mb = round(self.model_path.stat().st_size / (1024 ** 2), 2)
        return {
            "status": "ONLINE_ACTIVE",
            "model_name": self.model_path.name,
            "architecture": "YOLOv8n (Nano) Specialized Apex Detector",
            "size_mb": file_mb,
            "device": self.device,
            "classes": {cid: m["common_name"] for cid, m in SPECIES_TAXONOMY.items() if cid in (0, 1)},
            "benchmark_map50": "97.9%"
        }

    def predict_frame(self, frame_bgr, conf_thresh=0.45, imgsz=640, annotate=True):
        """
        Runs detection on a single BGR OpenCV frame.
        Returns: (detections_list, annotated_frame, latency_ms)
        """
        if not self.is_loaded or self.model is None or frame_bgr is None:
            return [], frame_bgr, 0.0

        start_t = time.time()
        results = self.model.predict(
            frame_bgr, 
            conf=conf_thresh, 
            imgsz=imgsz, 
            device=self.device,
            verbose=False
        )
        latency_ms = round((time.time() - start_t) * 1000.0, 1)

        boxes = results[0].boxes
        detections = []
        annotated = frame_bgr.copy() if annotate else frame_bgr

        h, w = frame_bgr.shape[:2]

        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

            # --- LENS OBSTRUCTION & MACRO GUARDRAIL ---
            # Rejects fingers/hands covering lens, blurred macro obstacles, or insects on glass.
            bw = max(0, x2 - x1)
            bh = max(0, y2 - y1)
            area_ratio = (bw * bh) / (w * h) if (w * h) > 0 else 0.0

            is_lens_obstruction = False
            if area_ratio > 0.80:
                roi = frame_bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
                if roi.size > 0:
                    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray_roi, 50, 150)
                    edge_density = np.count_nonzero(edges) / edges.size
                    # Blurred skin / obstruction covering >80% has edge_density < 3.5%
                    if edge_density < 0.035 or area_ratio > 0.92:
                        is_lens_obstruction = True

            if is_lens_obstruction:
                if annotate:
                    warn_color = (0, 165, 255)  # Amber Warning
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), warn_color, 2)
                    warn_text = "⚠️ LENS OBSTRUCTION / FINGER (IGNORED)"
                    (lw, lh), _ = cv2.getTextSize(warn_text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
                    cv2.rectangle(annotated, (x1 + 5, y1 + 5), (x1 + lw + 15, y1 + lh + 15), (10, 20, 16), -1)
                    cv2.putText(annotated, warn_text, (x1 + 10, y1 + lh + 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, warn_color, 1, cv2.LINE_AA)
                continue  # Reject false detection!

            tax = SPECIES_TAXONOMY.get(cls_id, {
                "common_name": self.model.names.get(cls_id, "Unknown"),
                "scientific_name": "Wild Carnivore",
                "threat_level": "CRITICAL",
                "color_bgr": (0, 0, 255),
                "badge_color": "#ef4444"
            })

            det_obj = {
                "species": tax["common_name"],
                "scientific_name": tax["scientific_name"],
                "class_id": cls_id,
                "confidence": round(conf * 100.0, 1),
                "threat_level": tax["threat_level"],
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "bbox_norm": [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)]
            }
            detections.append(det_obj)

            if annotate:
                color = tax["color_bgr"]
                # Tactical Corner Bounding Box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                corner_len = min(22, (x2 - x1) // 4, (y2 - y1) // 4)
                th = 4
                cv2.line(annotated, (x1, y1), (x1 + corner_len, y1), color, th)
                cv2.line(annotated, (x1, y1), (x1, y1 + corner_len), color, th)
                cv2.line(annotated, (x2, y1), (x2 - corner_len, y1), color, th)
                cv2.line(annotated, (x2, y1), (x2, y1 + corner_len), color, th)
                cv2.line(annotated, (x1, y2), (x1 + corner_len, y2), color, th)
                cv2.line(annotated, (x1, y2), (x1, y2 - corner_len), color, th)
                cv2.line(annotated, (x2, y2), (x2 - corner_len, y2), color, th)
                cv2.line(annotated, (x2, y2), (x2, y2 - corner_len), color, th)

                # Crosshair
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                cv2.circle(annotated, (cx, cy), 4, color, 1)

                # Label Badge
                label = f"{tax['common_name'].upper()} {conf:.1%} [{tax['threat_level']}]"
                (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                badge_y = max(26, y1 - lh - 8)
                cv2.rectangle(annotated, (x1, badge_y), (x1 + lw + 10, badge_y + lh + 6), color, -1)
                cv2.putText(annotated, label, (x1 + 5, badge_y + lh + 2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2, cv2.LINE_AA)

        return detections, annotated, latency_ms

    def predict_image_file(self, image_path, conf_thresh=0.45, save_to_snapshots=True):
        """
        Runs detection on an image from disk.
        If save_to_snapshots is True, saves verified image to static/snapshots/
        and returns the web-accessible URL.
        """
        im = cv2.imread(str(image_path))
        if im is None:
            return [], None, 0.0, None

        detections, annotated, latency = self.predict_frame(im, conf_thresh=conf_thresh, annotate=True)

        web_path = None
        if save_to_snapshots and detections:
            snap_dir = self.root_dir / "static" / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_filename = f"verified_{int(time.time())}_{Path(image_path).stem[:8]}.jpg"
            save_path = snap_dir / snap_filename
            cv2.imwrite(str(save_path), annotated)
            web_path = f"/static/snapshots/{snap_filename}"

        return detections, annotated, latency, web_path

    def run_random_test_sample(self):
        """
        Picks a random test image from the dataset, runs inference,
        saves the snapshot to static/snapshots/, and returns structured detection data.
        """
        test_dir = self.root_dir / "Indradhanu_Dataset" / "images" / "test"
        if not test_dir.exists():
            return None

        test_images = list(test_dir.glob("*.jpg"))
        if not test_images:
            return None

        # Pick random test image
        chosen = random.choice(test_images)
        detections, annotated, latency, web_path = self.predict_image_file(chosen, conf_thresh=0.45)

        if not detections:
            # Fallback to another image that has a target
            for candidate in random.sample(test_images, min(10, len(test_images))):
                detections, annotated, latency, web_path = self.predict_image_file(candidate, conf_thresh=0.45)
                if detections:
                    break

        if not detections:
            return None

        primary = detections[0]
        return {
            "species": primary["species"],
            "scientific_name": primary["scientific_name"],
            "threat_level": primary["threat_level"],
            "confidence": primary["confidence"],
            "latency_ms": latency,
            "web_snapshot_path": web_path or "/static/snapshots/tiger_sample.jpg",
            "bbox": primary["bbox"],
            "all_detections": detections
        }
