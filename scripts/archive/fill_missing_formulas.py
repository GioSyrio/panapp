#!/usr/bin/env python3
"""
fill_missing_formulas.py — Auto-fill missing formulas for math questions

Identifies questions where valid OCR formulas exist but weren't placed in the
HTML, and appends them at the end of text-content parts (best-effort placement).
Only touches question_html and question_html_parts — all batch data preserved.

Usage:
    python3 fill_missing_formulas.py                    # fix ALL affected
    python3 fill_missing_formulas.py --dry-run          # preview only
    python3 fill_missing_formulas.py --id 23314         # single question
"""

import json, os, re, sys, argparse, html as _html
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GREEK_PROSE_RE = re.compile(
    r'συν[άα]ρτηση|είναι|αποδείξετε|αντιστρ[έε]φεται|'
    r'προσδιορίσετε|αιτιολογήσετε|γνησίως|συνεχής|παραγωγίσιμη',
    re.IGNORECASE
)

def esc(s):
    return _html.escape(s)

def is_valid_ocr(latex):
    if not latex or len(latex) < 2:
        return False
    if GREEK_PROSE_RE.search(latex):
        return False
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't save")
    parser.add_argument("--id", type=int, default=0, help="Single question")
    args = parser.parse_args()

    data_dir = os.path.join(BASE_DIR, "data", "subjects", "mathematics")
    v2_file = os.path.join(data_dir, "questions_v2.json")
    ocr_file = os.path.join(data_dir, "ocr_results.json")

    v2 = json.load(open(v2_file, encoding="utf-8"))
    ocr = json.load(open(ocr_file, encoding="utf-8"))

    # Build OCR lookup: qid → sorted list of (filename, latex)
    ocr_by_qid = defaultdict(list)
    for k, v in ocr.items():
        parts = k.split("/")
        if len(parts) == 2:
            qid = int(parts[0])
            latex = v.get("latex", "").strip("$ ")
            latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
            if is_valid_ocr(latex):
                ocr_by_qid[qid].append((parts[1], latex))

    # Sort by filename for each qid
    for qid in ocr_by_qid:
        ocr_by_qid[qid].sort(key=lambda x: x[0])

    fixed = 0
    total_formulas_added = 0
    review_log = []

    for q in v2:
        qid = q["id"]
        if args.id and qid != args.id:
            continue

        available = ocr_by_qid.get(qid, [])
        if not available:
            continue

        html_parts = q.get("question_html_parts", [])
        if not html_parts:
            continue

        # Count existing formulas
        old_count = q.get("question_html", "").count("$") // 2
        needed = len(available) - old_count
        if needed <= 0:
            continue

        # Collect formulas to add
        formulas_to_add = available[-needed:]  # last N unused

        # Find text-content parts to append formulas to
        text_indices = [i for i, p in enumerate(html_parts)
                        if 'class="text-content"' in p and p.count("$") < 4]
        subq_indices = [i for i, p in enumerate(html_parts)
                        if 'class="subq"' in p and 'subq-text' in p]

        if not text_indices and not subq_indices:
            continue

        # Distribute formulas: 1 per text-content part, overflow to subq parts
        new_parts = list(html_parts)
        formula_idx = 0
        total_targets = text_indices + subq_indices

        for idx in total_targets:
            if formula_idx >= len(formulas_to_add):
                break
            part = new_parts[idx]
            fname, latex = formulas_to_add[formula_idx]
            formula_html = f" ${latex}$ "

            if 'class="text-content"' in part:
                # Append formula before closing </p>
                new_parts[idx] = part.replace("</p>", f"{formula_html}</p>")
            elif 'class="subq-text"' in part:
                # Append formula to subq-text span
                new_parts[idx] = part.replace("</span></div>",
                                              f"{formula_html}</span></div>")
            formula_idx += 1

        new_html = "\n".join(new_parts)
        new_count = new_html.count("$") // 2

        if args.dry_run:
            print(f"  Q{qid}: would add {formula_idx}/{needed} formulas ({old_count} → {new_count})")
            review_log.append((qid, old_count, new_count, formula_idx, needed))
        else:
            q["question_html"] = new_html
            q["question_html_parts"] = new_parts
            fixed += 1
            total_formulas_added += formula_idx
            if formula_idx > 0:
                review_log.append((qid, old_count, new_count, formula_idx, needed))

    if args.dry_run:
        print(f"\n[DRY RUN] Would fix {len(review_log)} questions, add {sum(r[3] for r in review_log)} formulas")
    else:
        if not args.id:
            with open(v2_file, "w", encoding="utf-8") as f:
                json.dump(v2, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Fixed {fixed} questions, added {total_formulas_added} formulas")
        if review_log:
            log_path = os.path.join(data_dir, "formula_fill_log.txt")
            with open(log_path, "w") as f:
                f.write(f"Questions with auto-filled formulas ({len(review_log)}):\n")
                for qid, old, new, added, needed in review_log:
                    f.write(f"  Q{qid}: {old} → {new} formulas (+{added}/{needed})\n")
            print(f"   Review log: {log_path}")

if __name__ == "__main__":
    main()