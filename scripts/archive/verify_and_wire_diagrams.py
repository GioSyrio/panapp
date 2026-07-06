#!/usr/bin/env python3
"""
verify_and_wire_diagrams.py — Activate diagrams once screenshots are placed

Checks static/images/math_diagrams/ for existing PNG files and wires them
into questions_v2.json by setting diagram_url and removing placeholders.

Usage:
    python3 verify_and_wire_diagrams.py --subject mathematics
    python3 verify_and_wire_diagrams.py --subject mathematics --dry-run
"""

import json, os, re, argparse

BASE = os.path.dirname(os.path.abspath(__file__))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="mathematics")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = os.path.join(BASE, "data", "subjects", args.subject)
    v2_file = os.path.join(data_dir, "questions_v2.json")
    img_dir = os.path.join(BASE, "static", "images", "math_diagrams")

    with open(v2_file, encoding="utf-8") as f:
        v2 = json.load(f)

    activated = 0
    still_pending = 0
    PLACEHOLDER_RE = re.compile(r'<div class="diagram-placeholder"[^>]*>.*?</div>', re.DOTALL)

    for q in v2:
        qid = q["id"]
        img_path = os.path.join(img_dir, f"{qid}.png")

        if os.path.exists(img_path):
            # Wire up the diagram
            url = f"static/images/math_diagrams/{qid}.png"
            img_tag = (
                f'<div class="diagram-section"><div class="diagram-label">📊 Σχήμα / Διάγραμμα:</div>'
                f'<img src="/{url}" alt="Διάγραμμα Εξέτασης" class="question-diagram" '
                f'style="max-width:100%;max-height:400px;border-radius:10px;border:1px solid var(--border);'
                f'cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.06);" onclick="openDiagramModal(this.src)" loading="lazy">'
                f'<div style="margin-top:6px;font-size:0.75rem;color:var(--text2);">💡 Κάνε κλικ στο σχήμα για μεγέθυνση</div></div>'
            )

            if not args.dry_run:
                q["diagram_url"] = url
                parts = list(q.get("question_html_parts", []))
                new_parts = []
                for p in parts:
                    if 'class="diagram-placeholder"' in p:
                        new_parts.append(img_tag)
                    else:
                        new_parts.append(p)
                q["question_html_parts"] = new_parts
                q["question_html"] = "\n".join(new_parts)

            activated += 1
        else:
            if any('class="diagram-placeholder"' in p for p in q.get("question_html_parts", [])):
                still_pending += 1

    if args.dry_run:
        print(f"\n[DRY RUN] Would activate {activated} diagrams")
        print(f"  Still pending: {still_pending}")
    else:
        with open(v2_file, "w", encoding="utf-8") as f:
            json.dump(v2, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Activated {activated} diagrams")
        print(f"   Still pending: {still_pending}")

if __name__ == "__main__":
    main()