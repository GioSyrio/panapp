#!/usr/bin/env python3
"""
LLM-based Greek text correction for questions.json.

Uses DeepSeek-chat to fix corrupted Greek accents, typos, and encoding artifacts
in question_text and answer_text fields.

Features:
- Incremental saves (every 5 questions)
- Uses deepseek-chat (fast, no reasoning overhead)
- Handles reasoning model output cleanup
- Resume support via progress file

Usage: DEEPSEEK_API_KEY=sk-... python3 fix_greek_with_llm.py
"""

import json
import os
import sys
import re
import time
import signal
from collections import defaultdict

from openai import OpenAI

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "trapeza_data_1_3_218")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
PROGRESS_FILE = os.path.join(DATA_DIR, "fix_progress.json")
BACKUP_FILE = QUESTIONS_FILE + ".backup"

# Known patterns that indicate corrupted Greek text
CORRUPT_MARKERS = [
    'Τζλοσ', 'αλγόρικμ', 'ψευδογλϊςςα', 'αλλιϊσ', '΢', 'ϊσ ',
    'μζχρι', 'μζςο', 'ϋχει', 'ϋχουν', 'λφςθ', 'αμζςωσ',
    'εκτελζςιμο', 'τθ δομι', 'τθσ δομισ', 'ιςοδφναμθ',
    'κριτιρια', 'τμιμα', 'πρζπει', 'ζνασ', 'ι ',
    'παραβιάηεται', 'κακορι', 'περατότθ', 'Δφο ',
    'ςτοιχείο', 'αντιςτοιχ', 'περιςςεφουν',
    'ακολουκία', 'μεταβλθτισ', 'μεταβλθτϊν',
    'πλικοσ', 'αρικμό', 'προςπακιςετε', 'Περίπτωσθ',
    'αντικακ', 'ΕΡΙΛΕΞ', 'γραμμζνο', 'αποκθκευμζνο',
    'ΓΛΩ΢΢Α', 'διάβαςε', 'εμφάνιςε', 'τφπωσε',
]

SYSTEM_PROMPT = """You are a Greek language expert and OCR corrector.

You will receive Greek text extracted from PDFs. Some characters may be:
- Corrupted (wrong glyph-to-Unicode mappings)
- Missing accents (τόνος)
- Using final sigma (ς) where medial sigma (σ) should be, or vice versa
- Having swapped Greek letters

Your task:
1. Fix ALL corrupted Greek letters to their correct form
2. Add missing accents (τόνους) where Greek grammar requires them
3. Fix final/medial sigma usage (ς at word end, σ elsewhere)
4. Preserve ALL pseudocode/ΓΛΩΣΣΑ keywords exactly as they should appear
5. Do NOT change any content, meaning, structure, line breaks, or numbers
6. Do NOT add or remove any text — only fix character-level errors
7. Return ONLY the corrected text with no explanations, no markdown, no quotes

The text may contain Greek pseudocode (ΓΛΩΣΣΑ) with keywords like:
ΑΡΧΗ, ΤΕΛΟΣ, ΔΙΑΒΑΣΕ, ΓΡΑΨΕ, ΕΜΦΑΝΙΣΕ, ΑΝ, ΤΟΤΕ, ΑΛΛΙΩΣ, ΑΛΛΙΩΣ_ΑΝ,
ΟΣΟ, ΕΠΑΝΑΛΑΒΕ, ΜΕΧΡΙΣ_ΟΤΟΥ, ΓΙΑ, ΑΠΟ, ΜΕΧΡΙ, ΜΕ_ΒΗΜΑ,
ΕΠΙΛΕΞΕ, ΠΕΡΙΠΤΩΣΗ, ΤΕΛΟΣ_ΕΠΙΛΟΓΩΝ, ΤΕΛΟΣ_ΑΝ, ΤΕΛΟΣ_ΕΠΑΝΑΛΗΨΗΣ,
ΠΡΟΓΡΑΜΜΑ, ΜΕΤΑΒΛΗΤΕΣ, ΑΚΕΡΑΙΕΣ, ΠΡΑΓΜΑΤΙΚΕΣ, ΧΑΡΑΚΤΗΡΕΣ,
ΣΤΑΘΕΡΕΣ, ΑΡΧΗ_ΕΠΑΝΑΛΗΨΗΣ, ΚΑΛΕΣΕ, ΔΙΑΔΙΚΑΣΙΑ, ΣΥΝΑΡΤΗΣΗ"""


