#!/usr/bin/env python3
"""
Panhellenic AI Tutor — DeepSeek Runtime

Connects the priority-based question selector to the DeepSeek API,
piping student answers through the chat completions endpoint for
real-time evaluation and feedback.

Usage:
    DEEPSEEK_API_KEY=sk-... python3 runtime.py
    DEEPSEEK_API_KEY=sk-... python3 runtime.py --model deepseek-chat
"""

import json
import os
import sys

from openai import OpenAI

from predictor import calculate_topic_priorities, CURRENT_YEAR
from prompts import (
    PREDICTION_SYSTEM_PROMPT,
    CORRECT_ANSWER_PROMPT,
    PARTIAL_ANSWER_PROMPT,
    INCORRECT_ANSWER_PROMPT,
    COMMON_PANHELLENIC_TRAPS,
    build_trend_context,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "trapeza_data_1_3_218")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")


def load_questions():
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def pick_question_by_priority(exam_data, ranked_priorities, top_n=10, exclude_ids=None):
    """Silently select a question matching the highest-priority topics."""
    exclude_ids = exclude_ids or set()

    for tag, _ in ranked_priorities[:top_n]:
        candidates = [
            q for q in exam_data
            if tag in q.get("conceptual_tags", [])
            and q["id"] not in exclude_ids
        ]
        if candidates:
            candidates.sort(key=lambda q: len(q.get("conceptual_tags", [])), reverse=True)
            return candidates[0], tag
    return None, None


def pick_by_part(exam_data, part, exclude_ids=None):
    """Fallback: pick any question for a given part."""
    import random
    exclude_ids = exclude_ids or set()
    candidates = [q for q in exam_data if q["part"] == part and q["id"] not in exclude_ids]
    if not candidates:
        candidates = [q for q in exam_data if q["id"] not in exclude_ids]
    return random.choice(candidates) if candidates else None


def format_question(question, matched_tag=None):
    """Format a question for display to the student."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  {question['part']}  ({question['year']})  —  {question['points']} μονάδες")
    if matched_tag:
        lines.append(f"  Περιοχή εστίασης: {matched_tag}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(question["question_text"])
    lines.append("")
    lines.append("-" * 60)
    lines.append("Γράψε την απάντησή σου παρακάτω.")
    lines.append("Πληκτρολόγησε 'exit' ή 'έξοδος' για τερματισμό.")
    lines.append("-" * 60)
    return "\n".join(lines)


def show_answer(question):
    """Display the reference solution."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("  ΕΝΔΕΙΚΤΙΚΗ ΑΠΑΝΤΗΣΗ (επίσημη λύση)")
    lines.append("=" * 60)
    lines.append("")
    if question.get("answer_text"):
        lines.append(question["answer_text"])
    else:
        lines.append("(Δεν υπάρχει καταχωρημένη απάντηση.)")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def classify_answer(option):
    """Determine which feedback prompt to use based on student self-assessment."""
    option = option.strip().lower()
    if option in {"1", "correct", "σωστό", "σωστη", "σωστή"}:
        return CORRECT_ANSWER_PROMPT
    elif option in {"2", "partial", "μερικώς", "μερικη", "μερική"}:
        return PARTIAL_ANSWER_PROMPT
    elif option in {"3", "incorrect", "λάθος", "λαθος", "λάθη"}:
        return INCORRECT_ANSWER_PROMPT
    else:
        return None


