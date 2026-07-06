#!/usr/bin/env python3
"""
fix_ocr_greek.py — Strip corrupted OCR formulas that are Greek prose disguised as LaTeX

Catches patterns where OCR misreads Greek text as LaTeX commands:
  - \eta \mu → ημ (sine)
  - \tau \text{ote} → τότε (then)
  - \varepsilon \varphi → εφ (tan)
  - \kappa, \mu → κ, μ (just variables)

Touches ONLY question_html_parts and question_html.
"""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

# Patterns that indicate OCR misread Greek prose as LaTeX
CORRUPT_PATTERNS = [
    (r'\\eta\\s*\\\\mu', 'ημ'),        # \eta \mu → sine
    (r'\\tau\\s*\\\\text\{ote\}', 'τότε'),  # \tau \text{ote} → then
    (r'\\varepsilon\\s*\\\\varphi', 'εφ'),  # \varepsilon \varphi → tan
    (r'\\kappa\s*,?\\s*\\\\mu\s*\\\\in\s*\\\\mathbb', 'κ, μ'),
    (r'\\sigma\s*\\\\upsilon\s*\\\\nu', 'συν'),  # sigma upsilon nu → συν
    (r'\\delta\s*\\\\iota\s*\\\\alpha', 'δια'),  # delta iota alpha → δια
]

def strip_greek_formulas(html):
    """Remove $...$ formulas that match Greek prose patterns."""
    def replace_formula(m):
        content = m.group(1)
        # Check if it matches any corrupt pattern
        for pattern, replacement in CORRUPT_PATTERNS:
            if re.search(pattern, content):
                return ''  # remove the formula entirely
        # Check if it's just Greek letters with no math operators
        if not re.search(r'[\\{}^_=<>+\-*/∫∑∏√∞∑∏]|frac|lim|int|sqrt|to|cdot|left|right|begin|end|mathbb|mathbf|mathrm', content):
            # If it contains 4+ consecutive Greek letters, it's prose
            if re.search(r'[α-ω]{4,}|\\\\[a-z]+\\s+\\\\[a-z]+', content, re.IGNORECASE):
                return ''
        return m.group(0)

    return re.sub(r'\$([^$]+)\$', replace_formula, html)

def main():
    with open(V2, encoding="utf-8") as f:
        v2 = json.load(f)

    fixed = 0
    total_fixed = 0

    for q in v2:
        parts = q.get("question_html_parts", [])
        new_parts = []
        changed = False

        for p in parts:
            new_p = strip_greek_formulas(p)
            new_p = re.sub(r'\s{2,}', ' ', new_p)  # clean double spaces
            new_parts.append(new_p)
            if new_p != p:
                changed = True

        if changed:
            q["question_html_parts"] = new_parts
            q["question_html"] = "\n".join(new_parts)
            fixed += 1
            # Count removed formulas
            old_count = "\n".join(parts).count("$")
            new_count = "\n".join(new_parts).count("$")
            total_fixed += (old_count - new_count) // 2
            print(f"  Q{q['id']}: removed {(old_count - new_count) // 2} corrupt formulas")

    with open(V2, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Fixed {fixed} questions, removed {total_fixed} corrupt OCR formulas")

if __name__ == "__main__":
    main()