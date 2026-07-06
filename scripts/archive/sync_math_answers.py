#!/usr/bin/env python3
"""Sync polished answer_html from mathematics/ to mathimatika_prosanatolismoy/"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
src = json.load(open(os.path.join(BASE, "data/subjects/mathematics/questions_v2.json"), encoding="utf-8"))
dst = json.load(open(os.path.join(BASE, "data/subjects/mathimatika_prosanatolismoy/questions_v2.json"), encoding="utf-8"))

# Build lookup from source
src_map = {q["id"]: q.get("answer_html", "") for q in src}

synced = 0
for q in dst:
    qid = q["id"]
    if qid in src_map and src_map[qid]:
        old = q.get("answer_html", "")
        new = src_map[qid]
        if len(new) > len(old) or "sol-step" in new:
            q["answer_html"] = new
            synced += 1
            print(f"  Q{qid}: synced ({len(old)}→{len(new)} chars, {new.count('$')//2} LaTeX)")

with open(os.path.join(BASE, "data/subjects/mathimatika_prosanatolismoy/questions_v2.json"), "w", encoding="utf-8") as f:
    json.dump(dst, f, ensure_ascii=False, indent=2)

print(f"\n✅ Synced {synced} answers")