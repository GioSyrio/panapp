#!/usr/bin/env python3
"""
polish_subject.py — Safe content polishing tool for individual questions.

Usage:
    # Read a question
    python3 polish_subject.py --subject mathematics_prosanatolismoy --id 23196

    # Set a field
    python3 polish_subject.py --subject fysiki_prosanatolismoy --id 30504 --field question_html --set "..."
    python3 polish_subject.py --subject fysiki_prosanatolismoy --id 30504 --field answer_text --set "..."

    # Report issues
    python3 polish_subject.py --subject fysiki_prosanatolismoy --report

Safety: Auto-backup before every modification. Validates after changes.
"""
import json, os, sys, argparse, shutil, re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def load_subject_config(subject_id):
    with open(os.path.join(BASE, "subjects", f"{subject_id}.json"), encoding="utf-8") as f:
        return json.load(f)

def backup(v2_file):
    backup = f"{v2_file}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(v2_file, backup)
    print(f"📦 Backup: {os.path.basename(backup)}")

def main():
    p = argparse.ArgumentParser(description="Safe content polishing for individual questions")
    p.add_argument("--subject", required=True, help="Subject ID (e.g. fysiki_prosanatolismoy)")
    p.add_argument("--id", type=int, help="Question ID")
    p.add_argument("--field", help="Field to modify (question_html, answer_html, answer_text, question_text)")
    p.add_argument("--set", help="New value for the field")
    p.add_argument("--report", action="store_true", help="Report issues across all questions")
    args = p.parse_args()

    cfg = load_subject_config(args.subject)
    data_dir = os.path.join(BASE, cfg.get("data", {}).get("data_dir", f"data/subjects/{args.subject}"))
    v2_file = os.path.join(data_dir, "questions_v2.json")

    if not os.path.exists(v2_file):
        print(f"ERROR: {v2_file} not found")
        return

    with open(v2_file, encoding="utf-8") as f:
        data = json.load(f)

    # ── Report mode ──
    if args.report:
        print(f"📊 Subject: {args.subject} ({len(data)} questions)")
        empty_ans = 0
        empty_qhtml = 0
        llm_commentary = 0
        unbalanced_dollars = 0
        
        for q in data:
            qid = q.get("id", "?")
            if not q.get("answer_html", "").strip(): empty_ans += 1
            if not q.get("question_html", "").strip(): empty_qhtml += 1
            a_html = q.get("answer_html", "")
            if "Σημείωση" in a_html or "Υποθέτουμε ότι" in a_html: llm_commentary += 1
            if a_html.count("$") % 2 != 0: unbalanced_dollars += 1
            
            part = q.get("part", "?")
            tags = q.get("conceptual_tags", [])
            
        print(f"  Empty answer_html: {empty_ans}/{len(data)}")
        print(f"  Empty question_html: {empty_qhtml}/{len(data)}")
        print(f"  LLM commentary: {llm_commentary}")
        print(f"  Unbalanced $ in answers: {unbalanced_dollars}")
        return

    # ── Read mode ──
    if args.id and not args.field:
        q = next((x for x in data if x["id"] == args.id), None)
        if not q:
            print(f"❌ Question {args.id} not found")
            return
        print(f"Q{q['id']} ({q.get('part','')}, {q.get('year','')}, {q.get('points','')} pts)")
        for key in ["question_text", "question_html", "answer_text", "answer_html"]:
            val = q.get(key, "")
            if val:
                print(f"\n--- {key} ({len(val)} chars) ---")
                print(val[:500])
        return

    # ── Write mode ──
    if args.id and args.field and args.set is not None:
        backup(v2_file)
        q = next((x for x in data if x["id"] == args.id), None)
        if not q:
            print(f"❌ Question {args.id} not found")
            return
        
        allowed_fields = ["question_html", "answer_html", "answer_text", "question_text"]
        if args.field not in allowed_fields:
            print(f"❌ Invalid field: {args.field}. Allowed: {allowed_fields}")
            return
        
        old_val = q.get(args.field, "")[:100]
        q[args.field] = args.set
        with open(v2_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Q{args.id}.{args.field} updated")
        print(f"   Old: {old_val}...")
        print(f"   New: {args.set[:100]}...")
        
        # Quick validate
        if "$" in args.set:
            dollars = args.set.count("$")
            if dollars % 2 != 0:
                print(f"   ⚠️  Unbalanced $: {dollars}")
        return

    print("❌ Must specify --report, or --id with optional --field/--set")

if __name__ == "__main__":
    main()