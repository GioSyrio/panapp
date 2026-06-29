#!/usr/bin/env python3
"""
repair_hints.py — Repair hint progress after DOCX section fix

For each new subject (10 total):
  1. Restores progress tracker from existing hints in questions_v2.json
  2. Marks sub-questions WITH hints as "done" → won't regenerate
  3. Marks sub-questions WITHOUT hints as NOT done → will regenerate when build_llm_hints runs
  4. Generates missing hints using the LLM (fills only the gaps)

Usage:
    python3 repair_hints.py --slug fysiki_prosanatolismoy
    python3 repair_hints.py --all
"""

import json, os, sys, time, argparse
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PROTECTED_SLUGS = {"mathematics", "informatics", "mathimatika_prosanatolismoy", "pliroforiki"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="fysiki_prosanatolismoy")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all:
        slugs = [d for d in os.listdir(os.path.join(BASE, "data", "subjects"))
                 if os.path.isdir(os.path.join(BASE, "data", "subjects", d))
                 and d not in PROTECTED_SLUGS and not d.startswith(".")]
    else:
        slugs = [args.slug]

    for slug in slugs:
        data_dir = os.path.join(BASE, "data", "subjects", slug)
        v2_path = os.path.join(data_dir, "questions_v2.json")
        prog_path = os.path.join(data_dir, "llm_hints_progress.json")

        if not os.path.exists(v2_path):
            print(f"  ❌ {slug}: no questions_v2.json")
            continue

        with open(v2_path, encoding="utf-8") as f:
            v2 = json.load(f)

        # Reconstruct progress based on ACTUAL hints present
        completed = []
        missing_subqs = 0
        total_subqs = 0
        questions_with_missing = 0

        for q in v2:
            qid = q["id"]
            subqs = [s for s in q.get("sections", []) if s["type"] == "sub_question"]
            hints = q.get("hints", [])

            if not subqs:
                # No sub-questions detected — mark as complete to skip
                completed.append(f"{qid}_0")
                continue

            total_subqs += len(subqs)

            # Check each sub-question for hints
            has_missing = False
            for si, sq in enumerate(subqs):
                if si < len(hints) and hints[si].get("hints") and len(hints[si]["hints"]) > 0:
                    # This sub-question has hints → mark complete
                    completed.append(f"{qid}_{si}")
                else:
                    # Missing hints → leave out of completed
                    missing_subqs += 1
                    has_missing = True

            if has_missing:
                questions_with_missing += 1

        # Save reconstructed progress
        progress = {"completed": completed}

        if args.dry_run:
            in_progress = total_subqs - missing_subqs
            pct = int(in_progress * 100 / max(total_subqs, 1))
            print(f"  {slug}: {len(v2)} qs, {total_subqs} subqs, {in_progress} done ({pct}%), {missing_subqs} gaps ({questions_with_missing} qs)")
        else:
            with open(prog_path, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
            in_progress = total_subqs - missing_subqs
            pct = int(in_progress * 100 / max(total_subqs, 1))
            print(f"  ✅ {slug}: {in_progress}/{total_subqs} hints complete ({pct}%) — {missing_subqs} gaps")

    if args.dry_run:
        print(f"\n[DRY RUN] Run without --dry-run to repair progress files")
        print(f"After repair, run: python3 build_llm_hints.py --subject <slug> to fill gaps")

if __name__ == "__main__":
    main()