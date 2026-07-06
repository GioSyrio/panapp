#!/usr/bin/env python3
"""Fix all 34 gap questions by editing question_html_parts arrays directly."""
import json, os, re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathimatika_prosanatolismoy", "questions_v2.json")
OCR = os.path.join(BASE, "data", "subjects", "mathematics", "ocr_results.json")

# Quality filter — only reject formulas with full Greek words or \text{} prose
GARBLED_RE = re.compile(r'\\text\{[α-ω]+\}|συν[άα]ρτηση|είναι|αποδείξετε|[α-ω]{5,}', re.IGNORECASE)

v2 = json.load(open(V2, encoding="utf-8"))
ocr = json.load(open(OCR, encoding="utf-8"))

# Build clean OCR formula lookup
ocr_map = defaultdict(list)
for k, v in ocr.items():
    parts = k.split("/")
    if len(parts) != 2: continue
    qid = int(parts[0])
    latex = v.get("latex", "").strip("$ ")
    latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
    if not latex or len(latex) > 80: continue
    if GARBLED_RE.search(latex): continue  # reject garbled OCR
    ocr_map[qid].append(latex)

# Now process ONLY questions with get parts WITH gaps
def find_gaps(text):
    """Find double-space gap positions in text."""
    return [(m.start(), m.end()) for m in re.finditer(r'\s{2,}', text)]

def insert_formula_at_gap(text, start, end, formula):
    """Insert formula at gap position, preserving surrounding text."""
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    return f"{before} ${formula}$ {after}"

fixed = 0
total_f = 0

for q in v2:
    qid = q["id"]
    formulas = ocr_map.get(qid, [])
    if not formulas:
        continue

    parts = q.get("question_html_parts", [])
    new_parts = list(parts)
    changed = False
    fi = 0  # formula index for THIS question

    for i, part in enumerate(new_parts):
        ptype = "text-content" if 'class="text-content"' in part else "subq" if 'class="subq"' in part else "other"
        
        if ptype == "text-content" and i >= 1:
            # Extract text content
            m = re.search(r'<p class="text-content">([^<]*)</p>', part)
            if not m: continue
            text = m.group(1).strip()
            gaps = find_gaps(text)
            if not gaps or fi >= len(formulas): continue
            
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
            if not m: continue
            text = m.group(1).strip()
            gaps = find_gaps(text)
            if not gaps or fi >= len(formulas): continue
            
            new_text = text
            for gap_start, gap_end in reversed(gaps):
                if fi < len(formulas):
                    new_text = insert_formula_at_gap(new_text, gap_start, gap_end, formulas[fi])
                    fi += 1
            if new_text != text:
                new_parts[i] = part.replace(text, new_text)
                changed = True

    if changed:
        q["question_html_parts"] = new_parts
        q["question_html"] = "\n".join(new_parts)
        old_f = "\n".join(parts).count("$")
        new_f = "\n".join(new_parts).count("$")
        added = (new_f - old_f) // 2
        fixed += 1
        total_f += added
        print(f"  Q{qid}: +{added} formulas (using {len(formulas)} OCR, consumed {fi})")

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)
print(f"\n✅ Fixed {fixed} questions, added {total_f} formulas")