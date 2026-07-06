#!/usr/bin/env python3
"""
download_docs_all.py — Download DOC files for ALL 10 new subjects

Uses the draw.iep.edu.gr endpoint (same as successful math download):
  https://subjects.draw.iep.edu.gr/{qid}-3?unique_identifier={qid}&file_type=0  (question)
  https://subjects.draw.iep.edu.gr/{qid}-3?unique_identifier={qid}&file_type=4  (answer)

Protected subjects (math + informatics) skipped permanently.

Usage:
    python3 download_docs_all.py --slug fysiki_prosanatolismoy
    python3 download_docs_all.py --all
    python3 download_docs_all.py --all --limit 5    # test first 5
"""

import json, os, sys, time, argparse, urllib.request, urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE_DIR, "data", "subjects")
DRAW_BASE = "https://subjects.draw.iep.edu.gr"
PROTECTED = {"mathematics", "informatics", "mathimatika_prosanatolismoy", "pliroforiki"}


def download_one(qid, file_type, dest_dir):
    """Download single DOC file. Returns (status, info)."""
    fname = f"{qid}-{file_type}.doc"
    dest = os.path.join(dest_dir, fname)

    if os.path.exists(dest) and os.path.getsize(dest) > 500:
        return "skip", os.path.getsize(dest)

    url = f"{DRAW_BASE}/{qid}-3?unique_identifier={qid}&file_type={file_type}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/msword, */*",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()
            if len(content) > 500:
                os.makedirs(dest_dir, exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(content)
                return "ok", len(content)
            return "empty", len(content)
    except urllib.error.HTTPError as e:
        return "http_err", e.code
    except Exception as e:
        return "err", str(e)[:60]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slug", help="Subject slug")
    p.add_argument("--all", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    targets = []
    if a.all:
        for slug in os.listdir(DATA_ROOT):
            if slug in PROTECTED or slug.startswith('.'):
                continue
            ip = os.path.join(DATA_ROOT, slug, "items_raw.json")
            if os.path.exists(ip):
                targets.append(slug)
        print(f"📚 {len(targets)} subjects")
    elif a.slug:
        targets = [a.slug]
    else:
        p.print_help()
        return

    total_ok, total_skip, total_fail = 0, 0, 0

    for slug in targets:
        ip = os.path.join(DATA_ROOT, slug, "items_raw.json")
        doc_dir = os.path.join(DATA_ROOT, slug, "raw", "docx")

        with open(ip, encoding="utf-8") as f:
            items = json.load(f)

        if a.limit > 0:
            items = items[:a.limit]

        print(f"\n📄 {slug} ({len(items)} questions)")
        ok, skip, fail = 0, 0, 0

        for i, item in enumerate(items):
            qid = item["id"]
            for ft, label in [(0, "Q"), (4, "A")]:
                status, info = download_one(qid, ft, doc_dir)
                if status == "ok":
                    ok += 1
                elif status == "skip":
                    skip += 1
                else:
                    fail += 1

            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(items)}] {ok} new, {skip} skip, {fail} fail")
            time.sleep(0.1)  # polite

        print(f"  ✅ {ok} downloaded, {skip} existed, {fail} failed")
        total_ok += ok
        total_skip += skip
        total_fail += fail

    print(f"\n{'='*60}")
    print(f"Total: {total_ok} downloaded, {total_skip} existed, {total_fail} failed")
    print(f"Files in: {DATA_ROOT}/{{slug}}/raw/docx/")

if __name__ == "__main__":
    main()