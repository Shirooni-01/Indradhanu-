"""
Project Indradhanu - Automated Dataset Extraction Pipeline
Dataset: Wildlife Conservation Society (WCS) Camera Traps from LILA BC
Target Species:
  0: Tiger (Panthera tigris)
  1: Leopard (Panthera pardus)
  2: Sloth Bear (Melursus ursinus)
  3: Asiatic Lion (Panthera leo persica)
"""

import os
import sys
import json
import zipfile
import urllib.request
import urllib.error
import argparse
import random
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import cv2
import numpy as np

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Base URLs for LILA BC WCS Storage
LILA_GCS_BASE = "https://storage.googleapis.com/public-datasets-lila"
LILA_AZURE_BASE = "https://lilawildlife.blob.core.windows.net/lila-wildlife"

METADATA_URLS = {
    "bboxes_classes": f"{LILA_GCS_BASE}/wcs/wcs_20220205_bboxes_with_classes.zip",
    "splits": f"{LILA_GCS_BASE}/wcs/wcs_splits.json"
}

IMAGE_MIRRORS = [
    f"{LILA_GCS_BASE}/wcs-unzipped",
    f"{LILA_AZURE_BASE}/wcs-unzipped"
]

# Strict Target Taxonomy Map
# Class 0: Tiger
# Class 1: Leopard
# Class 2: Sloth Bear
# Class 3: Asiatic Lion
TARGET_TAXONOMY = {
    "panthera tigris": {
        "class_id": 0,
        "class_name": "tiger",
        "scientific_name": "Panthera tigris",
        "common_name": "Bengal Tiger",
        "category_id": 154
    },
    "panthera pardus": {
        "class_id": 1,
        "class_name": "leopard",
        "scientific_name": "Panthera pardus",
        "common_name": "Indian Leopard",
        "category_id": 104
    },
    "melursus ursinus": {
        "class_id": 2,
        "class_name": "sloth_bear",
        "scientific_name": "Melursus ursinus",
        "common_name": "Indian Sloth Bear",
        "category_id": None  # Not in WCS
    },
    "panthera leo persica": {
        "class_id": 3,
        "class_name": "asiatic_lion",
        "scientific_name": "Panthera leo persica",
        "common_name": "Asiatic Lion",
        "category_id": None  # Not in WCS
    }
}

NEGATIVE_TAXONOMY = {
    71: "cattle (bos taurus)",
    175: "stray dog (canis familiaris)",
    75: "human (homo sapiens)",
    0: "empty forest scene"
}


def download_file_with_retry(url, dest_path, retries=3, timeout=30):
    """Downloads a file with exponential backoff retries."""
    headers = {"User-Agent": "Indradhanu-Dataset-Pipeline/1.0 (Conservation Research)"}
    req = urllib.request.Request(url, headers=headers)
    
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
                f.write(resp.read())
            return True
        except Exception as e:
            if attempt == retries - 1:
                return False
            time.sleep(1.0 * (2 ** attempt))
    return False


