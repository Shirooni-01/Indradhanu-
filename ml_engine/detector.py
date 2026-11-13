"""
Project Indradhanu - Edge AI Detection Engine (4-Species Wildlife Detector)
Optimized for Raspberry Pi 3 Model B+ (ARM Cortex-A53, 1 GB RAM, Raspberry Pi OS Lite).

Detects all 4 PRD-mandated target animals locally:
1. Bengal Tiger (Panthera tigris tigris)     -> key: 'tiger'
2. Asiatic Lion (Panthera leo persica)       -> key: 'lion'
3. Indian Leopard (Panthera pardus fusca)    -> key: 'leopard'
4. Indian Sloth Bear (Melursus ursinus)      -> key: 'bear'

Architecture:
- Stage 1: YOLOv8n (indradhanu_best.pt, imgsz=320 on Pi) for fast spatial bounding-box localization
- Stage 2: MobileNetV3-Small (edge_mobilenet_v3_small.pth, offline local weights) for 4-species classification
  and bear/lion recall recovery.
"""

import os
import sys
import time
import uuid
from pathlib import Path

os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")
import numpy as np

try:
    import torch
    import torchvision.transforms as T
    from torchvision.models import mobilenet_v3_small
    # Constrain CPU threads to 2 for Raspberry Pi 3 Model B+ thermal & memory stability
    if not torch.cuda.is_available():
        torch.set_num_threads(int(os.environ.get("EDGE_TORCH_THREADS", "2")))
except Exception:
    torch = None

import cv2
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Canonical 4-species taxonomy required by the Indradhanu PRD
TARGET_SPECIES_INFO = {
    "tiger": {
        "species_key": "tiger",
        "common_name": "Bengal Tiger",
        "scientific_name": "Panthera tigris tigris",
        "threat_level": "CRITICAL",
        "color_bgr": (0, 140, 255),   # Orange
        "badge_color": "#f97316",
        "imagenet_indices": [292, 282],  # tiger (292), tiger cat (282)
    },
    "lion": {
        "species_key": "lion",
        "common_name": "Asiatic Lion",
        "scientific_name": "Panthera leo persica",
        "threat_level": "CRITICAL",
        "color_bgr": (0, 180, 255),   # Golden Amber
        "badge_color": "#f59e0b",
        "imagenet_indices": [291],       # lion (291)
    },
    "leopard": {
        "species_key": "leopard",
        "common_name": "Indian Leopard",
        "scientific_name": "Panthera pardus fusca",
        "threat_level": "CRITICAL",
        "color_bgr": (0, 215, 255),   # Yellow
        "badge_color": "#eab308",
        "imagenet_indices": [288, 289, 290],  # leopard (288), snow leopard (289), jaguar (290)
    },
    "bear": {
        "species_key": "bear",
        "common_name": "Indian Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "threat_level": "CRITICAL",
        "color_bgr": (40, 110, 235),  # Rust / Brown-Orange
        "badge_color": "#ea580c",
        "imagenet_indices": [297, 294, 295],  # sloth bear (297), brown bear (294), American black bear (295)
    },
}

YOLO_CLASS_TO_KEY = {
    0: "tiger",
    1: "leopard",
}


def normalize_species_key(species_name):
    """Maps any species label ('Bengal Tiger', 'tiger', 'Asiatic Lion', etc.) to canonical key."""
    if not species_name:
        return None
    s = str(species_name).strip().lower()
    if "tiger" in s:
        return "tiger"
    if "lion" in s:
        return "lion"
    if "leopard" in s or "panther" in s:
        return "leopard"
    if "bear" in s:
        return "bear"
    return None