def count_greek_errors(text):
    """Count how many corrupted patterns exist in the text."""
    count = 0
    for marker in CORRUPT_MARKERS:
        count += text.count(marker)
    # Private Use Area chars
    count += sum(1 for c in text if 0xE000 <= ord(c) <= 0xF8FF)
    return count


def clean_llm_output(text):
    """Strip reasoning/think tags and markdown wrapping that the model may add."""
    # Remove  blocks (some reasoning models wrap in this)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Remove markdown code fences
    text = re.sub(r'^```[^\n]*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    # Remove surrounding quotes
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return text.strip()


def fix_with_llm(client, text, max_retries=2):
    """Send text to DeepSeek for Greek correction."""
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Please correct the Greek text below:\n\n{text}"},
                ],
                temperature=0.0,
                max_tokens=8000,
                timeout=60,
            )
            result = response.choices[0].message.content
            if result is None:
                print(f"    (attempt {attempt+1}: null response)")
                time.sleep(2)
                continue
            cleaned = clean_llm_output(result)
            if len(cleaned) < 10 and len(text) > 50:
                print(f"    (attempt {attempt+1}: output too short, raw: {result[:100]!r})")
                time.sleep(2)
                continue
            return cleaned
        except Exception as e:
            print(f"    (attempt {attempt+1}: {e})")
            time.sleep(2)
    return None


def verify_fix(original, fixed):
    """Check that the fix didn't change structure drastically."""
    if fixed is None:
        return False
    len_ratio = len(fixed) / max(len(original), 1)
    if len_ratio < 0.6 or len_ratio > 1.4:
        return False
    if len(original) > 100 and len(fixed) < 20:
        return False
    return True


def load_progress():
    """Load set of already-processed question IDs."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("processed_ids", []))
    return set()


def save_progress(processed_ids):
    """Save progress to resume later."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"processed_ids": list(processed_ids)}, f)


