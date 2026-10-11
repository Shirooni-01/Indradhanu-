"""
Project Indradhanu - Leopard ID 2022 Dataset Extraction Pipeline
Dataset: Leopard ID 2022 from LILA BC / Wild Me (Panthera pardus)
Target Species:
  1: Leopard (Panthera pardus)
"""

import os
import sys
import glob
import time
import json
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import cv2
import numpy as np

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LEOPARD_TAR_URL = "https://storage.googleapis.com/public-datasets-lila/wild-me/leopard.coco.tar.gz"
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
            with urllib.request.urlopen(req, timeout=30) as resp:
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


def ensure_leopard_tar_downloaded(cache_dir=CACHE_DIR, num_workers=10, chunk_size_mb=12):
    """
    Downloads the ~8.16GB Leopard ID tarball using parallel chunked requests.
    Supports resuming or skipping if already completely downloaded.
    """
    os.makedirs(cache_dir, exist_ok=True)
    tar_path = os.path.join(cache_dir, "leopard.coco.tar.gz")

    # 1. Check remote file size via HEAD request
    req = urllib.request.Request(LEOPARD_TAR_URL, method="HEAD")
    with urllib.request.urlopen(req, timeout=15) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))

    if total_size <= 0:
        raise ValueError("Could not determine remote Leopard tarball size.")

    total_mb = total_size / (1024 * 1024)
    print(f"[Leopard Downloader] Remote archive size: {total_mb:.2f} MB ({total_size:,} bytes)")

    if os.path.exists(tar_path):
        local_size = os.path.getsize(tar_path)
        if local_size == total_size:
            print(f"[Leopard Downloader] Archive already fully downloaded: {tar_path}")
            return tar_path
        else:
            print(f"[Leopard Downloader] Partial download detected ({local_size/(1024*1024):.2f} MB / {total_mb:.2f} MB). Re-downloading...")
            os.remove(tar_path)

    # Pre-allocate destination file
    print(f"[Leopard Downloader] Pre-allocating {total_mb:.2f} MB on disk...")
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

    print(f"[Leopard Downloader] Downloading {len(chunks)} chunks with {num_workers} parallel workers...")
    start_time = time.time()
    downloaded_bytes = 0
    last_print = start_time

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_map = {
            executor.submit(download_chunk, LEOPARD_TAR_URL, tar_path, s, e, i): (s, e, i)
            for s, e, i in chunks
        }
        for future in as_completed(future_map):
            bytes_written = future.result()
            downloaded_bytes += bytes_written
            now = time.time()
            if now - last_print >= 8.0 or downloaded_bytes == total_size:
                elapsed = max(0.1, now - start_time)
                speed_mb = (downloaded_bytes / (1024 * 1024)) / elapsed
                pct = (downloaded_bytes / total_size) * 100.0
                dl_mb = downloaded_bytes / (1024 * 1024)
                eta = (total_size - downloaded_bytes) / (speed_mb * 1024 * 1024) if speed_mb > 0 else 0
                print(f"  Progress: {dl_mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%) | Speed: {speed_mb:.2f} MB/s | ETA: {eta:.0f}s")
                last_print = now

    total_time = time.time() - start_time
    avg_speed = total_mb / max(0.1, total_time)
    print(f"[Leopard Downloader] Complete in {total_time:.1f}s ({avg_speed:.2f} MB/s).")
    return tar_path


def convert_coco_to_yolo_bbox(coco_bbox, img_width, img_height):
    """
    Converts COCO [x_min, y_min, width, height] to YOLO [x_center, y_center, width, height] normalized.
    """
    x_min, y_min, w, h = coco_bbox
    
    # Clip coordinates to image boundaries
    x_min = max(0.0, min(float(x_min), float(img_width)))
    y_min = max(0.0, min(float(y_min), float(img_height)))
    w = max(0.0, min(float(w), float(img_width) - x_min))
    h = max(0.0, min(float(h), float(img_height) - y_min))

    if w <= 0.0 or h <= 0.0 or img_width <= 0 or img_height <= 0:
        return None

    x_center = (x_min + (w / 2.0)) / img_width
    y_center = (y_min + (h / 2.0)) / img_height
    norm_w = w / img_width
    norm_h = h / img_height

    x_center = max(0.0, min(1.0, x_center))
    y_center = max(0.0, min(1.0, y_center))
    norm_w = max(0.0, min(1.0, norm_w))
    norm_h = max(0.0, min(1.0, norm_h))

    return x_center, y_center, norm_w, norm_h


