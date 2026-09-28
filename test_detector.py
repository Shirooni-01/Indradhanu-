"""
Project Indradhanu - Apex Predator Detection Testing & Verification Tool
Tests the trained model (indradhanu_best.pt / indradhanu_best.onnx) on unseen test data.
"""

import os
import sys
import glob
import random
import argparse
import subprocess
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPECIES_METADATA = {
    0: {"name": "Tiger", "color": (0, 140, 255), "threat": "CRITICAL"},      # Orange / Amber in BGR
    1: {"name": "Leopard", "color": (0, 215, 255), "threat": "CRITICAL"},    # Yellow in BGR
    2: {"name": "Sloth Bear", "color": (255, 100, 0), "threat": "HIGH"},
    3: {"name": "Asiatic Lion", "color": (0, 255, 255), "threat": "CRITICAL"}
}

def draw_tactical_hud(img, boxes, names):
    """Draws tactical surveillance HUD bounding boxes and badges on detection."""
    annotated = img.copy()
    h, w = annotated.shape[:2]
    
    # Top HUD Bar
    cv2.rectangle(annotated, (0, 0), (w, 40), (20, 20, 20), -1)
    cv2.putText(annotated, "INDRADHANU PERIMETER SURVEILLANCE - AI VISION", 
                (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2, cv2.LINE_AA)

    detected_count = len(boxes)
    status_text = f"TARGETS DETECTED: {detected_count}" if detected_count > 0 else "SECTOR CLEAR"
    status_color = (0, 0, 255) if detected_count > 0 else (0, 255, 0)
    cv2.putText(annotated, status_text, (w - 240, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2, cv2.LINE_AA)

    for box in boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].cpu().numpy().astype(int)
        x1, y1, x2, y2 = xyxy

        meta = SPECIES_METADATA.get(cls_id, {"name": names.get(cls_id, "Unknown"), "color": (0, 255, 0), "threat": "MEDIUM"})
        color = meta["color"]

        # Corner bracket tactical box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        corner_len = min(25, (x2 - x1) // 4, (y2 - y1) // 4)
        thickness = 4
        # Top-left
        cv2.line(annotated, (x1, y1), (x1 + corner_len, y1), color, thickness)
        cv2.line(annotated, (x1, y1), (x1, y1 + corner_len), color, thickness)
        # Top-right
        cv2.line(annotated, (x2, y1), (x2 - corner_len, y1), color, thickness)
        cv2.line(annotated, (x2, y1), (x2, y1 + corner_len), color, thickness)
        # Bottom-left
        cv2.line(annotated, (x1, y2), (x1 + corner_len, y2), color, thickness)
        cv2.line(annotated, (x1, y2), (x1, y2 - corner_len), color, thickness)
        # Bottom-right
        cv2.line(annotated, (x2, y2), (x2 - corner_len, y2), color, thickness)
        cv2.line(annotated, (x2, y2), (x2, y2 - corner_len), color, thickness)

        # Label badge
        label = f"{meta['name'].upper()} {conf:.1%} [{meta['threat']}]"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        badge_y1 = max(42, y1 - lh - 10)
        cv2.rectangle(annotated, (x1, badge_y1), (x1 + lw + 12, badge_y1 + lh + 8), color, -1)
        cv2.putText(annotated, label, (x1 + 6, badge_y1 + lh + 3), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

    return annotated

def test_random_samples(model, num_samples=6, output_dir="test_results"):
    """Picks random unseen images from test set (half tigers, half leopards) and runs detection."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    test_labels = list(Path("Indradhanu_Dataset/labels/test").glob("*.txt"))
    tiger_imgs = []
    leopard_imgs = []

    for lf in test_labels:
        with open(lf, "r") as f:
            lines = f.readlines()
        img_name = lf.stem + ".jpg"
        img_path = Path("Indradhanu_Dataset/images/test") / img_name
        if not img_path.exists():
            continue
        if any(l.startswith("0 ") for l in lines):
            tiger_imgs.append(img_path)
        elif any(l.startswith("1 ") for l in lines):
            leopard_imgs.append(img_path)

    sample_tigers = random.sample(tiger_imgs, min(num_samples // 2, len(tiger_imgs)))
    sample_leopards = random.sample(leopard_imgs, min(num_samples - len(sample_tigers), len(leopard_imgs)))
    samples = sample_tigers + sample_leopards
    random.shuffle(samples)

    print(f"\n[+] Selected {len(samples)} random test images ({len(sample_tigers)} Tigers, {len(sample_leopards)} Leopards)")
    print(f"[+] Output directory: {out_path.resolve()}\n")

    saved_files = []
    for i, img_p in enumerate(samples, 1):
        res = model.predict(str(img_p), conf=0.45, verbose=False)[0]
        orig = cv2.imread(str(img_p))
        if orig is None:
            continue
        annotated = draw_tactical_hud(orig, res.boxes, model.names)

        save_name = f"test_{i:02d}_{img_p.stem[:8]}.jpg"
        save_file = out_path / save_name
        cv2.imwrite(str(save_file), annotated)
        saved_files.append(save_file)

        dets = [f"{model.names[int(b.cls[0])]}: {float(b.conf[0]):.1%}" for b in res.boxes]
        det_str = ", ".join(dets) if dets else "No target detected"
        print(f" [{i}/{len(samples)}] {img_p.name} -> {det_str} | Saved: {save_name}")

    # Build side-by-side contact collage
    collage_rows = []
    cell_w, cell_h = 480, 320
    row = []
    for sf in saved_files:
        im = cv2.imread(str(sf))
        if im is not None:
            resized = cv2.resize(im, (cell_w, cell_h))
            row.append(resized)
            if len(row) == 3:
                collage_rows.append(np.hstack(row))
                row = []
    if row:
        while len(row) < 3:
            row.append(np.zeros((cell_h, cell_w, 3), dtype=np.uint8))
        collage_rows.append(np.hstack(row))

    if collage_rows:
        collage = np.vstack(collage_rows)
        collage_path = out_path / "contact_sheet_summary.jpg"
        cv2.imwrite(str(collage_path), collage)
        print(f"\n[+] Created summary collage: {collage_path.resolve()}")

    return out_path

def test_single_image(model, image_path, output_dir="test_results"):
    """Runs detection on a specific image."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    img_p = Path(image_path)
    if not img_p.exists():
        print(f"❌ Error: Image '{image_path}' not found!")
        return None

    res = model.predict(str(img_p), conf=0.4, verbose=True)[0]
    orig = cv2.imread(str(img_p))
    annotated = draw_tactical_hud(orig, res.boxes, model.names)

    save_file = out_path / f"result_{img_p.stem}.jpg"
    cv2.imwrite(str(save_file), annotated)
    print(f"\n[+] Result saved to: {save_file.resolve()}")
    return save_file

def evaluate_full_test_split(model):
    """Runs full evaluation on all 1,006 unseen test set images."""
    data_yaml = Path("Indradhanu_Dataset/metadata/data_2class.yaml").resolve()
    print(f"\n[+] Running official YOLO evaluation on the entire test set (1,006 images)...")
    metrics = model.val(data=str(data_yaml), split="test", conf=0.4, iou=0.6, verbose=True)
    print("\n" + "=" * 65)
    print(" 🎯 FINAL TEST SET EVALUATION REPORT (100% UNSEEN DATA)")
    print("=" * 65)
    print(f" Overall mAP50       : {metrics.box.map50:.3%}")
    print(f" Overall mAP50-95    : {metrics.box.map:.3%}")
    print(f" Precision (P)       : {metrics.box.mp:.3%}")
    print(f" Recall (R)          : {metrics.box.mr:.3%}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Test Indradhanu Wildlife Detector")
    parser.add_argument("--weights", type=str, default="ml_engine/weights/indradhanu_best.pt", help="Path to weights")
    parser.add_argument("--random", type=int, default=6, help="Number of random test images to evaluate (default: 6)")
    parser.add_argument("--image", type=str, default=None, help="Path to specific image file to test")
    parser.add_argument("--eval-test", action="store_true", help="Run full evaluation on all 1,006 test images")
    parser.add_argument("--open", action="store_true", default=True, help="Open output folder automatically in Windows Explorer")
    args = parser.parse_args()

    print("=" * 65)
    print(" 🐅 PROJECT INDRADHANU — TEST & VERIFICATION SUITE")
    print(f" Weights: {args.weights}")
    print("=" * 65)

    if not Path(args.weights).exists():
        print(f"❌ Error: Weights file '{args.weights}' not found!")
        sys.exit(1)

    model = YOLO(args.weights)

    if args.eval_test:
        evaluate_full_test_split(model)
    elif args.image:
        result_file = test_single_image(model, args.image)
        if args.open and result_file and result_file.exists():
            subprocess.run(["explorer.exe", str(result_file.parent)], shell=True)
    else:
        out_folder = test_random_samples(model, num_samples=args.random)
        if args.open and out_folder.exists():
            print(f"\n[+] Opening results in Windows Explorer...")
            subprocess.run(["explorer.exe", str(out_folder.resolve())], shell=True)

if __name__ == "__main__":
    main()
