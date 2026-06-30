#!/usr/bin/env python3
"""
fix_all_gaps_v2.py — Insert OCR formulas into question_html gaps.
Fixes the v1 bugs: correct dataset path, backup, dry-run, gap reporting.

Usage:
    python3 fix_all_gaps_v2.py          # dry-run (preview)
    python3 fix_all_gaps_v2.py --apply  # write changes
"""
import json, os, re, shutil, sys, time
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")
OCR = os.path.join(BASE, "data", "subjects", "mathematics", "ocr_results.json")
DRY_RUN = "--apply" not in sys.argv

# ── Quality filter — reject formulas with Greek prose ──────────────────────
GARBLED_RE = re.compile(
    r'\\text\{[α-ω]+\}|συν[άα]ρτηση|είναι|αποδείξετε|'
    r'αντιστρ[έε]φεται|γνησί[ωώ]ς|παραγωγ[ίι]|συνεχ[ήη]ς|'
    r'προσδιορίσετε|αιτιολογ[ήη]σετε|[α-ωΑ-Ω]{5,}',
    re.IGNORECASE
)

THEMA_RE = re.compile(r'^ΘΕΜΑ\s+\d+$')

# ── Load ────────────────────────────────────────────────────────────────────
if DRY_RUN:
    print("=== DRY RUN (use --apply to write) ===\n")
else:
    print("=== APPLYING (backup created) ===\n")

v2 = json.load(open(V2, encoding="utf-8"))
ocr = json.load(open(OCR, encoding="utf-8"))

# Build OCR formula lookup: {qid: [formula1, formula2, ...]}
ocr_map = defaultdict(list)
for k, v in ocr.items():
    parts = k.split("/")
    if len(parts) != 2:
        continue
    qid = int(parts[0])
    latex = v.get("latex", "").strip("$ ")
    latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
    if not latex or len(latex) > 80:
        continue
    if GARBLED_RE.search(latex):
        continue
    ocr_map[qid].append(latex)

print(f"OCR formulas available for {len(ocr_map)} questions")

# ── Gap utilities ───────────────────────────────────────────────────────────
def find_gaps(text):
    """Find double-space positions in text (formula gaps)."""
    return [(m.start(), m.end()) for m in re.finditer(r'\s{2,}', text)]

def insert_formula_at_gap(text, start, end, formula):
    """Insert $formula$ at gap, preserving surrounding text."""
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    return f"{before} ${formula}$ {after}"

# ── Process ─────────────────────────────────────────────────────────────────
fixed_q = 0
total_formulas_added = 0
unfixed_gaps = 0
questions_with_unfixed = []

for q in v2:
    qid = q["id"]
    formulas = ocr_map.get(qid, [])
    if not formulas:
        continue

    parts = q.get("question_html_parts", [])
    new_parts = list(parts)
    changed = False
    fi = 0  # formula index for this question

    for i, part in enumerate(new_parts):
        ptype = "other"
        if 'class="text-content"' in part:
            ptype = "text-content"
        elif 'class="subq"' in part:
            ptype = "subq"

        if ptype == "text-content":
            # Skip "ΘΕΜΑ X" headers at position 0
            if i == 0:
                m = re.search(r'<p class="text-content">([^<]*)</p>', part)
                if m and THEMA_RE.match(m.group(1).strip()):
                    continue
            m = re.search(r'<p class="text-content">([^<]*)</p>', part)
            if not m:
                continue
            text = m.group(1).strip()
            gaps = find_gaps(text)
            if not gaps or fi >= len(formulas):
                continue

            new_text = text
            for gap_start, gap_end in reversed(gaps):
                if fi < len(formulas):
                    new_text = insert_formula_at_gap(new_text, gap_start, gap_end, formulas[fi])
                    fi += 1
            if new_text != text:
                new_parts[i] = f'<p class="text-content">{new_text}</p>'
                changed = True

        elif ptype == "subq":
            m = re.search(r'class="subq-text">([^<]*)</span>', part)
            if not m:
                continue
            text = m.group(1).strip()
            gaps = find_gaps(text)
            if not gaps or fi >= len(formulas):
                continue

            new_text = text
            for gap_start, gap_end in reversed(gaps):
                if fi < len(formulas):
                    new_text = insert_formula_at_gap(new_text, gap_start, gap_end, formulas[fi])
                    fi += 1
            if new_text != text:
                new_parts[i] = part.replace(text, new_text)
                changed = True

    # Check for unfixed gaps
    remaining_gaps = 0
    for part in new_parts:
        if 'class="text-content"' in part or 'class="subq"' in part:
            m = re.search(r'(?:<p class="text-content">|<span class="subq-text">)([^<]*)(?:</p>|</span>)', part)
            if m:
                remaining_gaps += len(find_gaps(m.group(1)))

    if changed:
        q["question_html_parts"] = new_parts
        q["question_html"] = "\n".join(new_parts)
        old_f = "\n".join(parts).count("$")
        new_f = "\n".join(new_parts).count("$")
        added = (new_f - old_f) // 2
        fixed_q += 1
        total_formulas_added += added
        status = ""
        if remaining_gaps > 0:
            unfixed_gaps += remaining_gaps
            questions_with_unfixed.append(qid)
            status = f" ⚠️ {remaining_gaps} gaps unfixed (had {len(formulas)} OCR formulas)"
        print(f"  Q{qid}: +{added} formulas (used {len(formulas)} OCR, consumed {fi}){status}")

# ── Save ────────────────────────────────────────────────────────────────────
if DRY_RUN:
    print(f"\n✅ DRY RUN — would fix {fixed_q} questions, add {total_formulas_added} formulas")
    if questions_with_unfixed:
        print(f"⚠️  {len(questions_with_unfixed)} questions would still have {unfixed_gaps} unfixed gaps")
    print("Run with --apply to write changes")
else:
    # Backup
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = V2 + f".bak.gaps-{ts}"
    shutil.copy(V2, bak)
    print(f"Backup: {os.path.basename(bak)}")

    with open(V2, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
    print(f"✅ Fixed {fixed_q} questions, added {total_formulas_added} formulas")

    # Post-fix stats
    no_math = sum(1 for q in v2 if "$" not in q.get("question_html", ""))
    print(f"Questions still without math: {no_math}/{len(v2)}")
    if questions_with_unfixed:
        print(f"⚠️  {len(questions_with_unfixed)} questions still have {unfixed_gaps} unfixed gaps: {questions_with_unfixed[:10]}")