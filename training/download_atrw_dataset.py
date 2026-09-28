"""
Project Indradhanu - ATRW Amur Tiger Dataset Extraction Pipeline
Dataset: Amur Tiger Re-identification in the Wild (ATRW) from LILA BC / CVWC 2019
Target Species:
  0: Tiger (Panthera tigris)
"""

import os
import sys
import glob
import time
import json
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import cv2
import numpy as np

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ATRW_IMAGE_TAR_URL = "https://storage.googleapis.com/public-datasets-lila/cvwc2019/train/atrw_detection_train.tar.gz"
ATRW_ANNO_TAR_URL = "https://storage.googleapis.com/public-datasets-lila/cvwc2019/train/atrw_anno_detection_train.tar.gz"

CACHE_DIR = "data_cache"
DATASET_DIR = "Indradhanu_Dataset"


def download_chunk(url, dest_path, start_byte, end_byte, chunk_idx):
    """Downloads a specific byte range and writes it to the target file."""
    headers = {
        "Range": f"bytes={start_byte}-{end_byte}",
        "User-Agent": "Indradhanu-Dataset-Pipeline/1.0"
    }
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
            with open(dest_path, "r+b") as f:
                f.seek(start_byte)
                f.write(data)
            return len(data)
        except Exception as e:
            if attempt == 3:
                raise e
            time.sleep(1.0 * (2 ** attempt))
    return 0


def ensure_atrw_tar_downloaded(cache_dir=CACHE_DIR, num_workers=8, chunk_size_mb=8):
    """
    Downloads the 2.18GB ATRW tarball using parallel chunked requests.
    Supports resuming or skipping if already completely downloaded.
    """
    os.makedirs(cache_dir, exist_ok=True)
    tar_path = os.path.join(cache_dir, "atrw_detection_train.tar.gz")

    # 1. Check remote file size via HEAD request
    req = urllib.request.Request(ATRW_IMAGE_TAR_URL, method="HEAD")
    with urllib.request.urlopen(req, timeout=15) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))

    if total_size <= 0:
        raise ValueError("Could not determine remote ATRW tarball size.")

    total_mb = total_size / (1024 * 1024)
    print(f"[ATRW Downloader] Remote archive size: {total_mb:.2f} MB ({total_size:,} bytes)")

    if os.path.exists(tar_path):
        local_size = os.path.getsize(tar_path)
        if local_size == total_size:
            print(f"[ATRW Downloader] Archive already fully downloaded: {tar_path}")
            return tar_path
        else:
            print(f"[ATRW Downloader] Partial download detected ({local_size/(1024*1024):.2f} MB / {total_mb:.2f} MB). Re-downloading...")
            os.remove(tar_path)

    # Pre-allocate destination file
    print(f"[ATRW Downloader] Pre-allocating {total_mb:.2f} MB on disk...")
    with open(tar_path, "wb") as f:
        f.truncate(total_size)

    chunk_size = chunk_size_mb * 1024 * 1024
    chunks = []
    offset = 0
    idx = 0
    while offset < total_size:
        end = min(offset + chunk_size - 1, total_size - 1)
        chunks.append((offset, end, idx))
        offset = end + 1
        idx += 1

    print(f"[ATRW Downloader] Downloading {len(chunks)} chunks with {num_workers} parallel workers...")
    start_time = time.time()
    downloaded_bytes = 0
    last_print = start_time

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_map = {
            executor.submit(download_chunk, ATRW_IMAGE_TAR_URL, tar_path, s, e, i): (s, e, i)
            for s, e, i in chunks
        }
        for future in as_completed(future_map):
            bytes_written = future.result()
            downloaded_bytes += bytes_written
            now = time.time()
            if now - last_print >= 5.0 or downloaded_bytes == total_size:
                elapsed = max(0.1, now - start_time)
                speed_mb = (downloaded_bytes / (1024 * 1024)) / elapsed
                pct = (downloaded_bytes / total_size) * 100.0
                dl_mb = downloaded_bytes / (1024 * 1024)
                eta = (total_size - downloaded_bytes) / (speed_mb * 1024 * 1024) if speed_mb > 0 else 0
                print(f"  Progress: {dl_mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%) | Speed: {speed_mb:.2f} MB/s | ETA: {eta:.0f}s")
                last_print = now

    total_time = time.time() - start_time
    avg_speed = total_mb / max(0.1, total_time)
    print(f"[ATRW Downloader] Complete in {total_time:.1f}s ({avg_speed:.2f} MB/s).")
    return tar_path