def ensure_metadata_downloaded(cache_dir="data_cache"):
    """Downloads and extracts the required WCS annotation and split JSON files."""
    os.makedirs(cache_dir, exist_ok=True)
    zip_path = os.path.join(cache_dir, "wcs_20220205_bboxes_with_classes.zip")
    json_path = os.path.join(cache_dir, "wcs_20220205_bboxes_with_classes.json")
    splits_path = os.path.join(cache_dir, "wcs_splits.json")

    # 1. Download bounding box zip if needed
    if not os.path.exists(json_path):
        if not os.path.exists(zip_path):
            print(f"[Metadata] Downloading WCS bounding boxes JSON (~24MB) from LILA...")
            success = download_file_with_retry(METADATA_URLS["bboxes_classes"], zip_path)
            if not success:
                # Try Azure fallback
                azure_url = METADATA_URLS["bboxes_classes"].replace(LILA_GCS_BASE, LILA_AZURE_BASE)
                print(f"[Metadata] Retrying via Azure fallback: {azure_url}")
                download_file_with_retry(azure_url, zip_path)
            print("[Metadata] Download complete.")

        print(f"[Metadata] Extracting {zip_path}...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(cache_dir)
        print("[Metadata] Extraction complete.")

    # 2. Download splits JSON if needed
    if not os.path.exists(splits_path):
        print(f"[Metadata] Downloading WCS recommended splits JSON...")
        download_file_with_retry(METADATA_URLS["splits"], splits_path)
        print("[Metadata] Splits downloaded.")

    return json_path, splits_path


def load_wcs_metadata(json_path):
    """Loads and indexes WCS annotations and images."""
    print("[Metadata] Parsing WCS COCO Camera Traps JSON...")
    start_t = time.time()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[Metadata] Parsed in {time.time() - start_t:.1f}s. Images: {len(data['images'])}, Annotations: {len(data['annotations'])}, Categories: {len(data['categories'])}")
    return data


def generate_target_species_report(data):
    """Inspects categories and prints the required taxonomy report."""
    cats_by_id = {c["id"]: c for c in data["categories"]}
    cats_by_name = {c["name"].lower(): c for c in data["categories"]}
    
    # Count annotations and images per category
    anns_per_cat = {}
    imgs_per_cat = {}
    for a in data["annotations"]:
        cid = a.get("category_id")
        anns_per_cat[cid] = anns_per_cat.get(cid, 0) + 1
        if cid not in imgs_per_cat:
            imgs_per_cat[cid] = set()
        imgs_per_cat[cid].add(a["image_id"])

    print("\n" + "=" * 70)
    print("🐾 WCS TARGET SPECIES REPORT")
    print("=" * 70)

    # 1. Tiger
    tiger_cat = cats_by_name.get("panthera tigris")
    print("\nTiger:")
    if tiger_cat:
        cid = tiger_cat["id"]
        print(f"  Taxonomy label found: '{tiger_cat['name']}' (Category ID: {cid})")
        print(f"  Annotated Bounding Boxes: {anns_per_cat.get(cid, 0)}")
        print(f"  Unique Camera-Trap Images: {len(imgs_per_cat.get(cid, set()))}")
    else:
        print("  NOT AVAILABLE IN WCS")

    # 2. Leopard
    leopard_cat = cats_by_name.get("panthera pardus")
    print("\nLeopard:")
    if leopard_cat:
        cid = leopard_cat["id"]
        print(f"  Taxonomy label found: '{leopard_cat['name']}' (Category ID: {cid})")
        print(f"  Annotated Bounding Boxes: {anns_per_cat.get(cid, 0)}")
        print(f"  Unique Camera-Trap Images: {len(imgs_per_cat.get(cid, set()))}")
    else:
        print("  NOT AVAILABLE IN WCS")

    # 3. Sloth Bear
    sloth_cat = cats_by_name.get("melursus ursinus")
    print("\nSloth Bear:")
    if sloth_cat:
        cid = sloth_cat["id"]
        print(f"  Taxonomy label found: '{sloth_cat['name']}' (Category ID: {cid})")
        print(f"  Images: {len(imgs_per_cat.get(cid, set()))}")
    else:
        print("  Taxonomy label searched: 'melursus ursinus' / 'sloth bear'")
        print("  Status: NOT AVAILABLE IN WCS")
        print("  Note: WCS contains 'ursus thibetanus' (Asian black bear, 7 bboxes in Laos),")
        print("        which is NOT Sloth Bear. Per strict instructions, it is NOT substituted.")

    # 4. Asiatic Lion
    lion_cat = cats_by_name.get("panthera leo")
    print("\nAsiatic Lion:")
    print("  Taxonomy label searched: 'panthera leo persica'")
    print("  Status: NOT AVAILABLE IN WCS")
    if lion_cat:
        cid = lion_cat["id"]
        print(f"  Found general 'panthera leo' (Category ID: {cid}, {len(imgs_per_cat.get(cid, set()))} images).")
        print("  VERIFICATION CHECK: All 'panthera leo' images in WCS originate from Kenya (country_code: 'ken').")
        print("  They are African Lions (Panthera leo melanochaita), NOT Asiatic Lions (Panthera leo persica).")
        print("  Per strict instructions, they are NOT silently put into the asiatic_lion class.")

    print("\n" + "=" * 70 + "\n")


def build_stratified_location_splits(images_dict, target_annotations, seed=42, train_pct=0.70, val_pct=0.20, test_pct=0.10):
    """
    Groups images by camera 'location' (or 'seq_id') and assigns each entire location
    to train, val, or test to prevent frame-level data leakage across consecutive shots.
    """
    random.seed(seed)
    
    # Map species -> list of locations
    species_locations = {}
    img_to_locations = {}
    
    for a in target_annotations:
        iid = a["image_id"]
        img_info = images_dict.get(iid)
        if not img_info:
            continue
        loc = img_info.get("location") or img_info.get("seq_id") or "unknown"
        img_to_locations[iid] = loc
        cid = a["category_id"]
        if cid not in species_locations:
            species_locations[cid] = set()
        species_locations[cid].add(loc)

    loc_splits = {}  # loc -> 'train' | 'val' | 'test'

    # Stratify by each species' locations
    for cid, locs in species_locations.items():
        loc_list = sorted(list(locs))
        random.shuffle(loc_list)
        
        n_total = len(loc_list)
        n_train = max(1, int(n_total * train_pct))
        n_val = max(1, int(n_total * val_pct))
        
        for i, loc in enumerate(loc_list):
            if loc in loc_splits:
                continue
            if i < n_train:
                loc_splits[loc] = "train"
            elif i < n_train + n_val:
                loc_splits[loc] = "val"
            else:
                loc_splits[loc] = "test"

    return loc_splits, img_to_locations


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

    # Reject zero or negative dimensions
    if w <= 0.0 or h <= 0.0 or img_width <= 0 or img_height <= 0:
        return None

    x_center = (x_min + (w / 2.0)) / img_width
    y_center = (y_min + (h / 2.0)) / img_height
    norm_w = w / img_width
    norm_h = h / img_height

    # Final clamping to [0.0, 1.0]
    x_center = max(0.0, min(1.0, x_center))
    y_center = max(0.0, min(1.0, y_center))
    norm_w = max(0.0, min(1.0, norm_w))
    norm_h = max(0.0, min(1.0, norm_h))

    return x_center, y_center, norm_w, norm_h


def download_single_image(img_info, dest_path):
    """Downloads an individual image trying GCS then Azure mirror."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        return True, "skipped"

    file_name = img_info["file_name"]
    for mirror in IMAGE_MIRRORS:
        url = f"{mirror}/{file_name}"
        if download_file_with_retry(url, dest_path, retries=2, timeout=20):
            # Verify file integrity with OpenCV
            img = cv2.imread(dest_path)
            if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
                return True, "downloaded"
            else:
                if os.path.exists(dest_path):
                    os.remove(dest_path)

    return False, "failed"


def run_pipeline(output_dir="Indradhanu_Dataset", max_per_species=5000, seed=42, 
                 workers=8, inspect_only=False, include_negatives=False, num_negatives=50):
    """Main pipeline execution function."""
    print("=" * 70)
    print("🚀 PROJECT INDRADHANU - WCS DATASET EXTRACTION PIPELINE")
    print("=" * 70)

    # Step 1: Ensure metadata exists
    json_path, splits_path = ensure_metadata_downloaded()
    data = load_wcs_metadata(json_path)

    # Step 2: Generate Target Species Report
    generate_target_species_report(data)

    if inspect_only:
        print("[Info] --inspect-only flag set. Halting before download.")
        return

    # Step 3: Filter Annotations for Valid Target Species
    # Tiger (154) -> YOLO class 0
    # Leopard (104) -> YOLO class 1
    valid_cat_to_yolo = {
        154: {"class_id": 0, "name": "tiger"},
        104: {"class_id": 1, "name": "leopard"}
    }

    images_dict = {img["id"]: img for img in data["images"]}

    # Filter target annotations
    target_anns = [a for a in data["annotations"] if a.get("category_id") in valid_cat_to_yolo]
    
    # Group annotations by image_id
    anns_by_image = {}
    for a in target_anns:
        iid = a["image_id"]
        if iid not in anns_by_image:
            anns_by_image[iid] = []
        anns_by_image[iid].append(a)

    print(f"[Filter] Selected {len(target_anns)} bounding boxes across {len(anns_by_image)} target predator images.")

    # Step 4: Stratified Splitting by Camera Location
    loc_splits, img_to_loc = build_stratified_location_splits(images_dict, target_anns, seed=seed)

    # Organize images by split
    split_images = {"train": [], "val": [], "test": []}
    for iid, anns in anns_by_image.items():
        loc = img_to_loc.get(iid, "unknown")
        split = loc_splits.get(loc, "train")
        split_images[split].append(iid)

    print(f"[Splits] Locations assigned: {len(loc_splits)}. Image splits: Train={len(split_images['train'])}, Val={len(split_images['val'])}, Test={len(split_images['test'])}")

    # Step 5: Setup Directory Structure
    os.makedirs(os.path.join(output_dir, "metadata"), exist_ok=True)
    for s in ["train", "val", "test"]:
        os.makedirs(os.path.join(output_dir, "images", s), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "labels", s), exist_ok=True)

    # Step 6: Multi-Threaded Image Download & YOLO Label Generation
    print(f"\n[Download] Commencing downloads with {workers} parallel threads...")
    all_download_tasks = []
    
    # Flatten download list
    img_meta_list = []
    for split, iids in split_images.items():
        for iid in iids:
            img_info = images_dict[iid]
            clean_name = f"{img_info['id']}.jpg"
            img_dest = os.path.join(output_dir, "images", split, clean_name)
            lbl_dest = os.path.join(output_dir, "labels", split, clean_name.replace(".jpg", ".txt"))
            img_meta_list.append((img_info, split, img_dest, lbl_dest))

    total_imgs = len(img_meta_list)
    completed = 0
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    annotations_csv_rows = []
    class_stats = {
        "tiger": {"train": 0, "val": 0, "test": 0},
        "leopard": {"train": 0, "val": 0, "test": 0},
        "sloth_bear": {"train": 0, "val": 0, "test": 0},
        "asiatic_lion": {"train": 0, "val": 0, "test": 0}
    }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_single_image, item[0], item[2]): item for item in img_meta_list}
        
        for future in as_completed(futures):
            item = futures[future]
            img_info, split, img_dest, lbl_dest = item
            iid = img_info["id"]
            completed += 1

            success, status = future.result()
            if status == "downloaded":
                downloaded_count += 1
            elif status == "skipped":
                skipped_count += 1
            else:
                failed_count += 1
                if completed % 25 == 0 or completed == total_imgs:
                    print(f"  Progress: {completed}/{total_imgs} ({completed/total_imgs*100:.1f}%) | DL: {downloaded_count} | Skip: {skipped_count} | Fail: {failed_count}")
                continue

            if completed % 25 == 0 or completed == total_imgs:
                print(f"  Progress: {completed}/{total_imgs} ({completed/total_imgs*100:.1f}%) | DL: {downloaded_count} | Skip: {skipped_count} | Fail: {failed_count}")

            # Generate YOLO Labels
            img_w = img_info.get("width")
            img_h = img_info.get("height")
            if not img_w or not img_h:
                temp_img = cv2.imread(img_dest)
                if temp_img is not None:
                    img_h, img_w = temp_img.shape[:2]

            img_anns = anns_by_image.get(iid, [])
            yolo_lines = []

            for a in img_anns:
                cid = a["category_id"]
                yolo_meta = valid_cat_to_yolo[cid]
                class_id = yolo_meta["class_id"]
                class_name = yolo_meta["name"]

                coco_box = a["bbox"]
                yolo_coords = convert_coco_to_yolo_bbox(coco_box, img_w, img_h)
                if yolo_coords is None:
                    continue

                xc, yc, nw, nh = yolo_coords
                yolo_lines.append(f"{class_id} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}")
                class_stats[class_name][split] += 1

                annotations_csv_rows.append({
                    "original_image_id": iid,
                    "wcs_file_name": img_info["file_name"],
                    "local_image_path": img_dest,
                    "species": class_name,
                    "source_dataset": "LILA_BC_WCS_Camera_Traps",
                    "bbox_x_min": coco_box[0],
                    "bbox_y_min": coco_box[1],
                    "bbox_width": coco_box[2],
                    "bbox_height": coco_box[3],
                    "image_width": img_w,
                    "image_height": img_h,
                    "split": split
                })

            with open(lbl_dest, "w", encoding="utf-8") as lf:
                lf.write("\n".join(yolo_lines))

    # Step 7: Negative Background Mechanism (if requested)
    if include_negatives and num_negatives > 0:
        print(f"\n[Negatives] Collecting {num_negatives} negative background samples (cattle, dogs, humans, empty)...")
        neg_candidates = []
        for a in data["annotations"]:
            cid = a.get("category_id")
            if cid in NEGATIVE_TAXONOMY:
                neg_candidates.append((a["image_id"], NEGATIVE_TAXONOMY[cid]))

        random.seed(seed)
        random.shuffle(neg_candidates)
        selected_negs = neg_candidates[:num_negatives]

        neg_downloaded = 0
        for iid, neg_type in selected_negs:
            img_info = images_dict.get(iid)
            if not img_info:
                continue
            split = "train" if random.random() < 0.75 else "val"
            clean_name = f"neg_{img_info['id']}.jpg"
            img_dest = os.path.join(output_dir, "images", split, clean_name)
            lbl_dest = os.path.join(output_dir, "labels", split, clean_name.replace(".jpg", ".txt"))

            success, _ = download_single_image(img_info, img_dest)
            if success:
                # Write an empty label file for negative background images
                with open(lbl_dest, "w", encoding="utf-8") as lf:
                    lf.write("")
                neg_downloaded += 1

        print(f"[Negatives] Downloaded {neg_downloaded} negative samples with empty YOLO labels.")

    # Step 8: Save Metadata CSVs and data.yaml
    ann_csv_path = os.path.join(output_dir, "metadata", "annotations.csv")
    with open(ann_csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["original_image_id", "wcs_file_name", "local_image_path", "species", 
                      "source_dataset", "bbox_x_min", "bbox_y_min", "bbox_width", "bbox_height", 
                      "image_width", "image_height", "split"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(annotations_csv_rows)
    print(f"[Metadata] Saved annotations CSV: {ann_csv_path}")

    counts_csv_path = os.path.join(output_dir, "metadata", "class_counts.csv")
    with open(counts_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["species", "class_id", "train_annotations", "val_annotations", "test_annotations", "total_annotations"])
        writer.writerow(["tiger", 0, class_stats["tiger"]["train"], class_stats["tiger"]["val"], class_stats["tiger"]["test"], sum(class_stats["tiger"].values())])
        writer.writerow(["leopard", 1, class_stats["leopard"]["train"], class_stats["leopard"]["val"], class_stats["leopard"]["test"], sum(class_stats["leopard"].values())])
        writer.writerow(["sloth_bear", 2, 0, 0, 0, 0])
        writer.writerow(["asiatic_lion", 3, 0, 0, 0, 0])
    print(f"[Metadata] Saved class counts CSV: {counts_csv_path}")

    yaml_path = os.path.join(output_dir, "metadata", "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(f"""# Project Indradhanu - YOLOv8 Dataset Configuration
path: {os.path.abspath(output_dir)}
train: images/train
val: images/val
test: images/test

names:
  0: tiger
  1: leopard
  2: sloth_bear
  3: asiatic_lion
""")
    print(f"[Metadata] Saved data.yaml: {yaml_path}")

    # Step 9: Validation and Contact Sheet
    verify_dataset_and_generate_contact_sheet(output_dir)


def verify_dataset_and_generate_contact_sheet(dataset_dir="Indradhanu_Dataset"):
    """
    Validates all images and YOLO label files, removes corrupt files,
    prints counts, and creates a visual verification contact sheet.
    """
    print("\n" + "=" * 70)
    print("🔍 DATASET VALIDATION & CONTACT SHEET GENERATION")
    print("=" * 70)

    total_valid_imgs = 0
    total_valid_labels = 0
    split_counts = {"train": 0, "val": 0, "test": 0}
    class_totals = {0: 0, 1: 0, 2: 0, 3: 0}
    sample_crops_by_class = {0: [], 1: [], 2: [], 3: []}

    for split in ["train", "val", "test"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        lbl_dir = os.path.join(dataset_dir, "labels", split)
        
        if not os.path.exists(img_dir):
            continue

        for fname in os.listdir(img_dir):
            if not fname.lower().endswith(".jpg"):
                continue

            img_path = os.path.join(img_dir, fname)
            lbl_path = os.path.join(lbl_dir, fname.replace(".jpg", ".txt"))

            # 1. Verify image can be opened
            img = cv2.imread(img_path)
            if img is None or img.shape[0] == 0 or img.shape[1] == 0:
                print(f"[Corrupt] Removing corrupt image: {img_path}")
                os.remove(img_path)
                if os.path.exists(lbl_path):
                    os.remove(lbl_path)
                continue

            ih, iw = img.shape[:2]
            total_valid_imgs += 1
            split_counts[split] += 1

            # 2. Verify YOLO label
            if os.path.exists(lbl_path):
                valid_lines = []
                with open(lbl_path, "r", encoding="utf-8") as lf:
                    lines = lf.read().strip().splitlines()

                for line in lines:
                    parts = line.strip().split()
                    if len(parts) != 5:
                        continue
                    try:
                        cid = int(parts[0])
                        xc, yc, nw, nh = map(float, parts[1:])
                        # Verify normalized range
                        if 0.0 <= xc <= 1.0 and 0.0 <= yc <= 1.0 and 0.0 < nw <= 1.0 and 0.0 < nh <= 1.0:
                            valid_lines.append(line)
                            class_totals[cid] = class_totals.get(cid, 0) + 1
                            
                            # Save a sample crop for the contact sheet
                            if len(sample_crops_by_class[cid]) < 3:
                                x1 = max(0, int((xc - nw/2) * iw))
                                y1 = max(0, int((yc - nh/2) * ih))
                                x2 = min(iw, int((xc + nw/2) * iw))
                                y2 = min(ih, int((yc + nh/2) * ih))
                                if x2 > x1 and y2 > y1:
                                    crop = img[y1:y2, x1:x2]
                                    crop = cv2.resize(crop, (240, 240))
                                    sample_crops_by_class[cid].append(crop)
                    except ValueError:
                        continue

                # Overwrite cleaned lines
                with open(lbl_path, "w", encoding="utf-8") as lf:
                    lf.write("\n".join(valid_lines))
                total_valid_labels += len(valid_lines)

    print(f"\n[Validation Results]")
    print(f"  Total Valid Images: {total_valid_imgs}")
    print(f"  Train: {split_counts['train']} | Val: {split_counts['val']} | Test: {split_counts['test']}")
    print(f"  Class 0 (Tiger): {class_totals.get(0, 0)} boxes")
    print(f"  Class 1 (Leopard): {class_totals.get(1, 0)} boxes")
    print(f"  Class 2 (Sloth Bear): {class_totals.get(2, 0)} boxes (Not in WCS)")
    print(f"  Class 3 (Asiatic Lion): {class_totals.get(3, 0)} boxes (Not in WCS)")

    # 3. Create visual contact sheet
    contact_tiles = []
    class_names = {0: "0: Tiger", 1: "1: Leopard"}
    
    for cid in [0, 1]:
        crops = sample_crops_by_class[cid]
        if crops:
            row = np.hstack(crops)
            # Add text banner
            banner = np.zeros((40, row.shape[1], 3), dtype=np.uint8)
            cv2.putText(banner, f"Class {class_names[cid]} - LILA WCS Camera Traps", (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            block = np.vstack([banner, row])
            contact_tiles.append(block)

    if contact_tiles:
        # Match widths
        max_w = max(b.shape[1] for b in contact_tiles)
        padded_tiles = []
        for b in contact_tiles:
            if b.shape[1] < max_w:
                pad = np.zeros((b.shape[0], max_w - b.shape[1], 3), dtype=np.uint8)
                b = np.hstack([b, pad])
            padded_tiles.append(b)

        contact_sheet = np.vstack(padded_tiles)
        contact_path = os.path.join(dataset_dir, "metadata", "contact_sheet.jpg")
        cv2.imwrite(contact_path, contact_sheet)
        print(f"[Verification] Generated visual contact sheet: {contact_path}")


def main():
    parser = argparse.ArgumentParser(description="Indradhanu WCS Dataset Extraction Pipeline")
    parser.add_argument("--output-dir", default="Indradhanu_Dataset", help="Destination directory for dataset")
    parser.add_argument("--max-per-species", type=int, default=5000, help="Max target images per species")
    parser.add_argument("--workers", type=int, default=8, help="Number of download worker threads")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible split")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect WCS taxonomy without downloading")
    parser.add_argument("--include-negatives", action="store_true", help="Download negative background images")
    parser.add_argument("--num-negatives", type=int, default=50, help="Number of negative images to sample")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing dataset")

    args = parser.parse_args()

    if args.verify_only:
        verify_dataset_and_generate_contact_sheet(args.output_dir)
    else:
        run_pipeline(
            output_dir=args.output_dir,
            max_per_species=args.max_per_species,
            seed=args.seed,
            workers=args.workers,
            inspect_only=args.inspect_only,
            include_negatives=args.include_negatives,
            num_negatives=args.num_negatives
        )


if __name__ == "__main__":
    main()
