#!/usr/bin/env python3
"""
polish_math_hints.py — LLM reformats existing hints to add LaTeX ($...$)

Sends each hint to DeepSeek with a simple prompt to convert plain math
expressions to $...$ LaTeX. No content changes — only formatting.

Preserves all existing hints, only updates hint_text. No regeneration cost
since each hint is a single short API call.

Usage:
    python3 polish_math_hints.py --limit 5
    python3 polish_math_hints.py
"""

import json, os, sys, time, argparse
from dotenv import load_dotenv
load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))

SYSTEM = """Είσαι μαθηματικός. Πρόσθεσε LaTeX ($...$) σε ΚΑΘΕ μαθηματική έκφραση στο παρακάτω κείμενο.

ΚΑΝΟΝΕΣ:
1. ΟΛΕΣ οι μαθηματικές εκφράσεις (συναρτήσεις, παράγωγοι, ολοκληρώματα, όρια, μεταβλητές, αριθμοί σε μαθηματικό context) ΠΡΕΠΕΙ να μπουν σε $...$
2. ΜΗΝ αλλάξεις το νόημα, τη δομή, ή το ύφος του κειμένου
3. Διατήρησε το ίδιο στυλ — φιλικό, ενθαρρυντικό, στα Ελληνικά
4. Αν το κείμενο ΔΕΝ περιέχει μαθηματικά, επίστρεψέ το ΑΥΤΟΥΣΙΟ
5. Επίστρεψε ΜΟΝΟ το διορθωμένο κείμενο, χωρίς επεξηγήσεις

Παραδείγματα:
- "η παράγωγος f'(x)" → "η παράγωγος $f'(x)$"
- "το όριο lim x→0 f(x)" → "το όριο $\lim_{x \to 0} f(x)$"
- "η συνάρτηση f είναι συνεχής" → "η συνάρτηση $f$ είναι συνεχής"
- "θυμήσου τον τύπο E = 1/2 mv²" → "θυμήσου τον τύπο $E = \\frac{1}{2}mv^2$"
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
        hints = q.get("hints", [])
        if not hints:
            continue
        for hi, h in enumerate(hints):
            for lhi, lh in enumerate(h.get("hints", [])):
                text = lh.get("hint_text", "")
                if not text:
                    continue
                # Skip if already has good LaTeX coverage
                if text.count("$") >= 4:
                    continue
                
                try:
                    resp = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": text}
                        ],
                        temperature=0.1, max_tokens=500
                    )
                    polished = (resp.choices[0].message.content or text).strip()
                    if polished and len(polished) > 10:
                        old_latex = text.count("$")
                        new_latex = polished.count("$")
                        hints[hi]["hints"][lhi]["hint_text"] = polished
                        fixed += 1
                        if new_latex != old_latex:
                            print(f"  Q{q['id']} {h['number']} L{lh['level']}: {old_latex}→{new_latex} $")
                except Exception as e:
                    print(f"  Q{q['id']} ERR: {e}")
                
                time.sleep(0.3)

        q["hints"] = hints

        if (qi + 1) % 20 == 0:
            with open(v2_path, "w", encoding="utf-8") as f:
                json.dump(v2, f, ensure_ascii=False, indent=2)
            print(f"  💾 Saved ({qi+1}/{len(v2)})")

    with open(v2_path, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Polished {fixed} hints in {slug}")

if __name__ == "__main__":
    main()