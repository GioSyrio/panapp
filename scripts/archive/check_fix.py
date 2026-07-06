#!/usr/bin/env python3
import json, re
v2 = json.load(open("data/subjects/mathimatika_prosanatolismoy/questions_v2.json", encoding="utf-8"))
q = next(x for x in v2 if x["id"] == 23209)
for i, p in enumerate(q.get("question_html_parts", [])):
    text = re.sub(r'<[^>]+>', ' ', p).strip()
    formulas = re.findall(r'\$([^$]+)\$', p)
    print(f'[{i}] {len(formulas)} formulas, text={text[:150]}')
    for f in formulas[:5]:
        print(f'   formula: {f[:80]}')
    print()