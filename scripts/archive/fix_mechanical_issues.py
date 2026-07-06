#!/usr/bin/env python3
"""
fix_mechanical_issues.py — Fix remaining mechanical HTML structure issues

Fixes:
  1. nested_p: Remove nested <p class="text-content"><p...> wrappers (merge bug)
  2. consec_points: Deduplicate remaining consecutive points-chips
  3. corrupt_ocr: Remove $...$ with Greek prose, \text{...} artifacts
  4. text_as_subq: Convert text-content starting with subq prefix to subq wrapper

Touches ONLY question_html_parts and question_html.
"""

import json, os, re, argparse
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

GREEK_PROSE_RE = re.compile(
    r'συν[άα]ρτηση|είναι|αποδείξετε|αντιστρ[έε]φεται|γνησίως|παραγωγ|συνεχής|'
    r'παραουσιάζ|γραφική παράσταση|προσδιορίσετε|αιτιολογήσετε|μελετηθεί|'
    r'\bNa\b|\bΘα\b|\\?mathrm\{[α-ω]', re.IGNORECASE)

def fix_nested_p(parts):
    """Fix double-wrapped <p> tags from merge bugs."""
    changed = False
    new_parts = []
    for p in parts:
        new_p = re.sub(r'<p class="text-content">\s*<p class="text-content">\s*(.+?)\s*</p>\s*</p>',
                       r'<p class="text-content">\1</p>', p, flags=re.DOTALL)
        if new_p != p:
            changed = True
        new_parts.append(new_p)
    return new_parts, changed

def fix_consec_pts_remaining(parts):
    """Remove consecutive duplicate points-chips."""
    changed = False
    new_parts = []
    i = 0
    while i < len(parts):
        if 'points-chip' in parts[i] and i + 1 < len(parts) and 'points-chip' in parts[i + 1]:
            changed = True
            i += 1  # skip first, keep second
            continue
        new_parts.append(parts[i])
        i += 1
    return new_parts, changed

def fix_corrupt_ocr_extended(parts):
    """Remove $...$ spans with Greek prose or \text{} artifacts."""
    changed = False
    new_parts = []
    for p in parts:
        removed = [0]
        def clean(m):
            content = m.group(1)
            if GREEK_PROSE_RE.search(content):
                removed[0] += 1; return ''
            if re.search(r'\\text\{[^}]*[α-ωΑ-Ω]{3,}', content):
                removed[0] += 1; return ''
            return m.group(0)
        new_p = re.sub(r'\$([^$]+)\$', clean, p)
        new_p = re.sub(r'\s{2,}', ' ', new_p)
        if removed[0] > 0:
            changed = True
        new_parts.append(new_p)
    return new_parts, changed

def fix_text_as_subq(parts):
    """Convert text-content starting with subq prefix into proper subq wrapper."""
    changed = False
    new_parts = []
    subq_re = re.compile(r'^([α-ωΑ-Ω])\)\s*(.*)')
    for p in parts:
        if 'class="text-content"' not in p:
            new_parts.append(p)
            continue
        plain = re.sub(r'<[^>]+>', '', p).strip()
        m = subq_re.match(plain)
        if not m or len(m.group(2)) < 3:
            new_parts.append(p)
            continue
        num = m.group(1) + ')'
        text = m.group(2)
        new_parts.append(
            f'<div class="subq"><span class="subq-num">{num}</span> '
            f'<span class="subq-text">{text}</span></div>')
        changed = True
    return new_parts, changed

def analyze_and_fix(q):
    parts = list(q.get("question_html_parts", []))
    changes = []

    parts, ch = fix_nested_p(parts)
    if ch: changes.append("nested_p")

    parts, ch = fix_consec_pts_remaining(parts)
    if ch: changes.append("consec_pts")

    parts, ch = fix_text_as_subq(parts)
    if ch: changes.append("text_as_subq")

    parts, ch = fix_corrupt_ocr_extended(parts)
    if ch: changes.append("corrupt_ocr")

    return parts, changes

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--id", type=int, default=0)
    args = parser.parse_args()

    v2 = json.load(open(V2, encoding="utf-8"))
    targets = [args.id] if args.id else [q["id"] for q in v2]

    fixed = total = 0
    stats = Counter()
    log = []

    for qid in targets:
        q = next((x for x in v2 if x["id"] == qid), None)
        if not q: continue
        old = q.get("question_html_parts", [])
        new, changes = analyze_and_fix(q)
        if not changes: continue
        total += 1
        if args.dry_run:
            print(f"  Q{qid}: {'+'.join(changes)} ({len(old)}→{len(new)})")
        else:
            q["question_html_parts"] = new
            q["question_html"] = "\n".join(new)
            fixed += 1
            for c in changes: stats[c] += 1
            log.append(f"Q{qid}: {'+'.join(changes)} ({len(old)}→{len(new)})")

    if args.dry_run:
        print(f"\n[DRY] {total} qs")
    else:
        with open(V2, "w", encoding="utf-8") as f:
            json.dump(v2, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Fixed {fixed} ({sum(stats.values())} changes)")
        for k, v in stats.most_common(): print(f"  {k}: {v}")
        lp = os.path.join(os.path.dirname(V2), "fix_mechanical_log.txt")
        with open(lp, "w") as f:
            f.write(f"Mechanical fixes — {len(log)} qs\n\n")
            for k, v in stats.most_common(): f.write(f"  {k}: {v}\n")
            f.write("\nQuestions:\n")
            for l in log: f.write(f"  {l}\n")

if __name__ == "__main__":
    main()