def ingest_leopard_into_indradhanu(tar_path, output_dir=DATASET_DIR, 
                                   json_path=os.path.join(CACHE_DIR, "leopard_instances_train2022.json"),
                                   max_images=None):
    """
    Extracts annotated images from the Leopard ID tarball, generates YOLO labels (Class 1),
    assigns splits (70% train / 20% val / 10% test), and updates metadata.
    """
    print("\n" + "=" * 70)
    print("🐆 INGESTING LEOPARD ID 2022 ANNOTATIONS & IMAGES INTO INDRADHANU")
    print("=" * 70)

    # 1. Load COCO annotations
    with open(json_path, "r", encoding="utf-8") as f:
        coco_data = json.load(f)

    images_info = {img["id"]: img for img in coco_data["images"]}
    fname_to_img = {img["file_name"]: img for img in coco_data["images"]}

    # Group annotations by image_id
    anns_by_img_id = {}
    for a in coco_data["annotations"]:
        iid = a["image_id"]
        if iid not in anns_by_img_id:
            anns_by_img_id[iid] = []
        anns_by_img_id[iid].append(a)

    print(f"[Leopard Ingestion] Total images in JSON: {len(images_info)}, Annotated images: {len(anns_by_img_id)}")

    # 2. Determine target images & assign reproducible splits
    import random
    random.seed(42)
    annotated_img_ids = sorted(list(anns_by_img_id.keys()))
    random.shuffle(annotated_img_ids)

    if max_images and max_images < len(annotated_img_ids):
        annotated_img_ids = annotated_img_ids[:max_images]
        print(f"[Leopard Ingestion] Capping to {max_images} images.")

    n_total = len(annotated_img_ids)
    n_train = int(n_total * 0.70)
    n_val = int(n_total * 0.20)

    img_id_splits = {}
    for i, iid in enumerate(annotated_img_ids):
        if i < n_train:
            img_id_splits[iid] = "train"
        elif i < n_train + n_val:
            img_id_splits[iid] = "val"
        else:
            img_id_splits[iid] = "test"

    print(f"[Leopard Ingestion] Split assignment: Train={n_train}, Val={n_val}, Test={n_total - n_train - n_val}")

    # Map file_name -> iid
    target_fnames = {images_info[iid]["file_name"]: iid for iid in annotated_img_ids}

    # 3. Stream through tarball and extract target images
    print(f"[Leopard Ingestion] Extracting matching images from {tar_path}...")
    extracted_count = 0
    total_boxes_added = 0
    new_csv_rows = []

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue

            fname = os.path.basename(member.name)
            if fname not in target_fnames:
                continue

            iid = target_fnames[fname]
            split = img_id_splits[iid]
            img_info = images_info[iid]
            img_w = img_info["width"]
            img_h = img_info["height"]

            clean_stem = os.path.splitext(fname)[0]
            dest_img_name = f"leopard_wildme_{clean_stem}.jpg"
            dest_lbl_name = f"leopard_wildme_{clean_stem}.txt"

            dest_img_path = os.path.join(output_dir, "images", split, dest_img_name)
            dest_lbl_path = os.path.join(output_dir, "labels", split, dest_lbl_name)

            # Extract image
            img_file = tar.extractfile(member)
            if img_file is None:
                continue

            with open(dest_img_path, "wb") as f_out:
                f_out.write(img_file.read())

            # Generate YOLO annotations (Class ID: 1 for leopard)
            yolo_lines = []
            for a in anns_by_img_id.get(iid, []):
                coco_box = a["bbox"]
                yolo_coords = convert_coco_to_yolo_bbox(coco_box, img_w, img_h)
                if yolo_coords is None:
                    continue

                xc, yc, nw, nh = yolo_coords
                # Class 1: Leopard
                yolo_lines.append(f"1 {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}")
                total_boxes_added += 1

                new_csv_rows.append({
                    "original_image_id": f"wildme_{iid}",
                    "wcs_file_name": member.name,
                    "local_image_path": dest_img_path,
                    "species": "leopard",
                    "source_dataset": "LILA_BC_Leopard_ID_2022",
                    "bbox_x_min": coco_box[0],
                    "bbox_y_min": coco_box[1],
                    "bbox_width": coco_box[2],
                    "bbox_height": coco_box[3],
                    "image_width": img_w,
                    "image_height": img_h,
                    "split": split
                })

            with open(dest_lbl_path, "w", encoding="utf-8") as lf:
                lf.write("\n".join(yolo_lines))

            extracted_count += 1
            if extracted_count % 500 == 0 or extracted_count == len(target_fnames):
                print(f"  Extracted: {extracted_count}/{len(target_fnames)} images | Boxes added: {total_boxes_added}")

    print(f"\n[Leopard Ingestion] Successfully extracted {extracted_count} annotated leopard images ({total_boxes_added} boxes).")

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

    # 5. Recompute class counts
    from download_atrw_dataset import recompute_class_counts
    recompute_class_counts(output_dir)


def main():
    print("=" * 70)
    print("🐆 PROJECT INDRADHANU - LEOPARD ID 2022 INGESTION PIPELINE")
    print("=" * 70)

    # Step 1: Ensure Leopard tar is downloaded
    tar_path = ensure_leopard_tar_downloaded()

    # Step 2: Ingest annotated images into Indradhanu_Dataset
    ingest_leopard_into_indradhanu(tar_path)

    # Step 3: Run verification and contact sheet update
    from download_indradhanu_dataset import verify_dataset_and_generate_contact_sheet
    verify_dataset_and_generate_contact_sheet(DATASET_DIR)


if __name__ == "__main__":
    main()
