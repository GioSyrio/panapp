#!/usr/bin/env python3
"""
download_docs.py — Download DOC files for all 10 new subjects

Uses the corrected filename mapping from trapeza_scraper:
  - Question: {qid}-0.doc
  - Solution: {qid}-4.doc

Protected subjects (math + informatics) are skipped permanently.

Usage:
    python3 download_docs.py --slug fysiki_prosanatolismoy
    python3 download_docs.py --all
    python3 download_docs.py --all --limit 5    # test with first 5 questions
"""

import json, os, sys, time, argparse, urllib.request, urllib.error

FILES_BASE = "https://trapeza1.iep.edu.gr/files/trapezafiles"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROTECTED = {"mathematics", "informatics", "mathimatika_prosanatolismoy", "pliroforiki"}

def download(url, dest):
    if os.path.exists(dest):
        return True, "exists"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(dest, 'wb') as f:
                f.write(r.read())
        return True, "ok"
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception as e:
        return False, str(e)[:50]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slug", help="Subject slug")
    p.add_argument("--all", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Limit questions")
    a = p.parse_args()

    data_root = os.path.join(BASE_DIR, "data", "subjects")
    targets = []

    if a.all:
        for slug in os.listdir(data_root):
            if slug in PROTECTED or slug.startswith('.'):
                continue
            items_path = os.path.join(data_root, slug, "items_raw.json")
            if os.path.exists(items_path):
                targets.append(slug)
        print(f"📚 {len(targets)} subjects")
    elif a.slug:
        targets = [a.slug]
    else:
        p.print_help()
        return

    total = 0
    for slug in targets:
        items_path = os.path.join(data_root, slug, "items_raw.json")
        doc_dir = os.path.join(data_root, slug, "raw", "docx")
        os.makedirs(doc_dir, exist_ok=True)

        with open(items_path, encoding="utf-8") as f:
            items = json.load(f)

        if a.limit > 0:
            items = items[:a.limit]

        print(f"\n📄 {slug} ({len(items)} questions)")
        ok_count, skip_count, fail_count = 0, 0, 0

        for item in items:
            qid = item["id"]
            for suffix, label in [("0", "question"), ("4", "solution")]:
                fname = f"{qid}-{suffix}.doc"
                url = f"{FILES_BASE}/{fname}"
                dest = os.path.join(doc_dir, fname)
                ok, status = download(url, dest)
                if status == "ok":
                    ok_count += 1
                elif status == "exists":
                    skip_count += 1
                else:
                    fail_count += 1
            if (ok_count + skip_count + fail_count) % 20 == 0:
                print(f"  {ok_count} downloaded, {skip_count} skipped, {fail_count} failed")

        total += ok_count
        print(f"  ✅ {ok_count} new, {skip_count} existed, {fail_count} failed")

    print(f"\n✅ Total: {total} new DOC files downloaded")

if __name__ == "__main__":
    main()