#!/usr/bin/env python3
"""
classify_physics_tags.py — Rule-based conceptual_tags for Physics questions.
No API cost — uses keyword matching from question_text.

Usage:
    python3 classify_physics_tags.py
    python3 classify_physics_tags.py --subject fysiki_prosanatolismoy
"""
import json, os, re, argparse, shutil
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

# Topic definitions: (tag_name, regex_patterns)
TOPICS = [
    ("1.1 Μηχανική — Κινηματική", [
        r'\bκινηματ', r'\bταχύτητα\b', r'\bεπιτάχυνση\b', r'\bμετατόπιση\b',
        r'\bευθύγραμμη\s+ομαλή\b', r'\bομαλά\s+επιταχυνόμενη\b',
    ]),
    ("1.2 Μηχανική — Δυνάμεις & Νόμοι Νεύτωνα", [
        r'\bνεύτων', r'\bνόμοι?\s+(του\s+)?νεύτων',
        r'\bδύναμη\b', r'\bσυνισταμένη\b', r'\bτριβή\b', r'\bβάρος\b',
        r'\bισορροπία\b', r'\bελεύθερη\s+πτώση\b',
    ]),
    ("1.3 Μηχανική — Κρούσεις & Ορμή", [
        r'\bκρούση\b', r'\bκρούσεις\b', r'\bορμή\b', r'\bελαστική\b',
        r'\bανελαστική\b', r'\bπλαστική\b', r'\bκεντρική\b',
    ]),
    ("2.1 Ταλαντώσεις", [
        r'\bταλάντωση\b', r'\bταλαντώσεις\b', r'\bταλαντωτή\b',
        r'\bελατήρι', r'\bαπλή\s+αρμονική\b', r'\bΑ\.Α\.Τ\.',
        r'\bπλάτος\b', r'\bπερίοδο\b', r'\bσυχνότητα\b',
        r'\bσταθερά\s+επαναφοράς\b', r'\bD\s*=\s*', r'\bκ\s*=\s*',
    ]),
    ("2.2 Κύματα", [
        r'\bκύμα\b', r'\bκύματος\b', r'\bκυμάτων\b', r'\bμήκος\s+κύματος\b',
        r'\bσυχνότητα\b', r'\bφάση\b', r'\bαρμονικό\s+κύμα\b',
        r'\bεξίσωση\s+κύματος\b', r'\bsin\s*\(', r'\bταχύτητα\s+διάδοσης\b',
    ]),
    ("3.1 Ηλεκτρικό Πεδίο & Δυναμικό", [
        r'\bηλεκτρικό\s+πεδίο\b', r'\bηλεκτρική\s+δύναμη\b',
        r'\bcoulomb\b', r'\bδυναμικό\b', r'\bένταση\s+(του\s+)?πεδίου\b',
        r'\bφορτίο\b', r'\bηλεκτρόνιο\b', r'\bπρωτόνιο\b',
        r'\bπυκνωτή\b', r'\bχωρητικότητα\b',
    ]),
    ("3.2 Ηλεκτρομαγνητισμός & Επαγωγή", [
        r'\bμαγνητικ', r'\bεπαγωγή\b', r'\bεπαγωγική\b',
        r'\bμαγνητική\s+ροή\b', r'\bηλεκτρομαγν', r'\bfaraday\b',
        r'\blenz\b', r'\bπηνίο\b', r'\bσωληνοειδές\b',
        r'\bρεύμα\b', r'\bαντίσταση\b', r'\bωμική\b', r'\bohm\b',
        r'\bκύκλωμα\b', r'\bσε\s+σειρά\b', r'\bπαράλληλα\b',
    ]),
]

def classify_question(q):
    """Assign conceptual_tags based on keyword matching in question_text + answer_text."""
    text = (q.get("question_text", "") + " " + q.get("answer_text", "")).lower()
    tags = []
    for tag, patterns in TOPICS:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(tag)
                break
    return tags if tags else ["Γενική Φυσική"]

def load_subject_config(subject_id):
    cfg_path = os.path.join(BASE, "subjects", f"{subject_id}.json")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--subject", default="fysiki_prosanatolismoy", help="Subject ID")
    args = p.parse_args()

    cfg = load_subject_config(args.subject)
    data_dir = os.path.join(BASE, cfg.get("data", {}).get("data_dir", f"data/subjects/{args.subject}"))
    v2_file = os.path.join(data_dir, "questions_v2.json")

    if not os.path.exists(v2_file):
        print(f"ERROR: {v2_file} not found")
        return

    # ── Backup before modification ──
    backup = f"{v2_file}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(v2_file, backup)
    print(f"📦 Backup: {os.path.basename(backup)}")

    v2 = json.load(open(v2_file, encoding="utf-8"))
    classified = 0
    distribution = {}

    for q in v2:
        tags = classify_question(q)
        q["conceptual_tags"] = tags
        for t in tags:
            distribution[t] = distribution.get(t, 0) + 1
        if tags:
            classified += 1

    with open(v2_file, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)

    print(f"✅ Classified: {classified}/{len(v2)} questions [{args.subject}]")
    print(f"\n📊 Topic distribution:")
    for t, c in sorted(distribution.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c} questions")

if __name__ == "__main__":
    main()