#!/usr/bin/env python3
"""
find_all_subjects.py — Discover all subjects from the trapeza API tree

Fetches the school type/class tree from the trapeza API and lists all
available subjects with their IDs, names, and metadata.

Usage:
    python3 find_all_subjects.py                 # list all
    python3 find_all_subjects.py --json          # output as JSON manifest
    python3 find_all_subjects.py --save          # save manifest to data/subject_manifest.json
"""

import json, os, sys, argparse, urllib.request, urllib.error

API_BASE = "https://api.trapeza.registry.digitalschool.gov.gr/v1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def find_all_subjects(type_id=1, class_id=3):
    """Fetch the tree and extract all subjects."""
    tree = fetch_json(f"{API_BASE}/tree?type={type_id}&class={class_id}")
    subjects = []

    for st in tree.get("school_types", []):
        if st["id"] != type_id:
            continue
        for cl in st.get("classes", []):
            if cl["id"] != class_id:
                continue
            for lesson in cl.get("lessons", []):
                subjects.append({
                    "id": lesson["id"],
                    "name": lesson["name"],
                    "subject_types": lesson.get("subject_types", []),
                    "material": lesson.get("material", []),
                    "allsubjects_file_title": lesson.get("allsubjects_file_title"),
                    "criteria_file_title": lesson.get("criteria_file_title"),
                    "school_type": st["name"],
                    "class_name": cl["name"],
                })

    return subjects

def slugify(greek_name):
    """Convert Greek subject name to ASCII slug for file paths."""
    mapping = {
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
    slug = ''.join(mapping.get(c, c) for c in greek_name.lower())
    slug = ''.join(c if c.isalnum() or c == '_' else '_' for c in slug)
    return slug.strip('_') or 'unknown'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--save", action="store_true", help="Save manifest file")
    args = parser.parse_args()

    print("🔍 Fetching subject tree from trapeza API...")
    subjects = find_all_subjects(1, 3)

    if not subjects:
        print("❌ No subjects found!")
        sys.exit(1)

    # Add slug and status
    existing_slugs = {"informatics", "mathematics"}
    for s in subjects:
        s["slug"] = slugify(s["name"])
        s["status"] = "active" if s["slug"] in existing_slugs else "pending"

    manifest = {
        "source": f"{API_BASE}/tree?type=1&class=3",
        "school_type": "Γενικό Λύκειο",
        "class": "Γ' ΤΑΞΗ",
        "total_subjects": len(subjects),
        "subjects": subjects,
    }

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"\n📚 Found {len(subjects)} subjects for Γενικό Λύκειο, Γ' ΤΑΞΗ:\n")
        print(f"{'ID':>5}  {'Status':<10}  {'Name':<45}  {'Slug'}")
        print("-" * 85)
        for s in subjects:
            status_icon = "✅" if s["status"] == "active" else "⬜"
            print(f"{s['id']:>5}  {status_icon} {s['status']:<8}  {s['name']:<45}  {s['slug']}")

    if args.save:
        manifest_path = os.path.join(BASE_DIR, "data", "subject_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"\n📁 Saved to {manifest_path}")

    # Print quick-start commands
    pending = [s for s in subjects if s["status"] == "pending"]
    if pending:
        print(f"\n🚀 To scrape pending subjects:")
        for s in pending:
            print(f"   python3 scrape_subject.py --id {s['id']}  # {s['name']}")

if __name__ == "__main__":
    main()