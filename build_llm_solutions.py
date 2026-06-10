#!/usr/bin/env python3
"""
build_llm_solutions.py — Offline LLM pass for step-by-step solutions

Processes all 155 questions through DeepSeek to generate polished,
engaging step-by-step solutions in Greek. Results are stored in
questions_v2.json as 'llm_solution_html' — served instantly at runtime.

Runs ONCE, offline. Saves progress after each question.

Usage:
    python3 build_llm_solutions.py
    python3 build_llm_solutions.py --limit 5     # test with 5 questions
    python3 build_llm_solutions.py --id 25947    # single question
"""

import json
import os
import sys
import argparse
import time
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "trapeza_data_1_3_218")
V2_FILE = os.path.join(DATA_DIR, "questions_v2.json")
PROGRESS_FILE = os.path.join(DATA_DIR, "llm_solutions_progress.json")

# ── Prompts ─────────────────────────────────────────────────────────────────

SOLUTION_PROMPT = """Είσαι ένας υπομονετικός, ενθουσιώδης καθηγητής Πληροφορικής που βοηθά έναν μαθητή Γ' Λυκείου να καταλάβει τη λύση μιας άσκησης για τις Πανελλήνιες εξετάσεις.

Θα σου δώσω την εκφώνηση και την ενδεικτική απάντηση μιας άσκησης. Γράψε μια **βήμα-βήμα** λύση στα Ελληνικά, με φυσική γλώσσα σαν να μιλάς στον μαθητή.

**Κανόνες:**
1. Χώρισε τη λύση σε 3-5 βήματα με αρίθμηση (1., 2., 3.)
2. Κάθε βήμα να ξεκινά με **έντονη επικεφαλίδα** (π.χ. "Κατανόηση του προβλήματος", "Υπολογισμός", "Επαλήθευση")
3. Εξήγησε **γιατί** κάνουμε κάθε βήμα, όχι μόνο το τι κάνουμε
4. Χρησιμοποίησε φιλικό, ενθαρρυντικό ύφος (π.χ. "Πρόσεξε τώρα...", "Μπράβο, φτάσαμε στο...")
5. Αν έχει κώδικα/ψευδογλώσσα, δείξ' τον με σχόλια δίπλα
6. Στο τέλος, βάλε ένα **💡 Συμβουλή εξετάσεων** (τι να προσέξει ο μαθητής)

**Μορφοποίηση εξόδου (ΧΡΗΣΙΜΟΠΟΙΗΣΕ ΑΥΤΟ ΤΟ FORMAT):**

[ΒΗΜΑ 1] <έντονη επικεφαλίδα>
<επεξήγηση>

[ΒΗΜΑ 2] <έντονη επικεφαλίδα>
<επεξήγηση>

[ΒΗΜΑ 3] <έντονη επικεφαλίδα>
<επεξήγηση>

💡 Συμβουλή εξετάσεων:
<συμβουλή>

---
ΕΚΦΩΝΗΣΗ:
{question_text}

ΕΝΔΕΙΚΤΙΚΗ ΑΠΑΝΤΗΣΗ:
{answer_text}
"""

SYSTEM_PROMPT = """Είσαι ένας άριστος καθηγητής Πληροφορικής στην Ελλάδα. 
Γράφεις πάντα στα Ελληνικά με σαφή, βήμα-βήμα δομή.
Χρησιμοποιείς φιλικό και ενθαρρυντικό ύφος κατάλληλο για εφήβους.
Τονίζεις τα σημεία που συχνά μπερδεύουν τους μαθητές στις Πανελλαδικές."""


