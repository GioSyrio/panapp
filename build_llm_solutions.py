#!/usr/bin/env python3
"""
build_llm_solutions.py — Offline LLM pass for step-by-step solutions (all subjects)

Processes questions through DeepSeek to generate polished,
engaging step-by-step solutions in Greek. Results are stored in
questions_v2.json as 'llm_solution_html' — served instantly at runtime.

Usage:
    python3 build_llm_solutions.py --subject informatics
    python3 build_llm_solutions.py --subject istoria --limit 5
    python3 build_llm_solutions.py --subject istoria --id 25329
"""

import json
import os
import sys
import argparse
import time
import shutil
import re as _re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Subject-specific solution prompts ──────────────────────────────────────

GENERIC_SOLUTION_PROMPT = """Είσαι ένας υπομονετικός, ενθουσιώδης καθηγητής που βοηθά έναν μαθητή Γ' Λυκείου να καταλάβει τη λύση μιας άσκησης για τις Πανελλήνιες εξετάσεις.

Θα σου δώσω την εκφώνηση και την ενδεικτική απάντηση μιας άσκησης. Γράψε μια **βήμα-βήμα** λύση στα Ελληνικά, με φυσική γλώσσα σαν να μιλάς στον μαθητή.

**Κανόνες:**
1. Χώρισε τη λύση σε 3-5 βήματα με αρίθμηση (1., 2., 3.)
2. Κάθε βήμα να ξεκινά με **έντονη επικεφαλίδα** (π.χ. "Κατανόηση του προβλήματος", "Υπολογισμός", "Επαλήθευση")
3. Εξήγησε **γιατί** κάνουμε κάθε βήμα, όχι μόνο το τι κάνουμε
4. Χρησιμοποίησε φιλικό, ενθαρρυντικό ύφος (π.χ. "Πρόσεξε τώρα...", "Μπράβο, φτάσαμε στο...")
5. Στο τέλος, βάλε ένα **💡 Συμβουλή εξετάσεων** (τι να προσέξει ο μαθητής)

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

HUMANITIES_SOLUTION_PROMPT = """Είσαι ένας φίλος-προπονητής για Πανελλήνιες εξετάσεις. Θα σου δώσω μια ερώτηση θεωρητικού μαθήματος. Γράψε μια **πρότυπη απάντηση** στα Ελληνικά που να δείχνει στον μαθητή ΠΩΣ να απαντά σωστά σε τέτοιες ερωτήσεις.

**Κανόνες:**
1. Χώρισε την απάντηση σε 3-5 βήματα/παραγράφους με σαφή δομή
2. Κάθε βήμα να ξεκινά με σύντομη επικεφαλίδα
3. Δείξε πώς να οργανώνει τη σκέψη του: θέση → επιχείρημα → τεκμήρια → συμπέρασμα
4. Αν υπάρχουν πηγές/κείμενα, δείξε πώς να τα παραθέτει και να τα σχολιάζει
5. Χρησιμοποίησε φιλικό, ενθαρρυντικό ύφος
6. Στο τέλος, βάλε ένα **💡 Συμβουλή εξετάσεων**

**Μορφοποίηση εξόδου:**

[ΒΗΜΑ 1] <επικεφαλίδα>
<περιεχόμενο>

[ΒΗΜΑ 2] <επικεφαλίδα>
<περιεχόμενο>

💡 Συμβουλή εξετάσεων:
<συμβουλή>

---
ΕΚΦΩΝΗΣΗ:
{question_text}

