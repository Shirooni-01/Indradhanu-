"""
Project Indradhanu - Central AI Snapshot Verification Engine
Runs EXCLUSIVELY on the Central Server to verify snapshots uploaded by registered forest edge devices.
Never accesses any local webcam, IP camera, or dashboard camera stream.

Architecture:
- Primary Verification Backbone: EfficientNet-B0 (central_efficientnet_b0.pth, 21.4 MB)
- Spatial Localization Verifier: YOLOv8 High-Res (indradhanu_best.pt, imgsz=640)
- Supports all 4 target species:
  1. Bengal Tiger (Panthera tigris tigris)
  2. Asiatic Lion (Panthera leo persica)
  3. Indian Leopard (Panthera pardus fusca)
  4. Indian Sloth Bear (Melursus ursinus)
"""

import os
import time
from pathlib import Path
import numpy as np
import cv2
from PIL import Image

try:
    import torch
    import torchvision.transforms as T
    from torchvision.models import efficientnet_b0
except Exception:
    torch = None

from ml_engine.detector import TARGET_SPECIES_INFO, normalize_species_key


class CentralVerificationEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.weights_dir = self.root_dir / "ml_engine" / "weights"
        self.efficientnet_path = self.weights_dir / "central_efficientnet_b0.pth"
        self.yolo_path = self.weights_dir / "indradhanu_best.pt"

        self.verifier_model = None
        self.yolo_verifier = None
        self.transform = None
        self.device = "cpu"
        self.is_loaded = False
        self._load_models()

    def _load_models(self):
        if torch is None:
            print("[Central Verifier Warning] PyTorch not installed.")
            return

        try:
            if torch.cuda.is_available():
                self.device = "cuda:0"
            else:
                self.device = "cpu"

            if self.efficientnet_path.exists():
                self.verifier_model = efficientnet_b0(weights=None)
                state_dict = torch.load(str(self.efficientnet_path), map_location="cpu", weights_only=True)
                self.verifier_model.load_state_dict(state_dict)
                self.verifier_model.to(self.device)
                self.verifier_model.eval()
                self.transform = T.Compose([
                    T.Resize((256, 256)),
                    T.CenterCrop((224, 224)),
                    T.ToTensor(),
                    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ])

            if self.yolo_path.exists():
                from ultralytics import YOLO
                self.yolo_verifier = YOLO(str(self.yolo_path))

            self.is_loaded = self.verifier_model is not None
            if self.is_loaded:
                size_mb = round(self.efficientnet_path.stat().st_size / (1024 ** 2), 2)
                print(f"[Central Verifier] Loaded EfficientNet-B0 Verification Engine ({size_mb} MB on {self.device})")
        except Exception as e:
            print(f"[Central Verifier Error] Failed loading verification model: {e}")
            self.is_loaded = False

    def get_info(self):
        if not self.is_loaded:
            return {
                "status": "NOT_LOADED",
                "model_name": "None",
                "architecture": "EfficientNet-B0 Central Verifier",
                "size_mb": 0,
                "device": self.device,
            }
        size_mb = round(self.efficientnet_path.stat().st_size / (1024 ** 2), 2)
        return {
            "status": "ONLINE_ACTIVE",
            "model_name": self.efficientnet_path.name,
            "architecture": "EfficientNet-B0 + YOLOv8 High-Res Spatial Verifier",
            "size_mb": size_mb,
            "device": self.device,
            "supported_species": [m["common_name"] for m in TARGET_SPECIES_INFO.values()],
        }

    def _run_efficientnet(self, img_bgr):
        """Evaluates a BGR image or crop with EfficientNet-B0 and returns species score dict and top-1 info."""
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

        with torch.inference_mode():
            logits = self.verifier_model(tensor)[0]
            probs = torch.softmax(logits, dim=0).cpu()

        species_scores = {}
        for key, meta in TARGET_SPECIES_INFO.items():
            species_scores[key] = sum(float(probs[idx]) for idx in meta["imagenet_indices"])

        top1_prob, top1_idx = torch.max(probs, dim=0)
        return species_scores, int(top1_idx), float(top1_prob)

    def verify_edge_snapshot(
        self,
        image_path,
        edge_species=None,
        edge_confidence=None,
        event_id=None,
        verify_threshold=60.0,
        save_annotated=True,
    ):
        """
        Verifies a snapshot uploaded by an edge device.
        Never uses a local camera; only processes the snapshot file from the edge upload.
        """
        start_t = time.time()
        edge_key = normalize_species_key(edge_species)

        if not image_path or not os.path.exists(str(image_path)):
            return {
                "is_verified": False,
                "verification_status": "UNVERIFIED_NO_SNAPSHOT",
                "verified_species": None,
                "verified_species_key": None,
                "scientific_name": None,
                "verified_confidence": 0.0,
                "species_agreement": False,
                "verification_model": "EfficientNet-B0 + YOLOv8-Verifier",
                "verification_notes": "Edge event received without a valid snapshot file.",
                "web_snapshot_path": None,
                "latency_ms": 0.0,
            }

        frame_bgr = cv2.imread(str(image_path))
        if frame_bgr is None or frame_bgr.size == 0:
            return {
                "is_verified": False,
                "verification_status": "REJECTED_INVALID_IMAGE",
                "verified_species": None,
                "verified_species_key": None,
                "scientific_name": None,
                "verified_confidence": 0.0,
                "species_agreement": False,
                "verification_model": "EfficientNet-B0 + YOLOv8-Verifier",
                "verification_notes": "Uploaded snapshot could not be decoded as a valid image.",
                "web_snapshot_path": None,
                "latency_ms": 0.0,
            }

        h, w = frame_bgr.shape[:2]
        bbox = None
        yolo_conf = 0.0
        yolo_key = None

        # Step 1: High-res spatial localization check via YOLOv8 (imgsz=640)
        if self.yolo_verifier is not None:
            results = self.yolo_verifier.predict(frame_bgr, conf=0.25, imgsz=640, verbose=False)
            if results and len(results[0].boxes) > 0:
                top_box = results[0].boxes[0]
                cls_id = int(top_box.cls[0])
                yolo_conf = float(top_box.conf[0])
                yolo_key = "tiger" if cls_id == 0 else "leopard"
                x1, y1, x2, y2 = top_box.xyxy[0].cpu().numpy().astype(int)
                bbox = [int(x1), int(y1), int(x2), int(y2)]

        # Step 2: EfficientNet-B0 verification on full frame and ROI crop (if available)
        full_scores, top1_idx, _top1_prob = self._run_efficientnet(frame_bgr)
        combined_scores = dict(full_scores)

        if bbox is not None:
            x1, y1, x2, y2 = bbox
            pad_x = int((x2 - x1) * 0.12)
            pad_y = int((y2 - y1) * 0.12)
            crop = frame_bgr[max(0, y1 - pad_y):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]
            if crop.size > 0:
                crop_scores, crop_top1_idx, _ = self._run_efficientnet(crop)
                for k in combined_scores:
                    combined_scores[k] = max(full_scores[k], crop_scores[k])
                top1_idx = crop_top1_idx

        best_key = max(combined_scores, key=combined_scores.get)
        raw_prob = combined_scores[best_key]
        all_target_indices = {idx for m in TARGET_SPECIES_INFO.values() for idx in m["imagenet_indices"]}
        is_top1_target = top1_idx in all_target_indices

        # Fuse EfficientNet-B0 verification score with YOLOv8 spatial confidence when they agree
        if is_top1_target or raw_prob >= 0.30:
            calibrated = min(0.996, raw_prob * 1.15 if raw_prob >= 0.45 else raw_prob * 1.10)
            if yolo_key == best_key and yolo_conf > 0.5:
                calibrated = min(0.997, (calibrated * 0.65) + (yolo_conf * 0.35))
            verified_conf_pct = round(calibrated * 100.0, 1)
        else:
            verified_conf_pct = round(raw_prob * 100.0, 1)

        latency_ms = round((time.time() - start_t) * 1000.0, 1)

        # Step 3: Evaluate against Central Verification Policy
        if not is_top1_target and verified_conf_pct < 30.0:
            status = "REJECTED_NON_TARGET"
            is_verified = False
            verified_species = "Non-Target / False Positive"
            scientific_name = "Non-Target"
            species_agreement = False
            notes = (
                f"Central EfficientNet-B0 rejected edge claim ({edge_species or 'Unknown'}): "
                f"no target wildlife signature found (max target score {verified_conf_pct:.1f}%)."
            )
        elif verified_conf_pct < float(verify_threshold):
            meta = TARGET_SPECIES_INFO[best_key]
            status = "LOW_CONFIDENCE"
            is_verified = False
            verified_species = meta["common_name"]
            scientific_name = meta["scientific_name"]
            species_agreement = (edge_key == best_key)
            notes = (
                f"Candidate {verified_species} confidence ({verified_conf_pct:.1f}%) below central verification "
                f"policy threshold ({float(verify_threshold):.1f}%). Siren suppressed."
            )
        else:
            meta = TARGET_SPECIES_INFO[best_key]
            status = "VERIFIED"
            is_verified = True
            verified_species = meta["common_name"]
            scientific_name = meta["scientific_name"]
            species_agreement = (edge_key == best_key) if edge_key else True
            if species_agreement:
                notes = (
                    f"Central EfficientNet-B0 verified {verified_species} ({verified_conf_pct:.1f}%), "
                    f"confirming edge classification ({edge_species} @ {edge_confidence}%)."
                )
            else:
                notes = (
                    f"Central EfficientNet-B0 verified {verified_species} ({verified_conf_pct:.1f}%), "
                    f"reclassifying edge report ({edge_species} @ {edge_confidence}%)."
                )

        # Step 4: Save annotated central verification snapshot to static/snapshots/
        web_path = None
        if save_annotated:
            annotated = frame_bgr.copy()
            if bbox is None:
                bbox = [int(w * 0.10), int(h * 0.10), int(w * 0.90), int(h * 0.90)]
            x1, y1, x2, y2 = bbox
            color = (16, 185, 129) if is_verified else (0, 0, 235)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            header_txt = (
                f"CENTRAL VERIFIED: {verified_species.upper()} ({verified_conf_pct:.1f}%)"
                if is_verified
                else f"CENTRAL {status}: {verified_conf_pct:.1f}%"
            )
            (lw, lh), _ = cv2.getTextSize(header_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
            badge_y = max(28, y1 - lh - 10)
            cv2.rectangle(annotated, (x1, badge_y), (x1 + lw + 12, badge_y + lh + 8), color, -1)
            cv2.putText(
                annotated,
                header_txt,
                (x1 + 6, badge_y + lh + 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (0, 0, 0) if is_verified else (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            snap_dir = self.root_dir / "static" / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            safe_evt = str(event_id or int(time.time())).replace("/", "_").replace("\\", "_")[:36]
            snap_filename = f"verified_{safe_evt}.jpg"
            save_path = snap_dir / snap_filename
            cv2.imwrite(str(save_path), annotated)
            web_path = f"/static/snapshots/{snap_filename}"

        return {
            "is_verified": is_verified,
            "verification_status": status,
            "verified_species": verified_species,
            "verified_species_key": best_key if is_verified else "non_target",
            "scientific_name": scientific_name,
            "verified_confidence": verified_conf_pct,
            "species_agreement": species_agreement,
            "verification_model": "EfficientNet-B0 + YOLOv8-Verifier",
            "verification_notes": notes,
            "web_snapshot_path": web_path,
            "latency_ms": latency_ms,
        }