def parse_voc_xml(xml_path):
    """
    Parses Pascal VOC XML into normalized YOLO format:
    Class ID 0 (Tiger), x_center, y_center, width, height.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    img_w = float(size.find("width").text)
    img_h = float(size.find("height").text)

    boxes = []
    for obj in root.findall("object"):
        name = obj.find("name").text
        # Strict validation: ONLY Tiger
        if name.strip().lower() != "tiger":
            continue

        bbox = obj.find("bndbox")
        xmin = float(bbox.find("xmin").text)
        ymin = float(bbox.find("ymin").text)
        xmax = float(bbox.find("xmax").text)
        ymax = float(bbox.find("ymax").text)

        # Boundary clamping
        xmin = max(0.0, min(xmin, img_w))
        ymin = max(0.0, min(ymin, img_h))
        xmax = max(0.0, min(xmax, img_w))
        ymax = max(0.0, min(ymax, img_h))

        bw = xmax - xmin
        bh = ymax - ymin
        if bw <= 0.0 or bh <= 0.0:
            continue

        xc = (xmin + (bw / 2.0)) / img_w
        yc = (ymin + (bh / 2.0)) / img_h
        nw = bw / img_w
        nh = bh / img_h

        # Clamping
        xc = max(0.0, min(1.0, xc))
        yc = max(0.0, min(1.0, yc))
        nw = max(0.0, min(1.0, nw))
        nh = max(0.0, min(1.0, nh))

        boxes.append({
            "class_id": 0,
            "species": "tiger",
            "xc": xc,
            "yc": yc,
            "nw": nw,
            "nh": nh,
            "raw_bbox": [xmin, ymin, bw, bh],
            "img_w": img_w,
            "img_h": img_h
        })

    return img_w, img_h, boxes


def ingest_atrw_into_indradhanu(tar_path, output_dir=DATASET_DIR, anno_dir=os.path.join(CACHE_DIR, "Annotations")):
    """
    Extracts only annotated images from the ATRW tarball, generates YOLO labels,
    assigns splits (70% train / 20% val / 10% test), and updates metadata.
    """
    print("\n" + "=" * 70)
    print("🐅 INGESTING ATRW TIGER ANNOTATIONS & IMAGES INTO INDRADHANU")
    print("=" * 70)

    # 1. Map available XML annotations
    xml_files = glob.glob(os.path.join(anno_dir, "*.xml"))
    if not xml_files:
        raise FileNotFoundError(f"No XML annotations found in {anno_dir}")

    # Map image stem (e.g. '0001') -> xml_path
    stem_to_xml = {}
    for x in xml_files:
        stem = os.path.splitext(os.path.basename(x))[0]
        stem_to_xml[stem] = x

    print(f"[ATRW Ingestion] Found {len(stem_to_xml)} verified tiger XML annotations.")

    # 2. Assign reproducible splits (70% train / 20% val / 10% test)
    import random
    random.seed(42)
    stems = sorted(list(stem_to_xml.keys()))
    random.shuffle(stems)

    n_total = len(stems)
    n_train = int(n_total * 0.70)
    n_val = int(n_total * 0.20)

    stem_splits = {}
    for i, stem in enumerate(stems):
        if i < n_train:
            stem_splits[stem] = "train"
        elif i < n_train + n_val:
            stem_splits[stem] = "val"
        else:
            stem_splits[stem] = "test"

    print(f"[ATRW Ingestion] Split assignment: Train={n_train}, Val={n_val}, Test={n_total - n_train - n_val}")

    # 3. Open tarfile and extract matching images
    print(f"[ATRW Ingestion] Reading {tar_path}...")
    extracted_count = 0
    total_boxes_added = 0
    new_csv_rows = []

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue

            fname = os.path.basename(member.name)
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in [".jpg", ".jpeg"]:
                continue

            if stem not in stem_to_xml:
                # Strictly skip unannotated files if any
                continue

            split = stem_splits[stem]
            dest_img_name = f"atrw_tiger_{stem}.jpg"
            dest_lbl_name = f"atrw_tiger_{stem}.txt"

            dest_img_path = os.path.join(output_dir, "images", split, dest_img_name)
            dest_lbl_path = os.path.join(output_dir, "labels", split, dest_lbl_name)

            # Extract image
            img_file = tar.extractfile(member)
            if img_file is None:
                continue

            with open(dest_img_path, "wb") as f_out:
                f_out.write(img_file.read())

            # Parse XML annotation
            xml_path = stem_to_xml[stem]
            img_w, img_h, boxes = parse_voc_xml(xml_path)

            # Write YOLO labels
            yolo_lines = []
            for b in boxes:
                yolo_lines.append(f"{b['class_id']} {b['xc']:.6f} {b['yc']:.6f} {b['nw']:.6f} {b['nh']:.6f}")
                total_boxes_added += 1

                new_csv_rows.append({
                    "original_image_id": f"atrw_{stem}",
                    "wcs_file_name": member.name,
                    "local_image_path": dest_img_path,
                    "species": "tiger",
                    "source_dataset": "LILA_BC_ATRW_Tiger",
                    "bbox_x_min": b["raw_bbox"][0],
                    "bbox_y_min": b["raw_bbox"][1],
                    "bbox_width": b["raw_bbox"][2],
                    "bbox_height": b["raw_bbox"][3],
                    "image_width": img_w,
                    "image_height": img_h,
                    "split": split
                })

            with open(dest_lbl_path, "w", encoding="utf-8") as lf:
                lf.write("\n".join(yolo_lines))

            extracted_count += 1
            if extracted_count % 250 == 0 or extracted_count == len(stem_to_xml):
                print(f"  Extracted: {extracted_count}/{len(stem_to_xml)} images | Boxes added: {total_boxes_added}")

    print(f"\n[ATRW Ingestion] Successfully extracted {extracted_count} annotated tiger images ({total_boxes_added} boxes).")

    # 4. Append to annotations.csv
    ann_csv_path = os.path.join(output_dir, "metadata", "annotations.csv")
    file_exists = os.path.exists(ann_csv_path)
    with open(ann_csv_path, "a", newline="", encoding="utf-8") as f:
        fieldnames = ["original_image_id", "wcs_file_name", "local_image_path", "species", 
                      "source_dataset", "bbox_x_min", "bbox_y_min", "bbox_width", "bbox_height", 
                      "image_width", "image_height", "split"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_csv_rows)

    print(f"[Metadata] Appended {len(new_csv_rows)} records to annotations.csv.")

    # 5. Recompute and save class_counts.csv
    recompute_class_counts(output_dir)


def recompute_class_counts(dataset_dir=DATASET_DIR):
    """Counts YOLO bounding boxes across train, val, test and updates class_counts.csv."""
    class_map = {0: "tiger", 1: "leopard", 2: "sloth_bear", 3: "asiatic_lion"}
    stats = {cls_id: {"train": 0, "val": 0, "test": 0} for cls_id in class_map}

    for split in ["train", "val", "test"]:
        lbl_dir = os.path.join(dataset_dir, "labels", split)
        lbl_files = glob.glob(os.path.join(lbl_dir, "*.txt"))
        for lf in lbl_files:
            with open(lf, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        cid = int(parts[0])
                        if cid in stats:
                            stats[cid][split] += 1

    counts_csv_path = os.path.join(dataset_dir, "metadata", "class_counts.csv")
    with open(counts_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["species", "class_id", "train_annotations", "val_annotations", "test_annotations", "total_annotations"])
        for cid, name in class_map.items():
            tr = stats[cid]["train"]
            va = stats[cid]["val"]
            te = stats[cid]["test"]
            writer.writerow([name, cid, tr, va, te, tr + va + te])

    print("\n" + "=" * 70)
    print("📊 UPDATED DATASET CLASS COUNTS")
    print("=" * 70)
    for cid, name in class_map.items():
        total = stats[cid]["train"] + stats[cid]["val"] + stats[cid]["test"]
        print(f"  Class {cid} ({name:12s}): Train={stats[cid]['train']:4d} | Val={stats[cid]['val']:4d} | Test={stats[cid]['test']:4d} | Total={total:4d}")
    print("=" * 70 + "\n")


def main():
    print("=" * 70)
    print("🐅 PROJECT INDRADHANU - ATRW TIGER INGESTION PIPELINE")
    print("=" * 70)

    # Step 1: Ensure ATRW tar is downloaded
    tar_path = ensure_atrw_tar_downloaded()

    # Step 2: Ingest annotated images into Indradhanu_Dataset
    ingest_atrw_into_indradhanu(tar_path)

    # Step 3: Run verification and contact sheet update
    from download_indradhanu_dataset import verify_dataset_and_generate_contact_sheet
    verify_dataset_and_generate_contact_sheet(DATASET_DIR)


if __name__ == "__main__":
    main()
