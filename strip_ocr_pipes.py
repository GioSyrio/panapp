#!/usr/bin/env python3
"""Remove OCR artifact |..| patterns from math formulas."""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
SLUG = "mathimatika_prosanatolismoy"
V2 = os.path.join(BASE, "data", "subjects", SLUG, "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))
fixed = 0

for q in v2:
    parts = q.get("question_html_parts", [])
    new_parts = []
    for p in parts:
        # Remove \left| ... \right| wrappers
        p = re.sub(r'\\left\|\s*([^|]+?)\s*\\right\|', r'\1', p)
        # Remove bare |...| wrappers inside LaTeX
        p = re.sub(r'\|\s*([a-zA-Z0-9_{}\\\^\']+?)\s*\|', r'\1', p)
        new_parts.append(p)
    if new_parts != parts:
        q["question_html_parts"] = new_parts
        q["question_html"] = "\n".join(new_parts)
        fixed += 1
        old_pipes = "\n".join(parts).count("|")
        new_pipes = "\n".join(new_parts).count("|")
        print(f"  Q{q['id']}: {old_pipes}→{new_pipes} pipes")

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)
print(f"\n✅ Fixed {fixed} questions")