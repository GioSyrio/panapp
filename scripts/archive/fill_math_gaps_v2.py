#!/usr/bin/env python3
"""Fix 34 gap questions by inserting OCR formulas at gap positions directly."""
import json, os, re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathimatika_prosanatolismoy", "questions_v2.json")
OCR = os.path.join(BASE, "data", "subjects", "mathematics", "ocr_results.json")

GREEK_PROSE_RE = re.compile(r'συν[άα]ρτηση|είναι|αποδείξ|γνησίω|[α-ω]{4,}', re.IGNORECASE)

v2 = json.load(open(V2, encoding="utf-8"))
ocr = json.load(open(OCR, encoding="utf-8"))

# Build OCR formula lookup per question
ocr_map = defaultdict(list)
for k, v in ocr.items():
    parts = k.split("/")
    if len(parts) != 2: continue
    qid = int(parts[0])
    latex = v.get("latex", "").strip("$ ")
    latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
    if latex and not GREEK_PROSE_RE.search(latex):
        ocr_map[qid].append(latex)

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
    fi = 0  # formula index

    for i, part in enumerate(new_parts):
        # Fix text-content parts
        if 'class="text-content"' in part and i >= 1:
            text = re.sub(r'<[^>]+>', ' ', part).strip()
            gaps = list(re.finditer(r'\s{2,}', text))
            if gaps and fi < len(formulas):
                new_text = text
                for gap in reversed(gaps):
                    if fi < len(formulas):
                        new_text = (new_text[:gap.start()] + " " + 
                                   f"${formulas[fi]}$ " + 
                                   new_text[gap.end():])
                        fi += 1
                        changed = True
                new_parts[i] = f'<p class="text-content">{new_text.strip()}</p>'

        # Fix subq parts
        elif 'class="subq"' in part:
            m = re.search(r'class="subq-text">([^<]*)</span>', part)
            if not m: continue
            text = m.group(1).strip()
            gaps = list(re.finditer(r'\s{2,}', text))
            if gaps and fi < len(formulas):
                new_text = text
                for gap in reversed(gaps):
                    if fi < len(formulas):
                        new_text = (new_text[:gap.start()] + " " + 
                                   f"${formulas[fi]}$ " + 
                                   new_text[gap.end():])
                        fi += 1
                        changed = True
                new_parts[i] = part.replace(text, new_text.strip())

    if changed:
        q["question_html_parts"] = new_parts
        q["question_html"] = "\n".join(new_parts)
        old_f = "\n".join(parts).count("$")
        new_f = "\n".join(new_parts).count("$")
        added = (new_f - old_f) // 2
        fixed += 1
        total_f += added
        if added > 0:
            print(f"  Q{qid}: +{added} formulas")

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)
print(f"\n✅ Fixed {fixed} questions, added {total_f} formulas")