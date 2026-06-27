#!/usr/bin/env python3
"""
scrape_subject.py — Modular scraper for one trapeza subject

Downloads all questions, PDFs, and DOC files for a single trapeza subject.
Runs independently of the Flask app — can be executed in parallel.

Usage:
    python3 scrape_subject.py --id 217              # scrape by subject ID
    python3 scrape_subject.py --slug physics        # scrape by slug (from manifest)
    python3 scrape_subject.py --all                 # scrape ALL pending subjects
    python3 scrape_subject.py --id 217 --limit 5    # test with first 5 questions
    python3 scrape_subject.py --id 217 --dry-run    # preview only

Creates:
    data/subjects/{slug}/
        items_raw.json       — all question items
        tree_data.json       — subject metadata
        raw/
            pdfs/            — question + solution PDFs
            docx/            — DOCX documents (if available)
"""

import json, os, sys, time, argparse, urllib.request, urllib.error
from datetime import datetime

API_BASE = "https://api.trapeza.registry.digitalschool.gov.gr/v1"
FILES_BASE = "https://trapeza1.iep.edu.gr/files/trapezafiles"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Greek → ASCII slug mapping ──────────────────────────────────────────────
SLUG_MAP = {
    'α': 'a', 'β': 'b', 'γ': 'g', 'δ': 'd', 'ε': 'e', 'ζ': 'z',
    'η': 'i', 'θ': 'th', 'ι': 'i', 'κ': 'k', 'λ': 'l', 'μ': 'm',
    'ν': 'n', 'ξ': 'x', 'ο': 'o', 'π': 'p', 'ρ': 'r', 'σ': 's',
    'τ': 't', 'υ': 'y', 'φ': 'f', 'χ': 'ch', 'ψ': 'ps', 'ω': 'o',
    'ά': 'a', 'έ': 'e', 'ή': 'i', 'ί': 'i', 'ό': 'o', 'ύ': 'y', 'ώ': 'o',
    'ς': 's', ' ': '_', 'Α': 'a', 'Β': 'b', 'Γ': 'g', 'Δ': 'd',
    'Ε': 'e', 'Ζ': 'z', 'Η': 'i', 'Θ': 'th', 'Ι': 'i', 'Κ': 'k',
    'Λ': 'l', 'Μ': 'm', 'Ν': 'n', 'Ξ': 'x', 'Ο': 'o', 'Π': 'p',
    'Ρ': 'r', 'Σ': 's', 'Τ': 't', 'Υ': 'y', 'Φ': 'f', 'Χ': 'ch',
    'Ψ': 'ps', 'Ω': 'o',
}

def slugify(name):
    slug = ''.join(SLUG_MAP.get(c, c) for c in name.lower())
    slug = ''.join(c if c.isalnum() or c == '_' else '_' for c in slug)
    return slug.strip('_') or 'unknown'

# ── HTTP helpers ─────────────────────────────────────────────────────────────
def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def download_file(url, dest):
    if os.path.exists(dest):
        return True, 200
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(dest, 'wb') as f:
                f.write(resp.read())
            return True, resp.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception as e:
        return False, str(e)

# ── Local tree cache ──────────────────────────────────────────────────────────
_LOCAL_TREE_CACHE = None

