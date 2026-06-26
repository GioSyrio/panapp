#!/usr/bin/env python3
"""
build_llm_html_fix.py — LLM-powered HTML polishing for math question_html_parts

Feeds each question's current HTML parts, original sections, and available OCR
formulas to DeepSeek with a structured editing prompt. The LLM fixes:
  - Formulas placed at correct inline positions (not appended at paragraph ends)
  - Sub-questions using proper <div class="subq"> wrappers
  - Points chips immediately after their corresponding subq
  - Wrong subq labels corrected (e.g. γ showing β content)
  - Corrupted OCR greek text removed from formulas
  - Sub-items (i, ii, iii) properly nested

Usage:
    python3 build_llm_html_fix.py --subject mathematics
    python3 build_llm_html_fix.py --subject mathematics --limit 5
    python3 build_llm_html_fix.py --subject mathematics --id 34151
"""

import json, os, sys, argparse, time, re
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_subject_config(subject_id):
    cfg_path = os.path.join(BASE_DIR, "subjects", f"{subject_id}.json")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)

def init_client():
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set"); sys.exit(1)
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

# ── LLM Prompt ─────────────────────────────────────────────────────────────

HTML_FIX_SYSTEM = """Είσαι επιμελητής Μαθηματικών για Πανελλαδικές εξετάσεις. 
Διορθώνεις το HTML μιας ερώτησης ώστε να είναι τέλειο για μαθητές Λυκείου.

ΕΠΙΣΤΡΕΦΕ ΜΟΝΟ ενα JSON array από strings (τα διορθωμένα HTML parts).
ΠΟΤΕ μην επιστρέφεις επεξηγήσεις ή σχόλια εκτός του JSON."""

HTML_FIX_PROMPT = """Διόρθωσε το παρακάτω question_html_parts array.

ΚΑΝΟΝΕΣ (αυστηρά):
1. ΟΛΑ τα $...$ LaTeX πρέπει να είναι INLINE στη σωστή τους θέση μέσα στο κείμενο, 
   ΟΧΙ στοιβαγμένα στο τέλος της παραγράφου.
2. Οι υποερωτήσεις (α, β, γ, δ) πρέπει να χρησιμοποιούν 
   <div class="subq"><span class="subq-num">X)</span> <span class="subq-text">...</span></div>
   ΠΟΤΕ <p class="text-content"> για υποερώτηση.
3. Το <div class="points-chip">⭐ N μονάδες</div> πρέπει να ακολουθεί ΑΜΕΣΩΣ μετά το subq του.
4. Υπο-στοιχεία (i, ii, iii) μένουν ως <p class="text-content"> μέσα στην ενότητα της υποερώτησης.
5. ΔΙΩΞΕ οποιοδήποτε Ελληνικό κείμενο που μπήκε κατά λάθος μέσα σε $...$ (π.χ. $η συνάρτηση f$).
6. Το subq-num πρέπει να ταιριάζει με το ΠΡΑΓΜΑΤΙΚΟ περιεχόμενο:
   - subq-num="β)" πρέπει να περιέχει το β ερώτημα, ΟΧΙ το α ή το γ
   - Αν το subq-num="γ)" αλλά μέσα λέει "δ) ..." → άλλαξέ το σε subq-num="δ)"
7. Διόρθωσε broken text όπως "ς(Μονάδες 6)" → να μπει στο σωστό subq ή points-chip
8. Κράτησε ΟΛΑ τα έγκυρα math LaTeX formulas ακριβώς όπως είναι.
9. Αν υπάρχουν διπλότυπα subq (ίδιο γράμμα δύο φορές), ΚΡΑΤΑ μόνο το σωστό.
10. Η πρώτη παράγραφος (ΘΕΜΑ X) είναι ΠΑΝΤΑ <p class="text-content">ΘΕΜΑ X</p>

ΔΙΑΘΕΣΙΜΑ OCR FORMULAS (εικόνα → LaTeX):
{formulas}

ΑΥΘΕΝΤΙΚΗ ΔΟΜΗ (sections — ποιες υποερωτήσεις υπάρχουν):
{sections}

ΤΡΕΧΟΝ HTML ΠΟΥ ΠΡΕΠΕΙ ΝΑ ΔΙΟΡΘΩΣΕΙΣ:
{current_html}

ΔΙΟΡΘΩΜΕΝΟ JSON ARRAY (MONO το array, τίποτα άλλο):"""

