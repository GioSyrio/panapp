#!/usr/bin/env python3
"""
Scrape data from https://trapeza.iep.edu.gr - Subject 218
(Πληροφορική, Γ' ΤΑΞΗ, Γενικό Λύκειο)

Usage: python3 trapeza_scraper.py [type_id] [class_id] [subject_id]
       python3 trapeza_scraper.py 1 3 218
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Default values matching the URL: /grades/1/classes/3/subjects/218
TYPE_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
CLASS_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 3
SUBJECT_ID = int(sys.argv[3]) if len(sys.argv) > 3 else 218

API_BASE = "https://api.trapeza.registry.digitalschool.gov.gr/v1"
FILES_BASE = "https://trapeza1.iep.edu.gr/files/trapezafiles"
OUTPUT_DIR = f"trapeza_data_{TYPE_ID}_{CLASS_ID}_{SUBJECT_ID}"

os.makedirs(f"{OUTPUT_DIR}/attachments", exist_ok=True)

def fetch_json(url):
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def download_file(url, dest):
    """Download a file; returns (success, http_code)."""
    if os.path.exists(dest):
        return True, 200
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(dest, 'wb') as f:
                f.write(resp.read())
            return True, resp.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception as e:
        return False, str(e)

def find_subject_in_tree(tree_data, type_id, class_id, subject_id):
    """Extract subject metadata from tree."""
    for st in tree_data.get("school_types", []):
        if st["id"] == type_id:
            school_type_name = st["name"]
            for cl in st.get("classes", []):
                if cl["id"] == class_id:
                    class_name = cl["name"]
                    for lesson in cl.get("lessons", []):
                        if lesson["id"] == subject_id:
                            return {
                                "school_type": {"id": type_id, "name": school_type_name},
                                "class": {"id": class_id, "name": class_name},
                                "subject": {
                                    "id": subject_id,
                                    "name": lesson["name"],
                                    "subject_types": lesson.get("subject_types", []),
                                    "material": lesson.get("material", []),
                                    "allsubjects_file_title": lesson.get("allsubjects_file_title"),
                                    "criteria_file_title": lesson.get("criteria_file_title"),
                                    "eppe": lesson.get("eppe")
                                }
                            }
    return None

print("=" * 60)
print(f"Trapeza Scraper - Subject {SUBJECT_ID}")
print("=" * 60)

# Step 1: Fetch tree metadata
print("\n[1/3] Fetching school tree metadata...")
tree_file = f"{OUTPUT_DIR}/tree_data.json"
if not os.path.exists(tree_file):
    tree_data = fetch_json(f"{API_BASE}/public/school/type/tree")
    with open(tree_file, 'w', encoding='utf-8') as f:
        json.dump(tree_data, f, ensure_ascii=False, indent=2)
else:
    with open(tree_file, 'r', encoding='utf-8') as f:
        tree_data = json.load(f)

meta = find_subject_in_tree(tree_data, TYPE_ID, CLASS_ID, SUBJECT_ID)
if meta:
    print(f"  School Type: {meta['school_type']['name']}")
    print(f"  Class:       {meta['class']['name']}")
    print(f"  Subject:     {meta['subject']['name']}")
else:
    print(f"  WARNING: Subject {SUBJECT_ID} not found in tree!")
    meta = {
        "school_type": {"id": TYPE_ID, "name": "Unknown"},
        "class": {"id": CLASS_ID, "name": "Unknown"},
        "subject": {"id": SUBJECT_ID, "name": "Unknown",
                     "subject_types": [], "material": [],
                     "allsubjects_file_title": None,
                     "criteria_file_title": None, "eppe": None}
    }

# Step 2: Fetch items
print("\n[2/3] Fetching items...")
items_url = f"{API_BASE}/public/school/type/{TYPE_ID}/class/{CLASS_ID}/subject/{SUBJECT_ID}/items"
items_data = fetch_json(items_url)
items_raw_file = f"{OUTPUT_DIR}/items_raw.json"
with open(items_raw_file, 'w', encoding='utf-8') as f:
    json.dump(items_data, f, ensure_ascii=False, indent=2)

total_items = len(items_data["items"])
print(f"  {total_items} items fetched")

# Step 3: Build structured JSON and download files
print("\n[3/3] Building structured JSON and downloading attachments...")

output = {
    "source_url": f"https://trapeza.iep.edu.gr/grades/{TYPE_ID}/classes/{CLASS_ID}/subjects/{SUBJECT_ID}",
    "api_items_url": items_url,
    "api_tree_url": f"{API_BASE}/public/school/type/tree",
    "scraped_at": datetime.now(timezone.utc).isoformat(),
    "metadata": meta,
    "bulk_downloads": {
        "zip_all": f"{FILES_BASE}/ZIP/{TYPE_ID}_{CLASS_ID}_{SUBJECT_ID}.zip",
        "all_subjects_pdf": f"{FILES_BASE}/{TYPE_ID}_{CLASS_ID}_{SUBJECT_ID}_ALLSUBJECTS.pdf",
        "criteria_pdf": f"{FILES_BASE}/{TYPE_ID}_{CLASS_ID}_{SUBJECT_ID}_CRITERIA.pdf"
    },
    "total_items": total_items,
    "items": []
}

# Build items list
for item in items_data["items"]:
    resources_out = []
    for res in item.get("resources", []):
        fname = res.get("fileName", "")
        # Fix: API says format=doc but fileName is fake — real files use {id}-0.doc / {id}-4.doc
        corrected_fname = fname
        corrected_url = f"{FILES_BASE}/{fname}"
        if res.get("format") == "doc":
            item_id = item["id"]
            if "SOLUTIONDOC" in fname or "SOLUTION" in fname:
                corrected_fname = f"{item_id}-4.doc"
            else:
                corrected_fname = f"{item_id}-0.doc"
            corrected_url = f"{FILES_BASE}/{corrected_fname}"
        resources_out.append({
            "kind": res.get("kind", ""),
            "format": res.get("format", ""),
            "file_name": corrected_fname,
            "download_url": corrected_url if fname else ""
        })

    output["items"].append({
        "id": item["id"],
        "title": item.get("title"),
        "date": item.get("date"),
        "duration_min": item.get("durationMin"),
        "difficulty": item.get("difficulty"),
        "keywords": item.get("keywords", ""),
        "remarks": item.get("remarks", ""),
        "question": item.get("question"),
        "organization": item.get("organization", ""),
        "pma": item.get("pma", []),
        "material": item.get("material", []),
        "learning_outcomes": item.get("learning_outcomes", []),
        "resources": resources_out
    })

# Download bulk files
print("\n  Downloading bulk files...")
bulk_results = []
for name, url in output["bulk_downloads"].items():
    dest = f"{OUTPUT_DIR}/attachments/{os.path.basename(url)}"
    ok, code = download_file(url, dest)
    if ok:
        size = os.path.getsize(dest)
        print(f"    [OK] {name} ({size:,} bytes)")
        bulk_results.append({"file": name, "status": "downloaded", "size": size})
    else:
        print(f"    [SKIP] {name} (HTTP {code})")
        bulk_results.append({"file": name, "status": f"unavailable ({code})"})
output["bulk_download_results"] = bulk_results

# Download individual attachments
print("\n  Downloading individual attachments (may require authentication)...")
all_filenames = set()
for item in items_data["items"]:
    for res in item.get("resources", []):
        fname = res.get("fileName", "")
        if fname:
            all_filenames.add(fname)

downloaded = 0
failed = 0
for fname in sorted(all_filenames):
    url = f"{FILES_BASE}/{fname}"
    dest = f"{OUTPUT_DIR}/attachments/{fname}"
    ok, code = download_file(url, dest)
    if ok:
        downloaded += 1
        if downloaded % 20 == 0:
            print(f"    Downloaded {downloaded}/{len(all_filenames)}...")
    else:
        failed += 1
        if failed <= 5:
            print(f"    [FAIL] {fname} (HTTP {code})")

print(f"    Done: {downloaded} downloaded, {failed} failed, {len(all_filenames)} total")
output["attachments_downloaded"] = downloaded
output["attachments_failed"] = failed
output["attachments_total"] = len(all_filenames)

# Save final structured JSON
data_file = f"{OUTPUT_DIR}/data.json"
with open(data_file, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  Final structured JSON saved -> {data_file}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Output directory: {OUTPUT_DIR}/")
print(f"  data.json          - structured JSON with all metadata")
print(f"  items_raw.json     - raw API response")
print(f"  tree_data.json     - school tree from API")
print(f"  attachments/       - downloaded files")
print(f"\nFiles in output directory:")
for f in sorted(os.listdir(OUTPUT_DIR)):
    path = os.path.join(OUTPUT_DIR, f)
    if os.path.isfile(path):
        print(f"  {f} ({os.path.getsize(path):,} bytes)")
    else:
        count = len(os.listdir(path))
        print(f"  {f}/ ({count} files)")

# If ZIP was downloaded, extract it
zip_path = f"{OUTPUT_DIR}/attachments/{TYPE_ID}_{CLASS_ID}_{SUBJECT_ID}.zip"
if os.path.exists(zip_path):
    import zipfile
    print(f"\n  Extracting bulk ZIP ({os.path.getsize(zip_path):,} bytes)...")
    extract_dir = f"{OUTPUT_DIR}/attachments/extracted"
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)
    extracted_count = len(os.listdir(extract_dir))
    print(f"    Extracted {extracted_count} files to attachments/extracted/")

print("\nDone!")