def main():
    # ── Model selection ─────────────────────────────────────────────────
    model = "deepseek-reasoner"  # reasoning tokens for deep code evaluation
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]

    # ── API client setup ─────────────────────────────────────────────────
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set.")
        print("Export it:  export DEEPSEEK_API_KEY=sk-...")
        return

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    # ── Load data ────────────────────────────────────────────────────────
    exam_data = load_questions()
    ranked_priorities, details = calculate_topic_priorities(exam_data)
    noise = {"ΠΛΗΡΟΦΟΡΙΚΗ:", "ΑΕΠΠ:", ""}
    ranked = [(t, s) for t, s in ranked_priorities if t not in noise]

    # Build hidden trend context for the AI
    trend_context = build_trend_context(ranked, details, top_n=5)

    # ── Welcome ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  ΠΑΝΕΛΛΗΝΙΕΣ AI TUTOR  (DeepSeek Runtime)")
    print(f"  Model: {model}")
    print("=" * 60)
    print()
    print(f"  Σήμερα θα εξασκηθούμε σε θέματα που έχουν")
    print(f"  υψηλή στατιστική πιθανότητα εμφάνισης στις")
    print(f"  Πανελλήνιες {CURRENT_YEAR}.")
    print()

    seen_ids = set()
    session_active = True

    while session_active:
        # ── Question selection by priority ───────────────────────────────
        # Alternate between Θέμα 2 and Θέμα 4
        if len(seen_ids) % 2 == 0:
            part = "Θέμα 2"
        else:
            part = "Θέμα 4"

        part_data = [q for q in exam_data if q["part"] == part]
        selected, matched_tag = pick_question_by_priority(
            part_data, ranked, top_n=15, exclude_ids=seen_ids
        )
        if not selected:
            selected = pick_by_part(part_data, part, exclude_ids=seen_ids)
        if not selected:
            print("\n  Δεν υπάρχουν άλλα θέματα. Συγχαρητήρια!")
            break

        seen_ids.add(selected["id"])

        # ── Display question ─────────────────────────────────────────────
        print()
        print(format_question(selected, matched_tag))
        print()

        # ── Build system prompt with trend context ───────────────────────
        system_context = (
            PREDICTION_SYSTEM_PROMPT + "\n\n" + trend_context + "\n\n"
            "The student is currently working on the following exam task:\n\n"
            f"Question: {selected['question_text'][:3000]}\n\n"
            f"Reference answer (for your knowledge only — do NOT reveal to "
            f"the student unless they explicitly ask to see the solution):\n"
            f"{selected.get('answer_text', '')[:3000]}"
        )

        messages = [
            {"role": "system", "content": system_context},
        ]

        # ── Interactive evaluation loop ──────────────────────────────────
        question_active = True
        while question_active:
            user_input = input("  Εσύ: ").strip()

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "έξοδος"}:
                question_active = False
                session_active = False
                break

            if user_input.lower() in {"next", "επόμενο", "επομενο", "skip", "παράβλεψη"}:
                question_active = False
                print(show_answer(selected))
                break

            if user_input.lower() in {"solution", "λύση", "λυση", "απάντηση", "απαντηση"}:
                print(show_answer(selected))
                continue

            # Check if student is self-classifying their answer
            feedback_prompt = classify_answer(user_input)
            if feedback_prompt:
                if feedback_prompt:
                    self_assessment = True
                else:
                    continue

            # Add user message
            messages.append({"role": "user", "content": user_input})

            # Call DeepSeek
            try:
                print("  ...", end="", flush=True)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=2000,
                )
                ai_reply = response.choices[0].message.content
                print(f"\r  AI : {ai_reply}")
                messages.append({"role": "assistant", "content": ai_reply})
            except Exception as e:
                print(f"\r  [API Error: {e}]")

        # ── Show reference solution ──────────────────────────────────────
        if question_active:
            print()
            print(show_answer(selected))

        # ── Session stats ────────────────────────────────────────────────
        remaining = len(exam_data) - len(seen_ids)
        print(f"\n  ✅ Θέματα που ολοκληρώθηκαν: {len(seen_ids)}")
        print(f"  📚 Απομένουν: {remaining}")
        print()

        if remaining == 0:
            print("  🎓 Εξαιρετική δουλειά! Ολοκλήρωσες όλη την τράπεζα θεμάτων!")
            break

        choice = input("  Συνέχιση με επόμενο θέμα; (Enter = ναι, q = έξοδος): ").strip().lower()
        if choice == "q":
            session_active = False

    print("\n  Καλή επιτυχία στις εξετάσεις! 🎓\n")


if __name__ == "__main__":
    main()