def extract_formulas_for_q(qid, ocr_data):
    """Get available OCR formulas for this question."""
    formulas = []
    for k, v in ocr_data.items():
        if k.startswith(f"{qid}/"):
            latex = v.get("latex", "").strip("$ ")
            latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
            if latex and len(latex) < 200:
                formulas.append(f"  {k}: {latex}")
    return "\n".join(formulas) if formulas else "(καμία)"

def format_sections(sections):
    """Format sections array as readable text for the LLM."""
    lines = []
    for s in sections:
        stype = s.get("type", "?")
        if stype == "sub_question":
            lines.append(f"  [{stype}] {s.get('number','')}: {s.get('content','')[:200]}")
        elif stype == "text":
            lines.append(f"  [{stype}] {s.get('content','')[:200]}")
        else:
            lines.append(f"  [{stype}]")
    return "\n".join(lines)

def validate_fix(new_parts):
    """Validate that the LLM output is a proper array of strings."""
    if not isinstance(new_parts, list):
        return False
    if len(new_parts) == 0:
        return False
    if not all(isinstance(p, str) for p in new_parts):
        return False
    # Must contain at least one subq or text-content
    if not any('class=' in p for p in new_parts):
        return False
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="mathematics")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--id", type=int, default=0)
    args = parser.parse_args()

    cfg = load_subject_config(args.subject)
    data_dir = os.path.join(BASE_DIR, cfg.get("data", {}).get("data_dir",
                            f"data/subjects/{args.subject}"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    ocr_file = os.path.join(data_dir, "ocr_results.json")
    progress_file = os.path.join(data_dir, "llm_html_fix_progress.json")

    with open(v2_file, encoding="utf-8") as f:
        v2 = json.load(f)
    with open(ocr_file, encoding="utf-8") as f:
        ocr = json.load(f)

    # Progress tracking
    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file, encoding="utf-8") as f:
            progress = json.load(f)
    progress.setdefault("completed", [])

    if args.id:
        targets = [args.id]
    else:
        targets = [q["id"] for q in v2]
        # Skip already completed
        targets = [qid for qid in targets if str(qid) not in progress["completed"]]
        if args.limit > 0:
            targets = targets[:args.limit]

    if not targets:
        print("✅ All questions already processed!")
        return

    client = init_client()
    print(f"🎯 LLM HTML Fixer [{args.subject}]")
    print(f"   Remaining: {len(targets)} questions")
    print(f"   Completed: {len(progress['completed'])}")

    saved = 0
    for idx, qid in enumerate(targets):
        q = next((x for x in v2 if x["id"] == qid), None)
        if not q:
            continue

        parts = q.get("question_html_parts", [])
        sections = q.get("sections", [])
        if not parts:
            progress["completed"].append(str(qid))
            continue

        formulas_text = extract_formulas_for_q(qid, ocr)
        sections_text = format_sections(sections)
        current_html = json.dumps(parts, ensure_ascii=False, indent=2)

        prompt = HTML_FIX_PROMPT.format(
            formulas=formulas_text,
            sections=sections_text,
            current_html=current_html
        )

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": HTML_FIX_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.15,
                max_tokens=3000
            )
            raw = resp.choices[0].message.content or "[]"

            # Extract JSON array from response
            json_match = re.search(r'\[[\s\S]*\]', raw)
            if json_match:
                try:
                    new_parts = json.loads(json_match.group(0))
                except:
                    new_parts = []
            else:
                new_parts = []

            if validate_fix(new_parts):
                old_count = "\n".join(parts).count("$") // 2
                new_count = "\n".join(new_parts).count("$") // 2
                q["question_html_parts"] = new_parts
                q["question_html"] = "\n".join(new_parts)
                progress["completed"].append(str(qid))
                print(f"  Q{qid}: ✓ {len(parts)}→{len(new_parts)} parts, {old_count}→{new_count} formulas")
                saved += 1
            else:
                print(f"  Q{qid}: ⚠️ invalid response (kept original)")
                progress["completed"].append(str(qid))

        except Exception as e:
            print(f"  Q{qid}: ❌ {e}")
            time.sleep(2)

        # Save periodically
        if saved > 0 and saved % 10 == 0:
            with open(v2_file, "w", encoding="utf-8") as f:
                json.dump(v2, f, ensure_ascii=False, indent=2)
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
            print(f"  💾 Saved ({saved} fixed so far)")

        time.sleep(1.5)  # rate limit

    # Final save
    with open(v2_file, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! Fixed: {saved}, Total completed: {len(progress['completed'])}")
    print(f"   Progress: {progress_file}")

if __name__ == "__main__":
    main()