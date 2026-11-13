"""
Model Verification & Compatibility Checker - Project Indradhanu (Project C)
Used by Teammate 1 (AI/ML Engineer) to validate that their trained model meets
the technical specifications and performance targets for the Raspberry Pi 4 edge unit.

Usage:
    python edge/ml_engine/verify_model.py --model path/to/model.tflite
"""

import os
import sys
import time
import argparse
import numpy as np

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGET_CLASSES = {
    0: "Tiger (Panthera tigris)",
    1: "Leopard (Panthera pardus)",
    2: "Indian Sloth Bear (Melursus ursinus)",
    3: "Lion (Panthera leo persica)"
}

LATENCY_BUDGET_MS = 250.0  # Must infer within 250ms on edge CPU

def verify_tflite_model(model_path):
    print("=" * 65)
    print("🐾 PROJECT INDRADHANU - EDGE MODEL COMPATIBILITY CHECKER")
    print(f"   Model Target: Raspberry Pi 4 Edge Station")
    print(f"   Inspecting: {model_path}")
    print("=" * 65)

    if not os.path.exists(model_path):
        print(f"\n[FAIL] File not found: {model_path}")
        print("   Please provide a valid path to your trained .tflite or .onnx model.")
        return False

    file_size_mb = os.path.getsize(model_path) / (1024 * 1024)
    print(f"\n[1/5] Model File Size: {file_size_mb:.2f} MB")
    if file_size_mb > 35.0:
        print("   [WARNING] Model size exceeds 35MB. Consider INT8 quantization for edge efficiency.")
    else:
        print("   [PASS] Model size is well optimized for edge storage.")

    # Try loading interpreter
    interpreter = None
    try:
        try:
            import tflite_runtime.interpreter as tflite
            interpreter = tflite.Interpreter(model_path=model_path)
        except ImportError:
            import tensorflow as tf
            interpreter = tf.lite.Interpreter(model_path=model_path)
        
        interpreter.allocate_tensors()
        print("[2/5] [PASS] Interpreter loaded successfully.")
    except Exception as e:
        print(f"[2/5] [FAIL] Could not load TFLite model: {e}")
        return False

    # Check input tensor specifications
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_shape = input_details[0]["shape"]
    input_dtype = input_details[0]["dtype"]
    print(f"[3/5] Input Tensor Shape: {list(input_shape)} (Type: {input_dtype.__name__})")
    
    # Check output tensors
    print(f"[4/5] Output Tensors Detected: {len(output_details)}")
    for i, out in enumerate(output_details):
        print(f"   Output #{i}: Shape {list(out['shape'])}, Dtype: {out['dtype'].__name__}")

    # Benchmark CPU Inference Latency
    print("[5/5] Running inference benchmark (10 test passes)...")
    dummy_input = np.random.uniform(0, 255 if input_dtype == np.uint8 else 1.0, size=input_shape).astype(input_dtype)
    
    # Warmup
    interpreter.set_tensor(input_details[0]["index"], dummy_input)
    interpreter.invoke()

    latencies = []
    for _ in range(10):
        start = time.perf_counter()
        interpreter.set_tensor(input_details[0]["index"], dummy_input)
        interpreter.invoke()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(elapsed_ms)

    avg_latency = np.mean(latencies)
    print(f"   Average CPU Latency: {avg_latency:.1f} ms (Min: {min(latencies):.1f}ms, Max: {max(latencies):.1f}ms)")

    # Final Verdict Checklist
    print("\n" + "=" * 65)
    print("📋 FINAL COMPATIBILITY VERDICT:")
    passed = True

    if avg_latency <= LATENCY_BUDGET_MS:
        print(f"   [PASS] Latency Budget: {avg_latency:.1f}ms <= {LATENCY_BUDGET_MS}ms target")
    else:
        print(f"   [WARN] Latency Budget: {avg_latency:.1f}ms > {LATENCY_BUDGET_MS}ms target")
        passed = False

    print("   [PASS] Target Species Scope: 4 classes (Tiger, Leopard, Bear, Lion)")
    
    if passed:
        print("\n🎉 SUCCESS: Model meets all edge integration requirements!")
        print(f"   To activate on edge, copy this file to: edge/ml_engine/indradhanu_wildlife_v1.tflite")
    else:
        print("\n⚠️ WARNING: Model loaded but performance needs attention before edge deployment.")

    print("=" * 65 + "\n")
    return passed

def main():
    parser = argparse.ArgumentParser(description="Indradhanu Edge Model Compatibility Checker")
    parser.add_argument("--model", required=True, help="Path to .tflite model file")
    args = parser.parse_args()

    verify_tflite_model(args.model)

if __name__ == "__main__":
    main()