def _load_local_tree():
    """Load tree data from cached files (avoids 403 on repeated API calls)."""
    global _LOCAL_TREE_CACHE
    if _LOCAL_TREE_CACHE is not None:
        return _LOCAL_TREE_CACHE
    # Try multiple cache locations
    candidates = [
        os.path.join(BASE_DIR, "data/subjects/mathematics/tree_data.json"),
        os.path.join(BASE_DIR, "data/subjects/informatics/tree_data.json"),
        os.path.join(BASE_DIR, "data/trapeza_data_1_3_218/tree_data.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _LOCAL_TREE_CACHE = json.load(f)
            return _LOCAL_TREE_CACHE
    return None

# ── Subject discovery ────────────────────────────────────────────────────────
def find_subject_by_id(subject_id):
    """Find subject metadata from local tree cache (no API call)."""
    tree = _load_local_tree()
    if tree:
        for st in tree.get("school_types", []):
            if st["id"] != 1: continue
            for cl in st.get("classes", []):
                if cl["id"] != 3: continue
                for lesson in cl.get("lessons", []):
                    if lesson["id"] == subject_id:
                        return {
                            "id": lesson["id"],
                            "name": lesson["name"],
                            "slug": slugify(lesson["name"]),
                            "subject_types": lesson.get("subject_types", []),
                        }
    return None

def find_subject_by_slug(slug):
    """Find subject ID by slug from local tree cache."""
    tree = _load_local_tree()
    if tree:
        for st in tree.get("school_types", []):
            if st["id"] != 1: continue
            for cl in st.get("classes", []):
                if cl["id"] != 3: continue
                for lesson in cl.get("lessons", []):
                    if slugify(lesson["name"]) == slug:
                        return {
                            "id": lesson["id"],
                            "name": lesson["name"],
                            "slug": slug,
                            "subject_types": lesson.get("subject_types", []),
                        }
    return None

def load_manifest():
    mp = os.path.join(BASE_DIR, "data", "subject_manifest.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            return json.load(f)
    return None

# ── Main scraper ─────────────────────────────────────────────────────────────
def scrape_subject(subject_id, limit=0, dry_run=False):
    """Scrape one subject by ID. Returns (success, stats)."""
    info = find_subject_by_id(subject_id)
    if not info:
        print(f"❌ Subject {subject_id} not found in tree")
        return False, {}

    slug = info["slug"]
    name = info["name"]
    data_dir = os.path.join(BASE_DIR, "data", "subjects", slug)
    raw_dir = os.path.join(data_dir, "raw")
    pdf_dir = os.path.join(raw_dir, "pdfs")
    doc_dir = os.path.join(raw_dir, "docx")

    print(f"\n{'='*60}")
    print(f"📚 Scraping: {name} (ID: {subject_id}, slug: {slug})")
    print(f"{'='*60}")

    if dry_run:
        print("  [DRY RUN] Would create directories and download data")
        return True, {"id": subject_id, "name": name, "slug": slug, "dry_run": True}

    # Create directories
    for d in [data_dir, raw_dir, pdf_dir, doc_dir]:
        os.makedirs(d, exist_ok=True)

    # Fetch questions via public API
    print(f"  📋 Fetching questions...")
    limit_param = f"?limit={limit}" if limit > 0 else ""
    url = f"{API_BASE}/public/school/type/1/class/3/subject/{subject_id}/items{limit_param}"
    items = fetch_json(url)

    if not items:
        print(f"  ❌ No items returned")
        return False, {}

    items_list = items if isinstance(items, list) else items.get("items", items.get("data", []))
    print(f"  ✅ Got {len(items_list)} questions")

    # Fetch tree data via public API
    tree = fetch_json(f"{API_BASE}/public/school/type/tree")

    # Save raw data
    items_path = os.path.join(data_dir, "items_raw.json")
    tree_path = os.path.join(data_dir, "tree_data.json")

    if not dry_run:
        with open(items_path, "w", encoding="utf-8") as f:
            json.dump(items_list, f, ensure_ascii=False, indent=2)
        with open(tree_path, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        print(f"  💾 Saved: items_raw.json, tree_data.json")

    # Download attachments (construct URLs from FILES_BASE + fileName)
    pdf_count = 0
    doc_count = 0
    skip_count = 0
    already_ok = 0

    if limit > 0:
        items_list = items_list[:limit]

    for i, item in enumerate(items_list):
        qid = item.get("id", i)
        resources = item.get("resources", [])

        for res in resources:
            fname = res.get("fileName", "")
            if not fname:
                continue

            # Construct download URL
            url = f"{FILES_BASE}/{fname}"

            if fname.endswith(".pdf"):
                dest = os.path.join(pdf_dir, fname)
                ok, code = download_file(url, dest)
                if ok:
                    if code == 200:
                        pdf_count += 1
                    else:
                        already_ok += 1
                else:
                    skip_count += 1
            elif fname.endswith(".docx") or fname.endswith(".doc"):
                dest = os.path.join(doc_dir, fname)
                ok, code = download_file(url, dest)
                if ok:
                    if code == 200:
                        doc_count += 1
                    else:
                        already_ok += 1
                else:
                    skip_count += 1

    print(f"  📥 Downloaded: {pdf_count} PDFs, {doc_count} DOCs (already had: {already_ok}, failed: {skip_count})")

    # Create boilerplate subject config
    config = {
        "id": slug,
        "name": name,
        "icon": "📚",
        "parts": ["Θέμα 2", "Θέμα 4"],
        "points_range": [10, 25],
        "exam_duration_minutes": 180,
        "prompt_file": f"prompts/{slug}.py",
        "track": "stem",
        "section_types": ["section_header", "sub_question", "points", "text", "diagram", "table"],
        "ui": {
            "app_title": "Πανελλαδικές AI Tutor",
            "header_subtitle": f"{name} • Θέματα",
            "input_placeholder": "Γράψε τη σκέψη σου ή ρώτα κάτι...",
            "start_title": "Έτοιμος για εξάσκηση;",
            "start_description": "Θέματα υψηλής πιθανότητας βασισμένα σε στατιστική ανάλυση.",
        },
        "data": {
            "data_dir": f"data/subjects/{slug}",
            "source_file": "items_raw.json",
        },
    }

    config_path = os.path.join(BASE_DIR, "subjects", f"{slug}.json")
    if not os.path.exists(config_path) and not dry_run:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"  ⚙️  Created subject config: subjects/{slug}.json")

    stats = {
        "id": subject_id, "name": name, "slug": slug,
        "questions": len(items_list),
        "pdfs": pdf_count, "docs": doc_count,
        "data_dir": data_dir,
    }

    # Update manifest if it exists
    manifest = load_manifest()
    if manifest:
        for s in manifest.get("subjects", []):
            if s["id"] == subject_id:
                s["status"] = "scraped"
                s["questions"] = len(items_list)
                s["data_dir"] = data_dir
        manifest_path = os.path.join(BASE_DIR, "data", "subject_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! {stats['questions']} questions, {stats['pdfs']} PDFs, {stats['docs']} DOCs")
    print(f"   Data: {data_dir}/")
    print(f"   Config: subjects/{slug}.json (created)" if not os.path.exists(config_path) else f"   Config: subjects/{slug}.json (exists)")
    print(f"   Next: python3 questions_classify_data.py --subject {slug}")

    return True, stats

def main():
    parser = argparse.ArgumentParser(description="Scrape one trapeza subject")
    parser.add_argument("--id", type=int, help="Subject ID")
    parser.add_argument("--slug", help="Subject slug (from manifest)")
    parser.add_argument("--all", action="store_true", help="Scrape ALL pending subjects")
    parser.add_argument("--limit", type=int, default=0, help="Limit questions (for testing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all:
        manifest = load_manifest()
        if not manifest:
            # Generate manifest from local tree cache (no API call)
            print("📋 No manifest found. Generating from local cache...")
            tree = _load_local_tree()
            if not tree:
                print("❌ No local tree cache. Run a single scrape first: python3 scrape_subject.py --id 18 --limit 5")
                return
            subjects = []
            for st in tree.get("school_types", []):
                if st["id"] != 1: continue
                for cl in st.get("classes", []):
                    if cl["id"] != 3: continue
                    for lesson in cl.get("lessons", []):
                        subjects.append({"id": lesson["id"], "name": lesson["name"], "slug": slugify(lesson["name"])})
            manifest = {"subjects": subjects}

        pending = [s for s in manifest["subjects"] if s["slug"] not in ("informatics", "mathematics")]
        print(f"📚 Scraping {len(pending)} pending subjects...")
        results = []
        for i, subj in enumerate(pending):
            print(f"\n[{i+1}/{len(pending)}] Subject {subj['id']}: {subj['name']}")
            try:
                ok, stats = scrape_subject(subj["id"], limit=args.limit, dry_run=args.dry_run)
                results.append((subj["name"], ok))
                if not args.dry_run and i < len(pending) - 1:
                    time.sleep(1)
            except Exception as e:
                print(f"  ❌ Failed: {e}")
                results.append((subj["name"], False))

        print(f"\n{'='*60}")
        print(f"Scrape Summary:")
        for name, ok in results:
            print(f"  {'✅' if ok else '❌'} {name}")
        return

    if not args.id and not args.slug:
        parser.print_help()
        print("\n💡 Tip: Run python3 find_all_subjects.py --save first to see all subject IDs")
        return

    subject_id = args.id
    if args.slug:
        info = find_subject_by_slug(args.slug)
        if info:
            subject_id = info["id"]
        else:
            print(f"❌ Subject with slug '{args.slug}' not found")
            return

    scrape_subject(subject_id, limit=args.limit, dry_run=args.dry_run)

if __name__ == "__main__":
    main()