class IndradhanuDetector:
    _instance = None

    @classmethod
    def get_instance(cls):
        """Singleton instance for memory efficiency on constrained devices."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, weights_path=None):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.weights_dir = self.root_dir / "ml_engine" / "weights"

        default_pt = self.weights_dir / "indradhanu_best.pt"
        default_onnx = self.weights_dir / "indradhanu_best.onnx"
        self.mobilenet_path = self.weights_dir / "edge_mobilenet_v3_small.pth"

        if weights_path:
            self.model_path = Path(weights_path)
        elif default_pt.exists():
            self.model_path = default_pt
        elif default_onnx.exists():
            self.model_path = default_onnx
        else:
            self.model_path = None

        self.yolo_model = None
        self.classifier = None
        self.transform = None
        self.is_loaded = False
        self.device = "cpu"
        self.default_imgsz = int(os.environ.get("EDGE_IMGSZ", "320"))
        self._load_models()

    def _load_models(self):
        """Loads YOLOv8n detector and MobileNetV3-Small 4-species classifier from local weights."""
        if torch is None:
            print("[Edge AI Warning] PyTorch is not available.")
            return

        try:
            from ultralytics import YOLO

            self.device = "cpu"
            if self.model_path and self.model_path.exists():
                self.yolo_model = YOLO(str(self.model_path))

            if self.mobilenet_path.exists():
                self.classifier = mobilenet_v3_small(weights=None)
                state_dict = torch.load(str(self.mobilenet_path), map_location="cpu", weights_only=True)
                self.classifier.load_state_dict(state_dict)
                self.classifier.eval()
                self.transform = T.Compose([
                    T.Resize((224, 224)),
                    T.ToTensor(),
                    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ])

            self.is_loaded = (self.yolo_model is not None) or (self.classifier is not None)
            if self.is_loaded:
                print(
                    f"[Edge AI Engine] Loaded 4-species detector (YOLOv8n + MobileNetV3-Small, imgsz={self.default_imgsz}, threads={torch.get_num_threads()})"
                )
        except Exception as e:
            print(f"[Edge AI Error] Failed to load edge models: {e}")
            self.is_loaded = False

    def get_info(self):
        """Returns metadata about the active Edge AI model."""
        if not self.is_loaded:
            return {
                "status": "NOT_LOADED",
                "model_name": "None",
                "size_mb": 0,
                "device": self.device,
                "supported_species": [m["common_name"] for m in TARGET_SPECIES_INFO.values()],
            }

        total_bytes = 0
        if self.model_path and self.model_path.exists():
            total_bytes += self.model_path.stat().st_size
        if self.mobilenet_path and self.mobilenet_path.exists():
            total_bytes += self.mobilenet_path.stat().st_size

        return {
            "status": "ONLINE_ACTIVE",
            "model_name": "YOLOv8n + MobileNetV3-Small (Pi 3B+ Edge Suite)",
            "architecture": "Two-Stage Edge Detector (tiger, lion, leopard, bear)",
            "size_mb": round(total_bytes / (1024 ** 2), 2),
            "device": self.device,
            "imgsz": self.default_imgsz,
            "supported_species": [m["common_name"] for m in TARGET_SPECIES_INFO.values()],
            "classes": {
                0: "Bengal Tiger",
                1: "Indian Leopard",
                2: "Asiatic Lion",
                3: "Indian Sloth Bear",
            },
        }

    def _classify_crop_bgr(self, crop_bgr):
        """
        Runs MobileNetV3-Small on a BGR image/crop.
        Returns (species_key, confidence_0_to_1) or (None, 0.0) if not a target animal.
        """
        if self.classifier is None or crop_bgr is None or crop_bgr.size == 0:
            return None, 0.0

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        tensor = self.transform(pil_img).unsqueeze(0)

        with torch.inference_mode():
            logits = self.classifier(tensor)[0]
            probs = torch.softmax(logits, dim=0)

        species_scores = {}
        for key, meta in TARGET_SPECIES_INFO.items():
            score = sum(float(probs[idx]) for idx in meta["imagenet_indices"])
            species_scores[key] = score

        best_key = max(species_scores, key=species_scores.get)
        best_score = species_scores[best_key]

        # Check top-1 overall ImageNet class to avoid false triggers on unrelated everyday objects
        top1_prob, top1_idx = torch.max(probs, dim=0)
        all_target_indices = {idx for m in TARGET_SPECIES_INFO.values() for idx in m["imagenet_indices"]}

        if int(top1_idx) in all_target_indices or best_score >= 0.35:
            # Calibrate multi-index target probability into [0, 1] confidence
            calibrated_conf = min(0.995, best_score * 1.12 if best_score >= 0.5 else best_score)
            return best_key, float(calibrated_conf)

        return None, float(best_score)

    def _estimate_saliency_bbox(self, frame_bgr):
        """Computes a central foreground bounding box when classification triggers without a YOLO box (e.g. bear)."""
        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 140)
        ys, xs = np.where(edges > 0)
        if len(xs) > 50 and len(ys) > 50:
            x1 = int(max(int(w * 0.08), np.percentile(xs, 8)))
            y1 = int(max(int(h * 0.08), np.percentile(ys, 8)))
            x2 = int(min(int(w * 0.92), np.percentile(xs, 92)))
            y2 = int(min(int(h * 0.92), np.percentile(ys, 92)))
            if (x2 - x1) > int(w * 0.2) and (y2 - y1) > int(h * 0.2):
                return [x1, y1, x2, y2]
        return [int(w * 0.12), int(h * 0.12), int(w * 0.88), int(h * 0.88)]

    def _check_lens_obstruction(self, frame_bgr, x1, y1, x2, y2):
        h, w = frame_bgr.shape[:2]
        bw = max(0, x2 - x1)
        bh = max(0, y2 - y1)
        area_ratio = (bw * bh) / (w * h) if (w * h) > 0 else 0.0
        if area_ratio > 0.82:
            roi = frame_bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if roi.size > 0:
                gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray_roi, 50, 150)
                edge_density = np.count_nonzero(edges) / edges.size
                if edge_density < 0.030 or area_ratio > 0.95:
                    return True
        return False

    def _annotate_detection(self, annotated, x1, y1, x2, y2, species_meta, conf_0_to_1):
        color = species_meta["color_bgr"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        corner_len = max(8, min(22, (x2 - x1) // 4, (y2 - y1) // 4))
        th = 3
        cv2.line(annotated, (x1, y1), (x1 + corner_len, y1), color, th)
        cv2.line(annotated, (x1, y1), (x1, y1 + corner_len), color, th)
        cv2.line(annotated, (x2, y1), (x2 - corner_len, y1), color, th)
        cv2.line(annotated, (x2, y1), (x2, y1 + corner_len), color, th)
        cv2.line(annotated, (x1, y2), (x1 + corner_len, y2), color, th)
        cv2.line(annotated, (x1, y2), (x1, y2 - corner_len), color, th)
        cv2.line(annotated, (x2, y2), (x2 - corner_len, y2), color, th)
        cv2.line(annotated, (x2, y2), (x2, y2 - corner_len), color, th)

        label = f"EDGE: {species_meta['common_name'].upper()} {conf_0_to_1:.1%}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        badge_y = max(26, y1 - lh - 8)
        cv2.rectangle(annotated, (x1, badge_y), (x1 + lw + 10, badge_y + lh + 6), color, -1)
        cv2.putText(
            annotated,
            label,
            (x1 + 5, badge_y + lh + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

    def predict_frame(self, frame_bgr, conf_thresh=0.45, imgsz=None, annotate=True):
        """
        Runs 4-species detection on a BGR OpenCV frame.
        Returns: (detections_list, annotated_frame, latency_ms)
        """
        if not self.is_loaded or frame_bgr is None or frame_bgr.size == 0:
            return [], frame_bgr, 0.0

        use_imgsz = imgsz or self.default_imgsz
        start_t = time.time()
        h, w = frame_bgr.shape[:2]
        annotated = frame_bgr.copy() if annotate else frame_bgr
        detections = []

        yolo_boxes = []
        if self.yolo_model is not None:
            results = self.yolo_model.predict(
                frame_bgr,
                conf=max(0.25, conf_thresh - 0.15),
                imgsz=use_imgsz,
                device=self.device,
                verbose=False,
            )
            if results and len(results[0].boxes) > 0:
                yolo_boxes = results[0].boxes

        for box in yolo_boxes:
            cls_id = int(box.cls[0])
            yolo_conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

            if self._check_lens_obstruction(frame_bgr, x1, y1, x2, y2):
                continue

            yolo_key = YOLO_CLASS_TO_KEY.get(cls_id, "tiger")
            pad_x = int((x2 - x1) * 0.10)
            pad_y = int((y2 - y1) * 0.10)
            crop = frame_bgr[max(0, y1 - pad_y):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]

            mn_key, mn_conf = self._classify_crop_bgr(crop)
            if mn_key is None:
                mn_key, mn_conf = self._classify_crop_bgr(frame_bgr)

            if mn_key is not None and mn_conf >= 0.40:
                # MobileNetV3 refines species across all 4 targets (especially distinguishing lion/bear from leopard/tiger)
                final_key = mn_key
                final_conf = max(yolo_conf, mn_conf) if mn_key == yolo_key else mn_conf
            elif yolo_conf >= conf_thresh and self.classifier is None:
                final_key = yolo_key
                final_conf = yolo_conf
            elif yolo_conf >= max(0.75, conf_thresh):
                final_key = yolo_key
                final_conf = yolo_conf
            else:
                continue

            if final_conf < conf_thresh:
                continue

            meta = TARGET_SPECIES_INFO[final_key]
            det_obj = {
                "species_key": final_key,
                "species": meta["common_name"],
                "scientific_name": meta["scientific_name"],
                "confidence": round(final_conf * 100.0, 1),
                "threat_level": meta["threat_level"],
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "bbox_norm": [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)],
            }
            detections.append(det_obj)
            if annotate:
                self._annotate_detection(annotated, x1, y1, x2, y2, meta, final_conf)

        # Fallback to full-frame MobileNetV3-Small when YOLOv8n produces no box (e.g. Sloth Bear / Asiatic Lion)
        if not detections and self.classifier is not None:
            mn_key, mn_conf = self._classify_crop_bgr(frame_bgr)
            if mn_key is not None and mn_conf >= conf_thresh:
                x1, y1, x2, y2 = self._estimate_saliency_bbox(frame_bgr)
                if not self._check_lens_obstruction(frame_bgr, x1, y1, x2, y2):
                    meta = TARGET_SPECIES_INFO[mn_key]
                    det_obj = {
                        "species_key": mn_key,
                        "species": meta["common_name"],
                        "scientific_name": meta["scientific_name"],
                        "confidence": round(mn_conf * 100.0, 1),
                        "threat_level": meta["threat_level"],
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "bbox_norm": [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)],
                    }
                    detections.append(det_obj)
                    if annotate:
                        self._annotate_detection(annotated, x1, y1, x2, y2, meta, mn_conf)

        latency_ms = round((time.time() - start_t) * 1000.0, 1)
        return detections, annotated, latency_ms

    def predict_image_file(self, image_path, conf_thresh=0.45, save_to_snapshots=False, snapshot_dir=None, event_id=None):
        """
        Runs 4-species detection on an image file from disk.
        Optionally saves snapshot for edge upload buffering.
        """
        im = cv2.imread(str(image_path))
        if im is None:
            return [], None, 0.0, None

        detections, annotated, latency = self.predict_frame(im, conf_thresh=conf_thresh, annotate=True)

        saved_path = None
        if save_to_snapshots and detections:
            target_dir = Path(snapshot_dir) if snapshot_dir else (self.root_dir / "edge" / "snapshots")
            target_dir.mkdir(parents=True, exist_ok=True)
            evt_uid = event_id or str(uuid.uuid4())
            snap_filename = f"edge_{evt_uid}.jpg"
            full_save_path = target_dir / snap_filename
            cv2.imwrite(str(full_save_path), im)
            saved_path = str(full_save_path)

        return detections, annotated, latency, saved_path
