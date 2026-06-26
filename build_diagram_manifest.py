#!/usr/bin/env python3
"""
build_diagram_manifest.py — Phase 2: Diagram placeholder injection

Scans all math questions for graph/diagram references, adds placeholders
where diagrams are missing, and generates a manifest for manual screenshot flow.

Usage:
    python3 build_diagram_manifest.py --subject mathematics
    python3 build_diagram_manifest.py --subject mathematics --dry-run
"""

import json, os, re, argparse
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))

GRAPH_REF_RE = re.compile(
    r'(σχήμα|γραφική παράσταση|διάγραμμα|γραφικές παραστάσεις|'
    r'στο παρακάτω|στο διπλανό|στο σχήμα|η γραφική|Cf|Cg)',
    re.IGNORECASE)

def has_graph_reference(q):
    """Check if question text references a graph/diagram."""
    html = q.get("question_html", "")
    sections_text = " ".join(s.get("content", "") for s in q.get("sections", []))
    combined = html + " " + sections_text
    return bool(GRAPH_REF_RE.search(combined))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="mathematics")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = os.path.join(BASE, "data", "subjects", args.subject)
    v2_file = os.path.join(data_dir, "questions_v2.json")
    manifest_file = os.path.join(data_dir, "diagram_manifest.json")
    img_dir = os.path.join(BASE, "static", "images", "math_diagrams")

    with open(v2_file, encoding="utf-8") as f:
        v2 = json.load(f)

    needs_diagram = []
    has_diagram = []
    modified = 0

    for q in v2:
        qid = q["id"]
        if not has_graph_reference(q):
            continue

        existing = q.get("diagram_url")
        if existing:
            has_diagram.append({"id": qid, "url": existing, "part": q["part"]})
            continue

        needs_diagram.append({
            "id": qid,
            "part": q["part"],
            "points": q["points"],
            "year": q.get("year", "?"),
            "expected_path": f"static/images/math_diagrams/{qid}.png"
        })

        # Inject placeholder into question_html_parts
        parts = list(q.get("question_html_parts", []))
        placeholder = (
            '<div class="diagram-placeholder" data-qid="' + str(qid) + '" '
            'style="margin:16px 0;padding:40px 20px;border:2px dashed var(--amber, #d97706);'
            'border-radius:12px;text-align:center;background:#fffbeb;">'
            '<div style="font-size:1.1rem;font-weight:700;color:#92400e;margin-bottom:8px;">'
            '📊 Διάγραμμα / Σχήμα</div>'
            '<div style="font-size:0.85rem;color:#78350f;">'
            'Το διάγραμμα για αυτή την ερώτηση δεν έχει προστεθεί ακόμα.</div>'
            '<div style="font-size:0.75rem;color:#a16207;margin-top:4px;">'
            'ID: ' + str(qid) + ' — ' + str(q.get("year", "?")) + '</div>'
            '</div>'
        )

        # Insert placeholder after the description paragraphs but before first subq
        insert_idx = len(parts)
        for i, p in enumerate(parts):
            if 'class="subq"' in p:
                insert_idx = i
                break

        if not args.dry_run:
            parts.insert(insert_idx, placeholder)
            q["question_html_parts"] = parts
            q["question_html"] = "\n".join(parts)
            modified += 1

    # Write manifest
    manifest = {
        "subject": args.subject,
        "total_questions": len(v2),
        "questions_with_graphs": len(needs_diagram) + len(has_diagram),
        "needs_diagram": len(needs_diagram),
        "has_diagram": len(has_diagram),
        "pending": needs_diagram,
        "completed": has_diagram
    }

    if args.dry_run:
        print(f"\n[DRY RUN] Would add placeholders to {modified} questions")
        print(f"  Needs diagram: {len(needs_diagram)}")
        print(f"  Has diagram: {len(has_diagram)}")
        print(f"\nFirst 10 needing diagrams:")
        for d in needs_diagram[:10]:
            print(f"  Q{d['id']} [{d['part']}] — {d['expected_path']}")
    else:
        with open(v2_file, "w", encoding="utf-8") as f:
            json.dump(v2, f, ensure_ascii=False, indent=2)
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        os.makedirs(img_dir, exist_ok=True)

        print(f"\n✅ Diagram Manifest Complete")
        print(f"   Placeholders added: {modified}")
        print(f"   Needs screenshots: {len(needs_diagram)}")
        print(f"   Already has images: {len(has_diagram)}")
        print(f"   Manifest: {manifest_file}")
        print(f"   Image dir: {img_dir}/")
        print(f"\nNext steps:")
        print(f"   1. Take screenshots of diagrams → save as {img_dir}/{{qid}}.png")
        print(f"   2. Run verify_and_wire_diagrams.py to activate them")

if __name__ == "__main__":
    main()