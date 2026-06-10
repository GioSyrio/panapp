#!/usr/bin/env python3
"""
questions_classify_data.py — Offline Structural Classifier for Panhellenic Questions

Reads the raw questions JSON and tags each question with a deterministic
`"type"` field based on standard Panhellenic testing keywords and structural
markers. ZERO LLM processing required — purely rule-based.

Output: writes a new file `data/trapeza_data_1_3_218/questions_classified.json`
         with the same JSON structure plus the added `"type"` field.

Usage:
    python3 questions_classify_data.py
"""

import json
import os
import re
import sys
from collections import Counter

# ── Paths ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "trapeza_data_1_3_218")
INPUT_FILE = os.path.join(DATA_DIR, "questions.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "questions_classified.json")
BACKUP_FILE = os.path.join(DATA_DIR, "questions_classified.json.backup")

# ── Classification Rules (ordered by priority — first match wins) ─────────

def auto_detect_type(question_text):
    """
    Deterministic rule-based classification.
    Rules are ordered by specificity: more distinctive patterns checked first.
    """
    if not question_text:
        return "unknown"

    # Normalize for matching (preserve original for structural checks)
    qt_lower = question_text.lower()
    qt = question_text  # original case preserved

    # ── 1. Matching Table ─────────────────────────────────────────────
    # Distinct Στήλη Α / Στήλη Β structure
    if "Στήλη Α" in qt or "Στήλη Β" in qt or "ΣΤΗΛΗ Α" in qt or "ΣΤΗΛΗ Β" in qt:
        return "matching_table"

    # ── 2. True / False ───────────────────────────────────────────────
    # Questions asking to mark statements as Σωστό/Λάθος
    if re.search(r'(Σωστό|ΣΩΣΤΟ).*(Λάθος|ΛΑΘΟΣ)|(Λάθος|ΛΑΘΟΣ).*(Σωστό|ΣΩΣΤΟ)', qt):
        return "true_false"
    # "χαρακτηρίσετε ... ως Σωστή ή Λανθασμένη"
    if re.search(r'χαρακτηρίσετε.*(Σωστ|Λανθασμέν)|(Σωστή|Λάθος).*πρόταση.*(Σωστή|Λάθος)', qt, re.IGNORECASE):
        return "true_false"

    # ── 3. Gap Fill (συμπλήρωση κενών) ────────────────────────────────
    # Distinct markers: …1…, …2…, —1—, —2—, ..[1].., _1_
    if re.search(r'…\d+…|—\d+—|\.\.\[\d+\]\.\.|_\d+_', qt):
        return "gap_fill"
    # Questions explicitly asking to fill blanks
    if re.search(r'(συμπληρώσετε|συμπληρώστε|να συμπληρωθ|κενά|κενών)', qt, re.IGNORECASE):
        # But exclude questions that just mention κενά in passing
        if re.search(r'…\d+…|—\d+—|\.\.\[\d+\]\.\.', qt) or \
           re.search(r'(συμπληρώσετε|συμπληρώστε).*(κενά|κενά|όρους|λέξεις|φράσεις)', qt, re.IGNORECASE):
            return "gap_fill"
        # "Να συμπληρώσετε τους όρους που λείπουν" etc.
        if re.search(r'όρους που λείπουν|λέξεις που λείπουν|φράσεις που λείπουν|τιμές που λείπουν', qt, re.IGNORECASE):
            return "gap_fill"

    # ── 4. Code Structural Conversion ─────────────────────────────────
    # Converting one loop/multi-select structure to another
    code_conversion_keywords = [
        r'μετατρέψετε|μετατραπεί|μετατροπή',
        r'ισοδύναμο|ισοδύναμη|ισοδύναμες',
        r'αντικαθιστώντας|αντικαταστήσετε',
    ]
    loop_keywords = [r'ΟΣΟ|ΓΙΑ|ΜΕΧΡΙΣ_ΟΤΟΥ|ΕΠΙΛΕΞΕ|ΑΝ\b']
    multi_sel_keywords = [r'ΕΠΙΛΕΞΕ|ΠΕΡΙΠΤΩΣΗ|ΤΕΛΟΣ_ΕΠΙΛΟΓΩΝ|ΑΝ\b.*ΑΛΛΙΩΣ_ΑΝ']

    has_conv = any(re.search(kw, qt, re.IGNORECASE) for kw in code_conversion_keywords)
    has_loop = any(re.search(kw, qt) for kw in loop_keywords)
    has_msel = any(re.search(kw, qt) for kw in multi_sel_keywords)

    if has_conv and (has_loop or has_msel):
        return "code_conversion"

    # ── 5. Flowchart / Diagram Conversion ─────────────────────────────
    # Ask to draw or convert a flowchart/diagram
    if re.search(r'διάγραμμα ροής|διάγραμμα|διάγραμματος', qt, re.IGNORECASE):
        return "diagram_flow"

    # ── 6. Algorithm Trace (dry run) ──────────────────────────────────
    # "Τι θα εμφανίσει", "να εκτελέσετε το παρακάτω", "πίνακας τιμών"
    if re.search(r'(θα εμφανίσει|θα εμφανιστεί|πίνακα.*τιμών|ίχνος.*πίνακα|τιμές των μεταβλητών)', qt, re.IGNORECASE):
        return "algorithm_trace"
    # "να παρουσιάσετε ... τιμές", "να γράψετε την τιμή"
    if re.search(r'(να παρουσιάσετε.*τιμές|να γράψετε.*τιμή.*παίρνει)', qt, re.IGNORECASE):
        return "algorithm_trace"

    # ── 7. Explain / Analyze Concept ──────────────────────────────────
    # "να αιτιολογήσετε", "να εξηγήσετε", "να αναφέρετε"
    if re.search(r'αιτιολογήσετε|εξηγήσετε|αναφέρετε.*λόγο', qt, re.IGNORECASE):
        return "explain_concept"

    # ── 8. Open-Ended Problem (programming / algorithm writing) ───────
    # Fallback: any question not matching above patterns
    return "open_ended_problem"


# ── Main ─────────────────────────────────────────────────────────────────

def classify_all(input_path, output_path):
    """Load input JSON, classify every question, write output JSON."""
    if not os.path.exists(input_path):
        print(f"ERROR: {input_path} not found.")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("ERROR: Expected a JSON array of questions.")
        sys.exit(1)

    type_counts = Counter()
    classified = []

    for item in data:
        qt = item.get("question_text", "")
        qtype = auto_detect_type(qt)
        item["type"] = qtype
        type_counts[qtype] += 1
        classified.append(item)

    # ── Backup existing output if present ──────────────────────────────
    if os.path.exists(output_path):
        if os.path.exists(BACKUP_FILE):
            os.remove(BACKUP_FILE)
        os.rename(output_path, BACKUP_FILE)
        print(f"  📦 Previous classified file backed up to {os.path.basename(BACKUP_FILE)}")

    # ── Write output ───────────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(classified, f, ensure_ascii=False, indent=2)

    # ── Report ─────────────────────────────────────────────────────────
    total = len(classified)
    print(f"\n✅ Classification complete! {total} questions processed.\n")
    print(f"{'Type':<25} {'Count':>6}  {'%':>6}")
    print("-" * 40)
    for qtype, count in type_counts.most_common():
        pct = count * 100 / total
        print(f"{qtype:<25} {count:>6}  {pct:>5.1f}%")
    print("-" * 40)
    print(f"{'TOTAL':<25} {total:>6}  {'100.0%':>6}")
    print(f"\n  Output: {output_path}")

    return classified


if __name__ == "__main__":
    print("🔍 Panhellenic Questions Structural Classifier")
    print(f"   Input:  {INPUT_FILE}")
    print(f"   Output: {OUTPUT_FILE}")
    print()
    classify_all(INPUT_FILE, OUTPUT_FILE)