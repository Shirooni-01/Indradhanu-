"""
Project Indradhanu - Edge AI Model Training Pipeline
Target: Apex Predator Detection (Tiger & Leopard)
Edge Target: Raspberry Pi 4 (via TFLite / ONNX export)
"""

import os
import sys
import time
import shutil
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def print_banner():
    print("=" * 72)
    print(" 🐅 PROJECT INDRADHANU — WILDLIFE PERIMETER SURVEILLANCE AI")
    print(" Model: YOLOv8n (Nano) | Target Classes: 0: Tiger, 1: Leopard")
    print(" Deployment Target: Raspberry Pi 4 Edge Computing Unit")
    print("=" * 72)

def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 on Indradhanu Tiger & Leopard Dataset")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Pretrained model checkpoint (default: yolov8n.pt)")
    parser.add_argument("--data", type=str, default=str(Path("Indradhanu_Dataset/metadata/data_2class.yaml").resolve()), help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs (default: 50)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16, ~3.2 GB VRAM)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image resolution (default: 640)")
    parser.add_argument("--patience", type=int, default=10, help="Early stopping patience (default: 10)")
    parser.add_argument("--workers", type=int, default=4, help="Dataloader workers (default: 4)")
    parser.add_argument("--device", type=str, default="0", help="CUDA device index or 'cpu'")
    parser.add_argument("--name", type=str, default="indradhanu_tiger_leopard", help="Experiment name")
    parser.add_argument("--project", type=str, default="runs/detect", help="Project output folder")
    parser.add_argument("--export-tflite", action="store_true", default=True, help="Automatically export best model to TFLite for Raspberry Pi")
    args = parser.parse_args()

    print_banner()

    # 1. Environment & Hardware Diagnostics
    import torch
    from ultralytics import YOLO

    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU (No GPU detected)"
    
    print(f"\n[+] PyTorch Version    : {torch.__version__}")
    print(f"[+] CUDA Available     : {'YES ✅' if cuda_available else 'NO (CPU Mode) ⚠️'}")
    print(f"[+] Compute Device     : {device_name}")
    if cuda_available:
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"[+] Total GPU VRAM     : {vram_gb:.2f} GB")
        print(f"[+] Hardware Match     : NVIDIA RTX 4050 Laptop GPU (Ada Lovelace Tensor Cores active)")

    # 2. Dataset Verification
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"\n❌ Error: Dataset config '{data_path}' not found!")
        sys.exit(1)

    dataset_root = Path("Indradhanu_Dataset")
    train_imgs = list((dataset_root / "images" / "train").glob("*.*"))
    val_imgs = list((dataset_root / "images" / "val").glob("*.*"))
    print(f"\n[+] Dataset Config     : {data_path}")
    print(f"[+] Training Images    : {len(train_imgs):,} images")
    print(f"[+] Validation Images  : {len(val_imgs):,} images")
    print(f"[+] Planned Epochs     : {args.epochs}")
    print(f"[+] Batch Size         : {args.batch}")
    print(f"[+] Image Resolution   : {args.imgsz}x{args.imgsz}")

    # 3. Model Initialization
    print(f"\n[+] Loading base model : {args.model} ...")
    model = YOLO(args.model)

    # 4. Training Execution
    start_time = time.time()
    print("\n" + "=" * 72)
    print(" 🚀 STARTING TRAINING (Press Ctrl+C anytime to pause/stop)")
    print("=" * 72 + "\n")

    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        workers=args.workers,
        device=args.device if cuda_available else "cpu",
        project=args.project,
        name=args.name,
        amp=True,              # Automatic Mixed Precision for RTX Tensor Cores
        plots=True,            # Generate loss and PR curve plots
        save=True,             # Save checkpoints
        save_period=5,         # Save checkpoint every 5 epochs
        exist_ok=True,
        verbose=True
    )

    elapsed_min = (time.time() - start_time) / 60.0
    print("\n" + "=" * 72)
    print(f" ✅ TRAINING COMPLETE in {elapsed_min:.2f} minutes!")
    print("=" * 72)

    # 5. Model Paths & Artifact Management
    best_pt = Path(args.project) / args.name / "weights" / "best.pt"
    if not best_pt.exists():
        # Fallback search
        found_weights = list(Path(args.project).glob(f"**/{args.name}/**/best.pt"))
        if found_weights:
            best_pt = found_weights[0]

    print(f"\n[+] Best PyTorch Weights : {best_pt}")

    # Ensure ml_engine/weights directory exists
    ml_weights_dir = Path("ml_engine/weights")
    ml_weights_dir.mkdir(parents=True, exist_ok=True)
    
    deployed_pt = ml_weights_dir / "indradhanu_best.pt"
    if best_pt.exists():
        shutil.copy(best_pt, deployed_pt)
        print(f"[+] Deployed to Engine   : {deployed_pt} ({deployed_pt.stat().st_size / (1024**2):.2f} MB)")

    # 6. Automatic Edge Export for Raspberry Pi 4
    if args.export_tflite and best_pt.exists():
        print("\n[+] Exporting model to TensorFlow Lite (TFLite) for Raspberry Pi 4...")
        try:
            best_model = YOLO(str(best_pt))
            exported_tflite = best_model.export(format="tflite", imgsz=args.imgsz)
            print(f"[+] Exported TFLite Model: {exported_tflite}")
            
            # Copy to ml_engine/weights
            tflite_path = Path(exported_tflite)
            if tflite_path.exists():
                deployed_tflite = ml_weights_dir / "indradhanu_best.tflite"
                shutil.copy(tflite_path, deployed_tflite)
                print(f"[+] Ready for Raspberry Pi: {deployed_tflite} ({deployed_tflite.stat().st_size / (1024**2):.2f} MB)")
        except Exception as e:
            print(f"[-] Note: TFLite export skipped or encountered notice: {e}")
            print("    You can still export manually using: yolo export model=" + str(best_pt) + " format=tflite")

    print("\n" + "=" * 72)
    print(" 🎉 ALL SET! You can now integrate the model into app.py or run_edge.py")
    print("=" * 72)

if __name__ == "__main__":
    main()
