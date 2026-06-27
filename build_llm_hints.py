#!/usr/bin/env python3
"""
build_llm_hints.py — Offline 3-tier Socratic hints (informatics + mathematics)

Usage:
    python3 build_llm_hints.py --subject informatics
    python3 build_llm_hints.py --subject mathematics --limit 5
"""

import json, os, sys, argparse, time
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

INFORMATICS_HINT_PROMPT = """You are an expert Greek Informatics tutor using Socratic scaffolding.
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

MATH_HINT_PROMPT = """Είσαι ένας υπομονετικός καθηγητής Μαθηματικών που βοηθά μαθητή για τις Πανελλήνιες.
Δώσε μια σύντομη βοήθεια (ΟΧΙ την πλήρη λύση) στα Ελληνικά.

ΚΡΙΣΙΜΟ: ΟΛΕΣ οι μαθηματικές εκφράσεις ΠΡΕΠΕΙ να είναι σε LaTeX μέσα σε $...$.
Παράδειγμα: "η παράγωγος $f'(x)$" ΟΧΙ "η παράγωγος f'(x)".
Για ολοκληρώματα: $\\int_{a}^{b} f(x)dx$
Για όρια: $\\lim_{x \\to 0} f(x)$
Για κλάσματα: $\\frac{a}{b}$

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε το σχετικό θεώρημα ή ορισμό. Χρησιμοποίησε LaTeX για κάθε μαθηματικό σύμβολο.
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα επίλυσης με LaTeX (π.χ. "Βρες την $f'(x)$", "Εφάρμοσε το θεώρημα $Bolzano$")
- Επίπεδο 3: Δώσε τη γενική μεθοδολογία με LaTeX χωρίς αριθμητικά αποτελέσματα

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

def get_subquestions(q):
    subs = []
    for s in q.get("sections", []):
        if s["type"] == "sub_question":
            subs.append({"number": s.get("number","?"), "content": s.get("content","")})
    return subs

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="informatics", help="Subject ID")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--id", type=int, default=0)
    args = parser.parse_args()

    subject_id = args.subject
    cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    progress_file = os.path.join(data_dir, "llm_hints_progress.json")

    # Load prompts
# Load subject-specific prompts
    prompts = _load_subject_prompts(subject_id)
    system_prompt = "You are a Greek tutor. Answer ONLY in Greek. Return valid JSON."
    
    # All subjects use generic prompt that references LaTeX
    hint_prompt = """Είσαι ένας υπομονετικός καθηγητής που βοηθά μαθητή για τις Πανελλήνιες.
Δώσε μια σύντομη βοήθεια (ΟΧΙ την πλήρη λύση) στα Ελληνικά.

ΚΡΙΣΙΜΟ: ΟΛΕΣ οι μαθηματικές/επιστημονικές εκφράσεις ΠΡΕΠΕΙ να είναι σε LaTeX μέσα σε $...$.

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε το σχετικό θεώρημα, ορισμό ή κανόνα
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα επίλυσης
- Επίπεδο 3: Δώσε τη γενική μεθοδολογία χωρίς αριθμητικά αποτελέσματα

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

    client = init_client()
    with open(v2_file, encoding="utf-8") as f:
        data = json.load(f)

    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file, encoding="utf-8") as f:
            progress = json.load(f)
    progress.setdefault("completed", [])

    if args.id:
        data = [q for q in data if q["id"] == args.id]
    elif args.limit > 0:
        data = data[:args.limit]

    print(f"🎯 Hint Generator [{subject_id}]")
    print(f"   Questions: {len(data)}")
    print(f"   Completed: {len(progress['completed'])}")

    for i, q in enumerate(data):
        qid = q["id"]
        subs = get_subquestions(q)
        if not subs:
            subs = [{"number":"?", "content": q.get("question_text","")[:2000]}]
        
        hints = q.get("hints", [])
        for si, sub in enumerate(subs):
            key = f"{qid}_{si}"
            if key in progress["completed"]:
                continue

            if si >= len(hints):
                hints.append({"subq_idx": si, "number": sub["number"], "hints": []})
            
            subq_hints = hints[si]["hints"]
            for level in [1, 2, 3]:
                if any(h.get("level") == level for h in subq_hints):
                    continue

                prompt = hint_prompt.format(
                    level=level, subq_num=sub["number"],
                    subq_text=sub["content"][:2000],
                    answer_text=q.get("answer_text","")[:1500]
                )
                try:
                    resp = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role":"system","content":system_prompt},
                                  {"role":"user","content":prompt}],
                        temperature=0.2, max_tokens=400,
                        response_format={"type":"json_object"}
                    )
                    raw = resp.choices[0].message.content or "{}"
                    try:
                        hdata = json.loads(raw)
                        text = hdata.get("hint_text", raw[:300])
                    except:
                        import re
                        m = re.search(r'\{.*\}', raw, re.DOTALL)
                        text = json.loads(m.group(0)).get("hint_text", raw[:300]) if m else raw[:300]
                    subq_hints.append({"level": level, "hint_text": text.strip()})
                    print(f"  Q{qid} subq {sub['number']} L{level} ✓")
                except Exception as e:
                    print(f"  Q{qid} subq {sub['number']} L{level} ❌ {e}")
                    subq_hints.append({"level": level, "hint_text": f"Σφάλμα: {str(e)[:100]}"})
                time.sleep(0.8)

            hints[si] = {"subq_idx": si, "number": sub["number"], "hints": subq_hints}
            progress["completed"].append(key)

        q["hints"] = hints
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        if (i+1) % 5 == 0:
            with open(v2_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  Saved progress ({i+1}/{len(data)})")

    with open(v2_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Done! {len(progress['completed'])} hint-groups for {subject_id}")

if __name__ == "__main__":
    main()