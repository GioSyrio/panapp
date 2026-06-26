#!/usr/bin/env python3
"""
fix_ui_batch.py — Batch-fix structural issues in math question_html_parts

Fixes (auto):
  1. zero_points: "⭐ 06 μονάδες" → "⭐ 6 μονάδες"
  2. bare_dots: remove "<p class="text-content">.</p>" artifacts
  3. consec_points: deduplicate consecutive points-chips
  4. orphan_points: reorder so points-chips follow their preceding subq
  5. remove_duplicate_subqs: delete text-content parts that mirror existing subq-text
  6. strip_corrupted_ocr: remove $...$ spans containing Greek prose keywords
  7. merge_fragments: merge consecutive text-content parts when second starts lowercase

Touches ONLY question_html_parts and question_html. All batch data preserved.

Usage:
    python3 fix_ui_batch.py              # fix all
    python3 fix_ui_batch.py --dry-run    # preview
    python3 fix_ui_batch.py --start 0 --end 10  # batch of 10
    python3 fix_ui_batch.py --id 23210   # single question
"""

import json, os, re, argparse
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

# ── Greek prose keywords (LaTeX that shouldn't be in formulas) ────────────
GREEK_PROSE_RE = re.compile(
    r'συν[άα]ρτηση|είναι|αποδείξετε|αντιστρ[έε]φεται|γνησίως|παραγωγ|συνεχής|'
    r'παραουσιάζ|γραφική παράσταση|προσδιορίσετε|αιτιολογήσετε|μελετηθεί|'
    r'[α-ωΑ-Ω]{5,}', re.IGNORECASE)

def fix_zero_points(parts):
    """Strip leading zeros from points values."""
    changed = False
    new_parts = []
    for p in parts:
        m = re.search(r'⭐ 0(\d+) μονάδες', p)
        if m:
            new_p = p.replace(f'⭐ 0{m.group(1)} μονάδες', f'⭐ {m.group(1)} μονάδες')
            new_parts.append(new_p)
            changed = True
        else:
            new_parts.append(p)
    return new_parts, changed

def fix_bare_dots(parts):
    """Remove bare '.' text-content paragraphs."""
    new_parts = [p for p in parts if p.strip() != '<p class="text-content">.</p>']
    return new_parts, len(new_parts) != len(parts)

def fix_consecutive_points(parts):
    """Remove duplicate consecutive points-chips, keep the last one."""
    changed = False
    new_parts = []
    i = 0
    while i < len(parts):
        if 'points-chip' in parts[i]:
            if i + 1 < len(parts) and 'points-chip' in parts[i + 1]:
                changed = True
                i += 1
                continue
        new_parts.append(parts[i])
        i += 1
    return new_parts, changed

def fix_orphan_points(parts):
    """Move points-chips to after nearest preceding subq."""
    changed = False
    new_parts = list(parts)
    last_subq_idx = -1
    for i in range(len(new_parts)):
        if 'class="subq"' in new_parts[i]:
            last_subq_idx = i
        elif 'points-chip' in new_parts[i]:
            if i > 0 and 'class="subq"' in new_parts[i - 1]:
                continue
            if i > 0 and 'class="text-content"' in new_parts[i - 1]:
                if last_subq_idx >= 0:
                    pts = new_parts.pop(i)
                    new_parts.insert(last_subq_idx + 1, pts)
                    changed = True
                    return fix_orphan_points(new_parts)
    return new_parts, changed

def remove_duplicate_subqs(parts):
    """
    Delete text-content parts that mirror existing subq-text content.
    e.g. <p class="text-content">α) Να μελετηθεί...</p> when
         <div class="subq">...<span class="subq-text">α) Να μελετηθεί...</span> already exists.
    """
    changed = False
    # Collect normalized subq-text content
    subq_contents = []
    for p in parts:
        m = re.search(r'<span class="subq-text">([^<]+)</span>', p)
        if m:
            subq_contents.append(m.group(1).strip().lower())

    if not subq_contents:
        return parts, False

    # Remove text-content parts that duplicate a subq-text
    new_parts = []
    for p in parts:
        if 'class="text-content"' in p and '<span class="subq-num">' not in p:
            plain = re.sub(r'<[^>]+>', '', p).strip().lower()
            plain = re.sub(r'\s+', ' ', plain)  # normalize whitespace
            is_dup = False
            for sc in subq_contents:
                sc_norm = re.sub(r'\s+', ' ', sc)
                # Check if plain text is essentially the same as a subq
                if plain and len(plain) > 10 and (plain in sc_norm or sc_norm in plain):
                    is_dup = True
                    break
            if is_dup:
                changed = True
                continue  # skip this duplicate
        new_parts.append(p)

    return new_parts, changed

def strip_corrupted_ocr(parts):
    """Remove $...$ formula spans that contain Greek prose keywords."""
    changed = False
    new_parts = []
    for p in parts:
        # Find all $...$ spans
        def clean_formula(m):
            nonlocal changed
            content = m.group(1)
            if GREEK_PROSE_RE.search(content):
                changed = True
                return ''  # remove the formula entirely
            return m.group(0)  # keep as-is

        new_p = re.sub(r'\$([^$]+)\$', clean_formula, p)
        # Clean up double spaces left by removals
        new_p = re.sub(r'\s{2,}', ' ', new_p)
        new_parts.append(new_p)

    return new_parts, changed