ΕΝΔΕΙΚΤΙΚΗ ΑΠΑΝΤΗΣΗ (αν υπάρχει):
{answer_text}
"""

SYSTEM_PROMPT = """Είσαι ένας άριστος καθηγητής στην Ελλάδα. 
Γράφεις πάντα στα Ελληνικά με σαφή, βήμα-βήμα δομή.
Χρησιμοποιείς φιλικό και ενθαρρυντικό ύφος κατάλληλο για εφήβους.
Τονίζεις τα σημεία που συχνά μπερδεύουν τους μαθητές στις Πανελλαδικές."""


def load_subject_config(subject_id):
    cfg_path = os.path.join(BASE_DIR, "subjects", f"{subject_id}.json")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def init_client():
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def get_solution_prompt(subject_id):
    """Return appropriate solution prompt for the subject."""
    humanities = [
        "istoria", "istoria_prosanatolismoy",
        "neoelliniki_glossa_kai_logotechnia",
        "latinika", "archaia_elliniki_glossa_kai_grammateia___archaia_ellinika"
    ]
    if subject_id in humanities:
        return HUMANITIES_SOLUTION_PROMPT
    return GENERIC_SOLUTION_PROMPT


def get_question_text(q):
    """Get question text from v2 question, with fallbacks for humanities."""
    # Try question_text field first
    qt = q.get("question_text", "")
    if qt and len(qt) > 20:
        return qt[:3000]
    # Fall back to stripping HTML from question_html
    qhtml = q.get("question_html", "")
    if qhtml:
        qt = _re.sub(r'<[^>]+>', ' ', qhtml)
        qt = _re.sub(r'\s+', ' ', qt).strip()
        if qt and len(qt) > 20:
            return qt[:3000]
    # Last resort: concatenate section contents
    sections = q.get("sections", [])
    if sections:
        qt = "\n".join(s.get("content", "") for s in sections)
        if qt.strip() and len(qt) > 20:
            return qt[:3000]
    return "(δεν υπάρχει κείμενο ερώτησης)"


def get_answer_text(q):
    """Get answer text from v2 question, with fallbacks."""
    at = q.get("answer_text", "")
    if at and len(at) > 10:
        return at[:3000]
    ahtml = q.get("answer_html", "")
    if ahtml and len(ahtml) > 10:
        at = _re.sub(r'<[^>]+>', ' ', ahtml)
        at = _re.sub(r'\s+', ' ', at).strip()
        if at and len(at) > 10:
            return at[:3000]
    return "(δεν υπάρχει ενδεικτική απάντηση)"


def process_question(client, q, progress, solution_prompt):
    """Call DeepSeek to generate step-by-step solution for one question."""
    qid = str(q["id"])
    if qid in progress["completed"]:
        return True

    qt = get_question_text(q)
    at = get_answer_text(q)
    prompt = solution_prompt.format(question_text=qt, answer_text=at)

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

        # Convert [ΒΗΜΑ N] markers to HTML
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
    parts = _re.split(r'\[ΒΗΜΑ\s+(\d+)\]\s*', text)

    html = []
    if parts[0].strip():
        html.append(f'<div class="sol-intro">{e(parts[0].strip())}</div>')

    for i in range(1, len(parts) - 1, 2):
        num = parts[i]
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""

        lines = content.split('\n', 1)
        header = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        header = _re.sub(r'\*\*(.*?)\*\*', r'\1', header)
        body = _re.sub(r'\*\*(.*?)\*\*', r'\1', body)

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
    import html
    return html.escape(s) if s else ""


def _save_with_merge(v2_file, modified_data):
    """Save modified subset back into the full v2 file."""
    if not os.path.exists(v2_file):
        json.dump(modified_data, open(v2_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return
    with open(v2_file, encoding="utf-8") as f:
        full_data = json.load(f)
    if len(modified_data) == len(full_data):
        with open(v2_file, "w", encoding="utf-8") as f:
            json.dump(modified_data, f, ensure_ascii=False, indent=2)
        return
    mod_by_id = {q["id"]: q for q in modified_data}
    for i, q in enumerate(full_data):
        if q["id"] in mod_by_id:
            full_data[i] = mod_by_id[q["id"]]
    with open(v2_file, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Generate LLM solutions offline")
    parser.add_argument("--subject", default="informatics", help="Subject ID")
    parser.add_argument("--limit", type=int, default=0, help="Process only N questions")
    parser.add_argument("--id", type=int, default=0, help="Single question by ID")
    args = parser.parse_args()

    subject_id = args.subject
    cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    progress_file = os.path.join(data_dir, "llm_solutions_progress.json")

    if not os.path.exists(v2_file):
        print(f"ERROR: {v2_file} not found.")
        sys.exit(1)

    solution_prompt = get_solution_prompt(subject_id)
    client = init_client()

    with open(v2_file, encoding="utf-8") as f:
        data = json.load(f)

    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file, encoding="utf-8") as f:
            progress = json.load(f)
    progress.setdefault("completed", [])

    total = len(data)
    done = len(progress["completed"])

    print(f"🤖 LLM Solution Generator [{subject_id}]")
    print(f"   Questions: {total}")
    print(f"   Completed: {done}")
    print(f"   Remaining: {total - done}")
    print()

    # Check if already has solutions
    sample_with = sum(1 for q in data[:5] if q.get("llm_solution_html"))
    if sample_with >= 3:
        print(f"⚠️  Solutions appear to already exist ({sample_with}/5 in first sample)")
        print("   Delete llm_solutions_progress.json to re-generate.")
        return

    if args.id:
        data_qs = [q for q in data if q["id"] == args.id]
        if not data_qs:
            print(f"   Question {args.id} not found.")
            return
    elif args.limit > 0:
        todo = [q for q in data if str(q["id"]) not in progress["completed"]]
        data_qs = todo[:args.limit]
    else:
        data_qs = [q for q in data if str(q["id"]) not in progress["completed"]]

    print(f"   Processing {len(data_qs)} questions...\n")

    # Backup
    backup = f"{v2_file}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(v2_file, backup)
    print(f"📦 Backup: {os.path.basename(backup)}")

    for i, q in enumerate(data_qs):
        sys.stdout.write(f"  [{i + 1}/{len(data_qs)}] ")
        sys.stdout.flush()

        process_question(client, q, progress, solution_prompt)

        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        if i % 10 == 9:
            _save_with_merge(v2_file, data)
            print(f"  💾 Saved ({i+1}/{len(data_qs)})")

        time.sleep(1.5)

    # Final save
    _save_with_merge(v2_file, data)
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

    new_done = len(progress["completed"])
    print(f"\n✅ Done! {new_done}/{total} solutions generated.")
    print(f"   Progress: {progress_file}")
    print(f"   Output: {v2_file}")


if __name__ == "__main__":
    main()