def init_client():
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def load_v2():
    if not os.path.exists(V2_FILE):
        print(f"ERROR: {V2_FILE} not found. Run build_questions_v2.py first.")
        sys.exit(1)
    with open(V2_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"completed": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def save_v2(data):
    backup = V2_FILE + ".backup"
    if os.path.exists(V2_FILE):
        os.rename(V2_FILE, backup)
    with open(V2_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved {len(data)} questions to {V2_FILE}")


def process_question(client, q, progress):
    """Call DeepSeek to generate step-by-step solution for one question."""
    qid = q["id"]
    if qid in progress["completed"]:
        return True  # already done

    qt = q.get("question_text", "")[:3000]
    at = q.get("answer_text", "")[:3000]
    prompt = SOLUTION_PROMPT.format(question_text=qt, answer_text=at)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        result = response.choices[0].message.content or ""

        # Convert [ΒΗΜΑ N] markers to HTML with sol-step class
        html = convert_to_html(result)
        q["llm_solution_html"] = html
        q["llm_solution_raw"] = result

        progress["completed"].append(qid)
        print(f"  ✅ Q{qid}: {len(result)} chars")

    except Exception as e:
        print(f"  ❌ Q{qid}: {e}")

    return True


def convert_to_html(text):
    """Convert [ΒΗΜΑ N] markers to styled HTML."""
    import re

    # Split on [ΒΗΜΑ N] markers
    parts = re.split(r'\[ΒΗΜΑ\s+(\d+)\]\s*', text)

    html = []
    # First part before any step
    if parts[0].strip():
        html.append(f'<div class="sol-intro">{e(parts[0].strip())}</div>')

    # Process pairs: number, content
    for i in range(1, len(parts) - 1, 2):
        num = parts[i]
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""

        # Split content into header (first line) and body
        lines = content.split('\n', 1)
        header = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        # Remove any ** markers
        header = re.sub(r'\*\*(.*?)\*\*', r'\1', header)
        body = re.sub(r'\*\*(.*?)\*\*', r'\1', body)

        # Detect exam tip
        if 'συμβουλ' in header.lower() or 'συμβουλ' in body.lower():
            html.append(
                f'<div class="sol-tip">'
                f'<div class="sol-tip-label">💡 {e(header)}</div>'
                f'<div class="sol-tip-text">{e(body).replace(chr(10), "<br>")}</div>'
                f'</div>'
            )
        else:
            html.append(
                f'<div class="sol-step">'
                f'<div class="sol-step-label">📌 {e(header)}</div>'
                f'<div class="sol-step-text">{e(body).replace(chr(10), "<br>")}</div>'
                f'</div>'
            )

    return '\n'.join(html)


def e(s):
    """HTML-escape."""
    return (s.replace("&", "&").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def main():
    parser = argparse.ArgumentParser(description="Generate LLM solutions offline")
    parser.add_argument("--limit", type=int, default=0, help="Process only N questions")
    parser.add_argument("--id", type=int, default=0, help="Single question by ID")
    parser.add_argument("--resume", action="store_true", help="Resume from last progress")
    args = parser.parse_args()

    client = init_client()
    data = load_v2()
    progress = load_progress()

    total = len(data)
    done = len(progress["completed"])

    print(f"🤖 LLM Solution Generator")
    print(f"   Questions: {total}")
    print(f"   Completed: {done}")
    print(f"   Remaining: {total - done}")
    print()

    if args.id:
        target = [q for q in data if q["id"] == args.id]
        if not target:
            print(f"   Question {args.id} not found.")
            return
        data_qs = target
    elif args.limit > 0:
        todo = [q for q in data if q["id"] not in progress["completed"]]
        data_qs = todo[:args.limit]
    else:
        data_qs = [q for q in data if q["id"] not in progress["completed"]]

    print(f"   Processing {len(data_qs)} questions...\n")

    for i, q in enumerate(data_qs):
        sys.stdout.write(f"  [{i + 1}/{len(data_qs)}] ")
        sys.stdout.flush()

        process_question(client, q, progress)

        # Save after each question
        save_progress(progress)
        if i % 10 == 9:
            save_v2(data)

        time.sleep(1.5)  # rate limit

    # Final save
    save_v2(data)
    save_progress(progress)

    new_done = len(progress["completed"])
    print(f"\n✅ Done! {new_done}/{total} solutions generated.")
    print(f"   Progress saved to: {PROGRESS_FILE}")
    print(f"   Solutions saved to: {V2_FILE}")


if __name__ == "__main__":
    main()