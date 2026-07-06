#!/usr/bin/env python3
import json, re

v2 = json.load(open("data/subjects/mathimatika_prosanatolismoy/questions_v2.json", encoding="utf-8"))

affected = []
for q in v2:
    html = q.get("question_html", "")
    # Find $...$ formulas containing pipe characters
    formulas = re.findall(r"\$([^$]+)\$", html)
    pipe_f = [f for f in formulas if "|" in f and ("left" in f or "right" in f or f.count("|") >= 2)]
    if pipe_f:
        affected.append((q["id"], pipe_f))

print(f"Questions with pipe artifacts: {len(affected)}")
for qid, pipes in affected[:8]:
    print(f"\nQ{qid}:")
    for p in pipes[:4]:
        print(f"  ${p}$")