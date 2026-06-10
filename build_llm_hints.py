#!/usr/bin/env python3
"""
build_llm_hints.py — Offline 3-tier Socratic hint generation

Generates progressive hints (Level 1→2→3) per sub-question using DeepSeek.
Stores in questions_v2.json as 'hints' array.

Level 1: Chapter rule / concept reference (what to study)
Level 2: Structural milestone / trace hint (what to look at)
Level 3: Code scaffold with blanks (fill in the gaps)

Runs ONCE, offline. Saves progress after each question.

Usage:
    python3 build_llm_hints.py
    python3 build_llm_hints.py --limit 5
    python3 build_llm_hints.py --id 25947
"""

import json, os, sys, argparse, time
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "trapeza_data_1_3_218")
V2_FILE = os.path.join(DATA_DIR, "questions_v2.json")
PROGRESS_FILE = os.path.join(DATA_DIR, "llm_hints_progress.json")

HINT_PROMPT = """You are an expert Greek Informatics tutor using Socratic scaffolding. 
Generate a single hint at the requested level for the given question.

CRITICAL RULES:
- NEVER reveal the final answer, exact values, or complete solutions.
- Be encouraging, direct, and exclusively in Greek.
- Return ONLY a JSON object: {{"hint_text": "Your hint here..."}}

HINT LEVEL {level} INSTRUCTIONS:
- Level 1: High-level guidance. Point to the specific chapter rule or concept they need.
- Level 2: Point out a structural calculation milestone or loop trace condition.
- Level 3: Provide a small code snippet scaffold with ____ blanks for them to complete.

---

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}
"""

SYSTEM_PROMPT = "You are a Greek Informatics teacher. Answer ONLY in Greek. Return valid JSON."


def init_client():
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def load_v2():
    with open(V2_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"completed": []}  # list of "{qid}_{subq_idx}"


def save_progress(p):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def save_v2(data):
    if os.path.exists(V2_FILE):
        os.rename(V2_FILE, V2_FILE + ".backup")
    with open(V2_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_subquestions(q):
    """Get sub-questions from v2 sections."""
    subs = []
    for s in q.get("sections", []):
        if s["type"] == "sub_question":
            subs.append({
                "number": s.get("number", "?"),
                "content": s.get("content", ""),
            })
    return subs


def generate_hints(client, q, progress):
    """Generate 3-level hints for each sub-question of a question."""
    qid = q["id"]
    subs = get_subquestions(q)
    if not subs:
        subs = [{"number": "?", "content": q.get("question_text", "")[:2000]}]

    answer_text = q.get("answer_text", "")[:1500]
    hints = []

    for si, sub in enumerate(subs):
        key = f"{qid}_{si}"
        if key in progress["completed"]:
            continue

        subq_hints = []
        for level in [1, 2, 3]:
            prompt = HINT_PROMPT.format(
                level=level,
                subq_num=sub["number"],
                subq_text=sub["content"][:2000],
                answer_text=answer_text,
            )
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=400,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or "{}"
                try:
                    data = json.loads(raw)
                    text = data.get("hint_text", raw[:300])
                except json.JSONDecodeError:
                    import re
                    m = re.search(r'\{.*\}', raw, re.DOTALL)
                    if m:
                        try:
                            data = json.loads(m.group(0))
                            text = data.get("hint_text", raw[:300])
                        except:
                            text = raw[:300]
                    else:
                        text = raw[:300]

                subq_hints.append({"level": level, "hint_text": text.strip()})
                print(f"    Level {level} ✓")

            except Exception as e:
                print(f"    Level {level} ❌: {e}")
                subq_hints.append({"level": level, "hint_text": f"Σφάλμα: {str(e)[:100]}"})

            time.sleep(0.8)

        hints.append({"subq_idx": si, "number": sub["number"], "hints": subq_hints})
        progress["completed"].append(key)

    return hints


def main():
    parser = argparse.ArgumentParser(description="Generate Socratic hints offline")
    parser.add_argument("--limit", type=int, default=0, help="Process only N questions")
    parser.add_argument("--id", type=int, default=0, help="Single question by ID")
    args = parser.parse_args()

    client = init_client()
    data = load_v2()
    progress = load_progress()

    print(f"🎯 Socratic Hint Generator")
    print(f"   Questions: {len(data)}")
    print(f"   Completed hint-groups: {len(progress['completed'])}")
    print()

    if args.id:
        data = [q for q in data if q["id"] == args.id]
        if not data:
            print(f"Question {args.id} not found"); return
    elif args.limit > 0:
        data = data[:args.limit]

    for i, q in enumerate(data):
        qid = q["id"]
        sys.stdout.write(f"  [{i+1}/{len(data)}] Q{qid}...\n")
        sys.stdout.flush()

        q["hints"] = generate_hints(client, q, progress)

        save_progress(progress)
        if i % 5 == 4:
            save_v2(data)

    save_v2(data)
    save_progress(progress)

    print(f"\n✅ Done! {len(progress['completed'])} hint-groups generated.")
    print(f"   Saved to: {V2_FILE}")


if __name__ == "__main__":
    main()