def main():
    print("=" * 60)
    print("  Greek Text Fixer — DeepSeek-Chat LLM")
    print("=" * 60)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set.")
        print("Usage: DEEPSEEK_API_KEY=sk-... python3 fix_greek_with_llm.py")
        return

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Load questions
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        questions = json.load(f)

    # Create backup
    if not os.path.exists(BACKUP_FILE):
        import shutil
        shutil.copy2(QUESTIONS_FILE, BACKUP_FILE)
        print(f"  Backup saved to {BACKUP_FILE}")

    # Resume support
    processed_ids = load_progress()
    if processed_ids:
        print(f"  Resuming — {len(processed_ids)} questions already processed")
        # Apply previous fixes from progress
        already_fixed = 0
        for q in questions:
            if q["id"] in processed_ids:
                # Re-count — maybe already clean
                qe = count_greek_errors(q["question_text"])
                ae = count_greek_errors(q.get("answer_text", ""))
                if qe + ae == 0:
                    already_fixed += 1
        if already_fixed > 0:
            print(f"  {already_fixed} previously-fixed questions are now clean")

    # Analyze which need fixing
    needs_fix = []
    for q in questions:
        if q["id"] in processed_ids:
            # Recheck if still has errors
            q_errors = count_greek_errors(q["question_text"])
            a_errors = count_greek_errors(q.get("answer_text", ""))
            if q_errors + a_errors == 0:
                continue
        q_errors = count_greek_errors(q["question_text"])
        a_errors = count_greek_errors(q.get("answer_text", ""))
        total = q_errors + a_errors
        if total > 0:
            needs_fix.append((q["id"], total, q_errors, a_errors))

    needs_fix.sort(key=lambda x: -x[1])

    if not needs_fix:
        print("\n  All questions are already clean! ✓")
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        return

    print(f"\n  Questions needing fixes: {len(needs_fix)} / {len(questions)}")
    print(f"  {'ID':>6}  {'Total':>6}  {'Q_Err':>6}  {'A_Err':>6}")
    print(f"  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}")
    for qid, total, qe, ae in needs_fix[:20]:
        print(f"  {qid:>6}  {total:>6}  {qe:>6}  {ae:>6}")
    if len(needs_fix) > 20:
        print(f"  ... and {len(needs_fix) - 20} more")

    # Confirmation
    print(f"\n  About to fix {len(needs_fix)} questions using DeepSeek.")
    if "--dry-run" in sys.argv:
        print("  DRY RUN — no changes will be made.")
        return
    choice = input("  Continue? (y/n): ").strip().lower()
    if choice != 'y':
        print("  Aborted.")
        return

    # Process
    fixed_count = 0
    failed_count = 0
    id_to_q = {q["id"]: q for q in questions}
    SAVE_EVERY = 5  # Incremental save every N questions

    # Graceful shutdown handler
    def save_and_exit(signum=None, frame=None):
        print(f"\n\n  Interrupted! Saving progress...")
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        save_progress(processed_ids)
        print(f"  Progress saved. Run again to resume.")
        print(f"  Fixed so far: {fixed_count} | Failed: {failed_count}")
        sys.exit(0)

    signal.signal(signal.SIGINT, save_and_exit)
    signal.signal(signal.SIGTERM, save_and_exit)

    for i, (qid, total, qe, ae) in enumerate(needs_fix):
        q = id_to_q[qid]
        print(f"\n  [{i+1}/{len(needs_fix)}] id={qid} ({total} errors)")

        modified = False

        # Fix question_text
        if qe > 0:
            print(f"    Fixing question_text ({qe} errors, {len(q['question_text'])} chars)...")
            fixed_q = fix_with_llm(client, q["question_text"])
            if verify_fix(q["question_text"], fixed_q):
                new_errors = count_greek_errors(fixed_q)
                if new_errors < qe:
                    q["question_text"] = fixed_q
                    modified = True
                    print(f"    ✓ question_text fixed ({qe} → {new_errors} errors)")
                else:
                    print(f"    ✗ question_text — errors not reduced ({qe} → {new_errors}), keeping original")
                    failed_count += 1
            else:
                print(f"    ✗ question_text verification failed — kept original")
                failed_count += 1
            time.sleep(0.3)

        # Fix answer_text
        if ae > 0:
            print(f"    Fixing answer_text ({ae} errors, {len(q.get('answer_text', ''))} chars)...")
            fixed_a = fix_with_llm(client, q.get("answer_text", ""))
            if verify_fix(q.get("answer_text", ""), fixed_a):
                new_errors = count_greek_errors(fixed_a)
                if new_errors < ae:
                    q["answer_text"] = fixed_a
                    modified = True
                    print(f"    ✓ answer_text fixed ({ae} → {new_errors} errors)")
                else:
                    print(f"    ✗ answer_text — errors not reduced ({ae} → {new_errors}), keeping original")
                    failed_count += 1
            else:
                print(f"    ✗ answer_text verification failed — kept original")
                failed_count += 1
            time.sleep(0.3)

        if modified:
            fixed_count += 1
        processed_ids.add(qid)

        # Incremental save
        if (i + 1) % SAVE_EVERY == 0:
            print(f"    [Saving checkpoint at {i+1}/{len(needs_fix)}...]")
            with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)
            save_progress(processed_ids)

    # Final save
    print(f"\n  {'='*60}")
    print(f"  Final save...")
    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    save_progress(processed_ids)

    print(f"  Fixed: {fixed_count} | Failed: {failed_count}")
    print(f"  Saved to {QUESTIONS_FILE}")
    print(f"  {'='*60}")

    # Re-analyze
    remaining = sum(
        count_greek_errors(q["question_text"]) + count_greek_errors(q.get("answer_text", ""))
        for q in questions
    )
    print(f"\n  Errors remaining after fix: {remaining}")
    if remaining == 0:
        print("  All Greek text is clean! ✓")
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
    else:
        still_bad = [q["id"] for q in questions
                     if count_greek_errors(q["question_text"]) + count_greek_errors(q.get("answer_text", "")) > 0]
        print(f"  Questions still needing fixes: {len(still_bad)}")
        if len(still_bad) <= 10:
            print(f"  IDs: {still_bad}")


if __name__ == "__main__":
    main()