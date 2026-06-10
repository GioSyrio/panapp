#!/usr/bin/env python3
"""
Πανελλήνιες AI Tutor — Exam Practice Engine

Silently selects questions based on computed high-probability categories
instead of picking at random or asking the student what to study.

Usage: python3 tutor.py
"""

import json
import os
import random
from collections import defaultdict
from predictor import calculate_topic_priorities, CURRENT_YEAR

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "trapeza_data_1_3_218")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")


def load_questions():
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def pick_question_by_priority(exam_data, ranked_priorities, top_n=10, exclude_ids=None):
    """
    Silently select a question matching the highest-priority topics.
    Walks down the ranked list until a match is found.
    Returns (question, matched_tag).
    """
    exclude_ids = exclude_ids or set()

    for tag, _ in ranked_priorities[:top_n]:
        candidates = [
            q for q in exam_data
            if tag in q.get("conceptual_tags", [])
            and q["id"] not in exclude_ids
        ]
        if candidates:
            # Prefer questions with more sub-tags (richer content)
            candidates.sort(key=lambda q: len(q.get("conceptual_tags", [])), reverse=True)
            return candidates[0], tag

    return None, None


def pick_by_part(exam_data, part, exclude_ids=None):
    """Fallback: pick any question for a given part."""
    exclude_ids = exclude_ids or set()
    candidates = [q for q in exam_data if q["part"] == part and q["id"] not in exclude_ids]
    if not candidates:
        candidates = [q for q in exam_data if q["id"] not in exclude_ids]
    return random.choice(candidates) if candidates else None


def summarize_plan(ranked_priorities):
    """Build a summary of the session plan for display (optional debug)."""
    return ranked_priorities[:3]


def format_question(question, matched_tag=None):
    """Format a question for display to the student."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  {question['part']}  ({question['year']})  —  {question['points']} μονάδες")
    lines.append("=" * 60)
    lines.append("")

    # Show the question text
    lines.append(question["question_text"])
    lines.append("")
    lines.append("-" * 60)
    lines.append("Γράψε την απάντησή σου. Πάτησε Enter για να δεις τη λύση...")
    lines.append("-" * 60)

    return "\n".join(lines)


def show_answer(question):
    """Display the solution."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("  ΕΝΔΕΙΚΤΙΚΗ ΑΠΑΝΤΗΣΗ")
    lines.append("=" * 60)
    lines.append("")
    if question.get("answer_text"):
        lines.append(question["answer_text"])
    else:
        lines.append("(Δεν υπάρχει καταχωρημένη απάντηση για αυτό το θέμα.)")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def show_session_stats(completed):
    """Show summary of completed questions in the session."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("  ΣΥΝΟΨΗ ΣΥΝΕΔΡΙΑΣ")
    lines.append("=" * 60)
    parts_count = defaultdict(int)
    total_points = 0
    for q in completed:
        parts_count[q["part"]] += 1
        total_points += q["points"]
    lines.append(f"  Θέματα που ολοκληρώθηκαν: {len(completed)}")
    for part, count in sorted(parts_count.items()):
        lines.append(f"    {part}: {count}")
    lines.append(f"  Σύνολο μονάδων: {total_points}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  ΠΑΝΕΛΛΗΝΙΕΣ AI TUTOR")
    print(f"  Στοχευμένη εξάσκηση βάσει στατιστικής ανάλυσης θεμάτων")
    print("=" * 60)

    if not os.path.exists(QUESTIONS_FILE):
        print(f"\n  [ERROR] Δεν βρέθηκε το {QUESTIONS_FILE}.")
        print("  Τρέξε πρώτα: python3 build_questions.py")
        return

    exam_data = load_questions()
    ranked_priorities, details = calculate_topic_priorities(exam_data)

    # Filter noise tags
    noise = {"ΠΛΗΡΟΦΟΡΙΚΗ:", "ΑΕΠΠ:", ""}
    ranked_priorities = [(t, s) for t, s in ranked_priorities if t not in noise]

    completed = []
    seen_ids = set()

    print(f"\n  Σήμερα θα εξασκηθούμε σε θέματα που έχουν")
    print(f"  υψηλή στατιστική πιθανότητα εμφάνισης στις")
    print(f"  Πανελλήνιες {CURRENT_YEAR}.\n")

    session_active = True

    while session_active:
        # 1. Pick Θέμα 2 by priority
        thema2_data = [q for q in exam_data if q["part"] == "Θέμα 2"]
        if thema2_data:
            q2, tag2 = pick_question_by_priority(thema2_data, ranked_priorities, top_n=10, exclude_ids=seen_ids)
            if not q2:
                q2 = pick_by_part(thema2_data, "Θέμα 2", exclude_ids=seen_ids)
            if q2:
                seen_ids.add(q2["id"])
                print(format_question(q2, tag2))
                input()
                print(show_answer(q2))
                completed.append(q2)

        print()

        # 2. Pick Θέμα 4 by priority
        thema4_data = [q for q in exam_data if q["part"] == "Θέμα 4"]
        if thema4_data:
            q4, tag4 = pick_question_by_priority(thema4_data, ranked_priorities, top_n=10, exclude_ids=seen_ids)
            if not q4:
                q4 = pick_by_part(thema4_data, "Θέμα 4", exclude_ids=seen_ids)
            if q4:
                seen_ids.add(q4["id"])
                print(format_question(q4, tag4))
                input()
                print(show_answer(q4))
                completed.append(q4)

        # Stats
        print(show_session_stats(completed))

        # Ask if they want more
        remaining = len(exam_data) - len(seen_ids)
        if remaining == 0:
            print("\n  Δεν υπάρχουν άλλα διαθέσιμα θέματα.")
            print("  Εξαιρετική δουλειά! Ολοκλήρωσες όλη την τράπεζα θεμάτων!")
            break

        print(f"\n  Απομένουν {remaining} θέματα στην τράπεζα.")
        choice = input("  Συνέχιση; (Enter = ναι, q = έξοδος): ").strip().lower()
        if choice == 'q':
            session_active = False
            print("\n  Καλή επιτυχία στις εξετάσεις! 🎓")

    print()


if __name__ == "__main__":
    main()