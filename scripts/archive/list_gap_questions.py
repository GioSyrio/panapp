#!/usr/bin/env python3
"""List all gap questions with their parts for manual review."""
import json, re

v2 = json.load(open("data/subjects/mathimatika_prosanatolismoy/questions_v2.json", encoding="utf-8"))

gapped = []
for q in v2:
    parts = q.get("question_html_parts", [])
    has_gap = any(len(re.findall(r'\s{2,}', re.sub(r'<[^>]+>', ' ', p).strip())) >= 2 
                  for p in parts if 'class="subq"' in p)
    if has_gap:
        gapped.append(q["id"])

print(f"Gap questions: {len(gapped)}")
for qid in sorted(gapped):
    print(f"  {qid}")
print()

# Show the first 5 in detail
for qid in sorted(gapped)[:5]:
    q = next(x for x in v2 if x["id"] == qid)
    print(f"=== Q{qid} ===")
    for i, p in enumerate(q.get("question_html_parts", [])):
        text = re.sub(r'<[^>]+>', ' ', p).strip()
        gaps = len(re.findall(r'\s{2,}', text))
        if gaps > 0:
            print(f"  [{i}] gaps={gaps} | {text[:120]}")
    print()