def merge_fragments(parts):
    """
    Merge consecutive text-content parts when the second starts with
    a lowercase Greek letter or plain continuation word.
    Only merge when both are pure text-content (no subq, no points).
    """
    changed = False
    new_parts = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if 'class="text-content"' in p and i + 1 < len(parts) and 'class="text-content"' in parts[i + 1]:
            # Safe merge: combine into one paragraph, join with space
            next_plain = re.sub(r'<[^>]+>', '', parts[i + 1]).strip()
            # Only merge if next part starts with lowercase or is a sentence continuation
            if next_plain and (
                next_plain[0].islower() or
                next_plain.startswith('και ') or
                next_plain.startswith('για ') or
                next_plain.startswith('με ') or
                next_plain.startswith('στο ') or
                next_plain.startswith('ενώ ') or
                next_plain.startswith(',') or
                next_plain.startswith('όπου ') or
                next_plain.startswith('η ') or
                next_plain.startswith('τα ') or
                next_plain.startswith('το ')
            ):
                # Merge: remove </p> from current, <p...> from next, join
                merged = p.replace('</p>', ' ') + parts[i + 1].replace('<p class="text-content">', '').replace('</p>', '')
                # Re-wrap in single paragraph
                new_parts.append(f'<p class="text-content">{merged.strip()}</p>')
                changed = True
                i += 2
                continue
        new_parts.append(p)
        i += 1
    return new_parts, changed

def analyze_and_fix(q):
    """Analyze and fix a single question's parts. Returns (fixed_parts, changes)."""
    parts = list(q.get("question_html_parts", []))
    changes = []

    # Fix 1: zero_points
    parts, ch = fix_zero_points(parts)
    if ch: changes.append("zero_points")

    # Fix 2: bare_dots
    parts, ch = fix_bare_dots(parts)
    if ch: changes.append("bare_dots")

    # Fix 3: consec_points
    parts, ch = fix_consecutive_points(parts)
    if ch: changes.append("consec_points")

    # Fix 4: orphan_points
    parts, ch = fix_orphan_points(parts)
    if ch: changes.append("orphan_points")

    # Fix 5: remove_duplicate_subqs
    parts, ch = remove_duplicate_subqs(parts)
    if ch: changes.append("remove_dup_subqs")

    # Fix 6: strip_corrupted_ocr
    parts, ch = strip_corrupted_ocr(parts)
    if ch: changes.append("strip_corrupt_ocr")

    # Fix 7: merge_fragments (conservative)
    parts, ch = merge_fragments(parts)
    if ch: changes.append("merge_fragments")

    return parts, changes

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--id", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    v2 = json.load(open(V2, encoding="utf-8"))

    if args.id:
        targets = [args.id]
    elif args.end > 0:
        targets = [q["id"] for q in v2[args.start:args.end]]
    else:
        targets = [q["id"] for q in v2]

    fixed = 0
    total = 0
    total_changes = Counter()
    log_lines = []

    for qid in targets:
        q = next((x for x in v2 if x["id"] == qid), None)
        if not q:
            continue

        old_parts = q.get("question_html_parts", [])
        new_parts, changes = analyze_and_fix(q)

        if not changes:
            continue

        total += 1
        if args.dry_run:
            old_count = "\n".join(old_parts).count("$") // 2
            new_count = "\n".join(new_parts).count("$") // 2
            print(f"  Q{qid}: would fix {'+'.join(changes)} ({len(old_parts)}→{len(new_parts)} parts, {old_count}→{new_count} formulas)")
        else:
            q["question_html_parts"] = new_parts
            q["question_html"] = "\n".join(new_parts)
            fixed += 1
            for c in changes:
                total_changes[c] += 1
            log_lines.append(f"Q{qid}: {'+'.join(changes)} ({len(old_parts)}→{len(new_parts)} parts)")

    if args.dry_run:
        print(f"\n[DRY RUN] Would fix {total} questions")
    else:
        with open(V2, "w", encoding="utf-8") as f:
            json.dump(v2, f, ensure_ascii=False, indent=2)

        log_path = os.path.join(os.path.dirname(V2), "fix_ui_batch_log.txt")
        with open(log_path, "w") as f:
            f.write(f"UI Batch Fix Log — {len(log_lines)} questions fixed\n\n")
            f.write("Change breakdown:\n")
            for k, v in total_changes.most_common():
                f.write(f"  {k}: {v}\n")
            f.write("\nQuestions:\n")
            for line in log_lines:
                f.write(f"  {line}\n")

        print(f"\n✅ Fixed {fixed} questions ({sum(total_changes.values())} changes)")
        for k, v in total_changes.most_common():
            print(f"  {k}: {v}")
        print(f"  Log: {log_path}")

if __name__ == "__main__":
    main()