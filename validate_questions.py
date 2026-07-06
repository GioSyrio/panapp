#!/usr/bin/env python3
"""
validate_questions.py — Smoke test for questions_v2.json quality.
Run after any data change to catch regressions.

Usage:
    python3 validate_questions.py
    python3 validate_questions.py --subject mathematics
"""
import json, os, re, sys, argparse

BASE = os.path.dirname(os.path.abspath(__file__))

def validate(subject_id="mathematics"):
    cfg_path = os.path.join(BASE, "subjects", f"{subject_id}.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(BASE, "subjects", "mathematics_prosanatolismoy.json")
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    
    data_dir = os.path.join(BASE, cfg.get("data", {}).get("data_dir", f"data/subjects/{subject_id}"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    
    if not os.path.exists(v2_file):
        print(f"❌ File not found: {v2_file}")
        return False
    
    data = json.load(open(v2_file, encoding="utf-8"))
    print(f"📋 Validating {len(data)} questions in {subject_id}")
    
    errors = 0
    warnings = 0
    
    for q in data:
        qid = q.get("id", "?")
        
        # 1. Required fields
        for field in ["id", "year", "part", "points", "question_html", "answer_html", "hints", "sections"]:
            if field not in q:
                print(f"  ❌ q{qid}: missing field '{field}'")
                errors += 1
        
        # 2. question_html $ balance
        q_html = q.get("question_html", "")
        q_dollars = q_html.count("$")
        if q_dollars > 0 and q_dollars % 2 != 0:
            print(f"  ❌ q{qid}: question_html has unbalanced $: {q_dollars}")
            errors += 1
        
        # 3. answer_html $ balance
        a_html = q.get("answer_html", "")
        a_dollars = a_html.count("$")
        if a_dollars > 0 and a_dollars % 2 != 0:
            print(f"  ❌ q{qid}: answer_html has unbalanced $: {a_dollars}")
            errors += 1
        
        # 4. Empty answer check
        if not a_html.strip():
            print(f"  ⚠️ q{qid}: empty answer_html")
            warnings += 1
        
        # 5. LLM commentary check
        if "Σημείωση" in a_html or "Υποθέτουμε ότι" in a_html:
            print(f"  ⚠️ q{qid}: answer_html contains LLM commentary")
            warnings += 1
        
        # 6. Gap pattern check (double spaces in question)
        if "  " in q_html and 'text-content' in q_html:
            gap_count = len(re.findall(r'\s{2,}', q_html))
            if gap_count > 2:
                print(f"  ⚠️ q{qid}: question_html has {gap_count} gap patterns")
                warnings += 1
        
        # 7. Hints match sub-questions
        subqs = [s for s in q.get("sections", []) if s.get("type") == "sub_question"]
        hints = q.get("hints", [])
        if subqs and len(hints) != len(subqs):
            print(f"  ⚠️ q{qid}: {len(hints)} hint groups vs {len(subqs)} sub-questions")
            warnings += 1
        
        # 8. Hint levels check
        for i, h in enumerate(hints):
            h_count = len(h.get("hints", []))
            if h_count == 0:
                print(f"  ⚠️ q{qid}: hints[{i}] has 0 hint levels")
                warnings += 1
            elif h_count < 3:
                print(f"  ⚠️ q{qid}: hints[{i}] has only {h_count} hint levels (expected 3)")
                warnings += 1
        
        # 9. Answer/question function match
        a_html = q.get("answer_html", "")
        q_funcs = set(re.findall(r'f\(x\)\s*=\s*[\$\s]*([^\$\n<]+?)(?:\$|\.|,|<)', q_html))
        a_funcs = set(re.findall(r'f\(x\)\s*=\s*[\$\s]*([^\$\n<]+?)(?:\$|\.|,|<)', a_html))
        q_norm = {re.sub(r'\s+','',f.strip()) for f in q_funcs if len(f.strip())>2}
        a_norm = {re.sub(r'\s+','',f.strip()) for f in a_funcs if len(f.strip())>2}
        if q_norm and a_norm and not (q_norm & a_norm):
            print(f"  ⚠️ q{qid}: ANSWER MISMATCH — Q f(x)={q_norm}, A f(x)={a_norm}")
            warnings += 1
        
        # 10. question_html_parts consistency
        parts = q.get("question_html_parts", [])
        if parts:
            rebuilt = "\n".join(parts)
            if rebuilt != q_html:
                print(f"  ⚠️ q{qid}: question_html_parts out of sync with question_html")
                warnings += 1
    
    # Summary
    print(f"\n{'='*50}")
    no_math = sum(1 for q in data if "$" not in q.get("question_html", ""))
    balanced_answers = sum(1 for q in data if q.get("answer_html", "").count("$") % 2 == 0)
    
    print(f"  Questions: {len(data)}")
    print(f"  With math in question_html: {len(data) - no_math}/{len(data)}")
    print(f"  Without math: {no_math}/{len(data)}")
    print(f"  Balanced answers: {balanced_answers}/{len(data)}")
    print(f"  Errors: {errors}")
    print(f"  Warnings: {warnings}")
    
    if errors == 0 and warnings == 0:
        print(f"\n✅ ALL CHECKS PASSED")
        return True
    elif errors == 0:
        print(f"\n⚠️  {warnings} warnings (acceptable)")
        return True
    else:
        print(f"\n❌ {errors} errors found")
        return False

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--subject", default="mathematics_prosanatolismoy")
    args = p.parse_args()
    sys.exit(0 if validate(args.subject) else 1)