#!/usr/bin/env python3
"""Diagnose math subject issues: |..| patterns, missing/misplaced formulas"""
import json, re, os

BASE = os.path.dirname(os.path.abspath(__file__))
SLUG = "mathimatika_prosanatolismoy"
V2 = os.path.join(BASE, "data", "subjects", SLUG, "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))

flagged = [24130, 23312, 23216, 23209, 36827, 28684, 29549, 36838, 28477, 29646, 34151]

print("=" * 80)
print("ISSUE 1: |..| pipe patterns (absolute value / vector notation artifacts)")
print("=" * 80)

for qid in flagged:
    q = next((x for x in v2 if x["id"] == qid), None)
    if not q: continue
    parts = q.get("question_html_parts", [])
    found_pipes = False
    for i, p in enumerate(parts):
        # Check for pipe chars that are NOT LaTeX delimiters ($...$)
        text = re.sub(r'<[^>]+>', ' ', p).strip()
        pipe_count = text.count("|")
        if pipe_count > 2:
            if not found_pipes:
                found_pipes = True
            # Extract actual formulas with pipes
            formulas = re.findall(r'\$([^$]+)\$', p)
            pipe_formulas = [f for f in formulas if "|" in f or "arrowvert" in f or "mid" in f]
            if pipe_formulas:
                print(f"  Q{qid} part[{i}]: {len(pipe_formulas)} formulas with |")
                for f in pipe_formulas[:3]:
                    print(f"    ${f[:100]}$")
    if not found_pipes:
        pass  # Question was flagged but no pipes found

print()
print("=" * 80)
print("ISSUE 2: Missing formulas (gap analysis)")
print("=" * 80)

for qid in flagged:
    q = next((x for x in v2 if x["id"] == qid), None)
    if not q: continue
    parts = q.get("question_html_parts", [])
    for i, p in enumerate(parts):
        if 'class="subq"' not in p:
            continue
        # Extract subq text content
        text_match = re.search(r'class="subq-text">([^<]*)</span>', p)
        if not text_match:
            continue
        text = text_match.group(1).strip()
        formulas_in_part = re.findall(r'\$([^$]+)\$', p)
        # Count "  " (double spaces) as formula gaps
        gaps = len(re.findall(r'  +', text))
        if gaps >= 2 and len(formulas_in_part) < gaps:
            print(f"  Q{qid} part[{i}]: {gaps} gaps, only {len(formulas_in_part)} formulas")
            print(f"    text: {text[:150]}")

print()
print("=" * 80)
print("ISSUE 3: Formula placement audit (description vs subq)")
print("=" * 80)

for qid in flagged:
    q = next((x for x in v2 if x["id"] == qid), None)
    if not q: continue
    parts = q.get("question_html_parts", [])
    desc_formulas = []
    subq_formulas = []
    for i, p in enumerate(parts):
        if 'class="text-content"' in p and i <= 2:  # First 3 text parts = description
            desc_formulas.extend(re.findall(r'\$([^$]+)\$', p))
        elif 'class="subq"' in p:
            subq_formulas.extend(re.findall(r'\$([^$]+)\$', p))
    if len(desc_formulas) > 10:
        print(f"  Q{qid}: {len(desc_formulas)} formulas in description (={len(subq_formulas)} in subqs)")
        print(f"    Description: {[f[:60] for f in desc_formulas[:5]]}")

print()
print("=" * 80)
print("SUMMARY: Count of affected questions across ALL math")
print("=" * 80)

piped = 0
gapped = 0
misplaced = 0
for q in v2:
    parts = q.get("question_html_parts", [])
    # Check for pipes
    has_pipe = any("|" in re.sub(r'<[^>]+>', ' ', p).strip() for p in parts 
                   if re.sub(r'<[^>]+>', ' ', p).strip().count("|") > 2)
    if has_pipe: piped += 1
    
    # Check for gaps
    for p in parts:
        if 'class="subq"' not in p: continue
        m = re.search(r'class="subq-text">([^<]*)</span>', p)
        if not m: continue
        t = m.group(1).strip()
        gaps = len(re.findall(r'  +', t))
        formulas = len(re.findall(r'\$([^$]+)\$', p))
        if gaps >= 2 and formulas < gaps:
            gapped += 1
            break
    
    # Misplacement
    desc_formulas = []
    subq_formulas = []
    for i, p in enumerate(parts):
        if 'class="text-content"' in p and i <= 2:
            desc_formulas.extend(re.findall(r'\$([^$]+)\$', p))
        elif 'class="subq"' in p:
            subq_formulas.extend(re.findall(r'\$([^$]+)\$', p))
    if len(desc_formulas) > 10 and len(subq_formulas) < len(desc_formulas):
        misplaced += 1

total = len(v2)
print(f"  Pipe patterns: {piped}/{total} ({piped*100//total}%)")
print(f"  Missing formulas in subq: {gapped}/{total} ({gapped*100//total}%)")
print(f"  Misplaced formulas: {misplaced}/{total} ({misplaced*100//total}%)")