#!/usr/bin/env python3
"""
Download DOC files from subjects.draw.iep.edu.gr — NO authentication needed.

URL pattern: https://subjects.draw.iep.edu.gr/{qid}-3?unique_identifier={qid}&file_type=0
  file_type=0 → question DOCX
  file_type=4 → answer DOCX

Files saved to: data/trapeza_data_1_3_218/attachments/docx/

Usage:
    python3 download_doc_files.py                          # diagram questions only
    python3 download_doc_files.py --all                    # all 155 questions
    python3 download_doc_files.py --id 25938               # single question
"""

import json
import os
import sys
import argparse
import time
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "trapeza_data_1_3_218")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions_classified.json")
DOC_DIR = os.path.join(DATA_DIR, "attachments", "docx")
DRAW_BASE = "https://subjects.draw.iep.edu.gr"

PRIORITY_IDS = {25938, 29219, 34676, 35762}


def load_questions():
    if not os.path.exists(QUESTIONS_FILE):
        print(f"ERROR: {QUESTIONS_FILE} not found.")
        return []
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def download_doc(qid, file_type, label, headers):
    """Download single DOC file. Returns (success, size)."""
    dest = os.path.join(DOC_DIR, f"{qid}-{file_type}.doc")
    if os.path.exists(dest) and os.path.getsize(dest) > 500:
        return "skip", os.path.getsize(dest)

    url = f"{DRAW_BASE}/{qid}-3?unique_identifier={qid}&file_type={file_type}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()
            if len(content) > 500:
                os.makedirs(DOC_DIR, exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(content)
                return "ok", len(content)
            return "empty", len(content)
    except urllib.error.HTTPError as e:
        return "http_err", e.code
    except Exception as e:
        return "err", str(e)[:60]


def main():
    parser = argparse.ArgumentParser(description="Download DOC files from trapeza")
    parser.add_argument("--all", action="store_true", help="Download ALL questions")
    parser.add_argument("--id", type=int, default=0, help="Download single question by ID")
    args = parser.parse_args()

    questions = load_questions()
    if not questions:
        sys.exit(1)

    if args.id:
        target_ids = {args.id}
    elif args.all:
        target_ids = {q["id"] for q in questions}
    else:
        target_ids = PRIORITY_IDS

    target_ids = sorted(target_ids)

    print(f"📥 DOC Downloader ({len(target_ids)} questions)")
    print(f"   Destination: {DOC_DIR}")
    print(f"   Endpoint: {DRAW_BASE}/{{qid}}-3")
    print()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/msword, */*",
    }

    ok = 0
    failed = 0
    skipped = 0

    for qid in target_ids:
        for ft, label in [(0, "Q"), (4, "A")]:
            fname = f"{qid}-{ft}.doc"
            dest = os.path.join(DOC_DIR, fname)

            if os.path.exists(dest) and os.path.getsize(dest) > 500:
                skipped += 1
                if skipped % 40 == 1:
                    print(f"   [skipping {skipped} existing files...]")
                continue

            sys.stdout.write(f"  Q{qid} ({label}): ")
            sys.stdout.flush()

            result, info = download_doc(qid, ft, label, headers)
            if result == "ok":
                print(f"✅ {info:,} bytes")
                ok += 1
            elif result == "skip":
                skipped += 1
                print(f"⏭️  already exists ({info:,} bytes)")
            elif result == "http_err":
                print(f"❌ HTTP {info}")
                failed += 1
            else:
                print(f"❌ {info}")
                failed += 1

            time.sleep(0.2)  # polite delay

    total = ok + failed + skipped
    print(f"\n{'='*60}")
    print(f"Results: {ok} downloaded, {failed} failed, {skipped} skipped")
    print(f"Files saved to: {DOC_DIR}/")
    if ok > 0:
        print(f"\nNext: python3 extract_doc_diagrams.py")


if __name__ == "__main__":
    main()