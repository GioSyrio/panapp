#!/usr/bin/env python3
"""
polish_math_answers.py — LLM reformats answer_text → answer_html with LaTeX

Takes the plain-text answer and converts it to HTML with proper $...$ LaTeX
for all mathematical expressions. Preserves existing answer structure.

Cost: ~$0.15, ~3 minutes for 202 answers.

Usage:
    python3 polish_math_answers.py --limit 5
    python3 polish_math_answers.py
"""

import json, os, sys, time, argparse
from dotenv import load_dotenv
load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))

SYSTEM = """Είσαι μαθηματικός. Μετάτρεψε το παρακάτω κείμενο λύσης σε HTML με LaTeX.

ΚΑΝΟΝΕΣ:
1. ΟΛΕΣ οι μαθηματικές εκφράσεις ΠΡΕΠΕΙ να είναι σε $...$ (inline) ή $$...$$ (display)
2. Τύλιξε κάθε βήμα λύσης σε <div class="sol-step"><div class="sol-step-label">βήμα</div><div class="sol-step-text">...</div></div>
3. Χρησιμοποίησε Ελληνικά για τις ετικέτες βημάτων (π.χ. "Βήμα 1", "α)", "β)")
4. Διατήρησε ΟΛΟ το περιεχόμενο, μόνο πρόσθεσε HTML δομή και LaTeX
5. ΜΗΝ αλλάξεις μαθηματικά αποτελέσματα ή αριθμούς
6. Επίστρεψε ΜΟΝΟ το HTML, χωρίς επεξηγήσεις

Παράδειγμα εισόδου:
"α) f'(x)=3x^2-2x, f'(x)=0 => x=0 ή x=2/3. β) f γν. αύξουσα στο (-∞,0)∪(2/3,+∞)"

Παράδειγμα εξόδου:
<div class="sol-step"><div class="sol-step-label">α)</div><div class="sol-step-text">$f'(x)=3x^2-2x$, $f'(x)=0 \Rightarrow x=0$ ή $x=\\frac{2}{3}$.</div></div>
<div class="sol-step"><div class="sol-step-label">β)</div><div class="sol-step-text">$f$ γν. αύξουσα στο $(-\\infty,0)\\cup(\\frac{2}{3},+\\infty)$</div></div>
"""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--subject", default="mathimatika_prosanatolismoy")
    a = p.parse_args()

    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Set DEEPSEEK_API_KEY"); sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    slug = a.subject
    v2_path = os.path.join(BASE, "data", "subjects", slug, "questions_v2.json")
    with open(v2_path, encoding="utf-8") as f:
        v2 = json.load(f)

    if a.limit:
        v2 = v2[:a.limit]

    fixed = 0
    for qi, q in enumerate(v2):
        answer = q.get("answer_text", "")
        if not answer or len(answer) < 30:
            continue
        
        # Skip if already has good LaTeX
        cur_html = q.get("answer_html", "")
        if cur_html.count("$") >= 6:
            continue

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": answer[:3000]}
                ],
                temperature=0.1, max_tokens=1000
            )
            formatted = (resp.choices[0].message.content or "").strip()
            if formatted and len(formatted) > 30:
                old_latex = cur_html.count("$")
                new_latex = formatted.count("$")
                q["answer_html"] = formatted
                fixed += 1
                if new_latex > old_latex:
                    print(f"  Q{q['id']}: {old_latex}→{new_latex} LaTeX in answer")
        except Exception as e:
            print(f"  Q{q['id']} ERR: {e}")

        time.sleep(0.4)

        if (qi + 1) % 20 == 0:
            with open(v2_path, "w", encoding="utf-8") as f:
                json.dump(v2, f, ensure_ascii=False, indent=2)
            print(f"  💾 Saved ({qi+1}/{len(v2)})")

    with open(v2_path, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Formatted {fixed} answers in {slug}")

if __name__ == "__main__":
    main()