#!/usr/bin/env python3
"""Fix Q31149 — missing formulas"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))
q = next(x for x in v2 if x["id"] == 31149)

q["question_html_parts"] = [
    '<p class="text-content">ΘΕΜΑ 4</p>',
    '<p class="text-content">Θεωρούμε τη συνάρτηση $f(x) = \\ln\\left(\\frac{1+x}{x}\\right)$ με $x > 0$ .</p>',
    '<div class="subq"><span class="subq-num">α)</span> <span class="subq-text">Να αποδείξτε ότι $f(x) > 0$ για κάθε $x > 0$ και ότι η $f$ είναι γνησίως φθίνουσα στο $(0, +\\infty)$.</span></div>',
    '<div class="points-chip">⭐ 9 μονάδες</div>',
    '<div class="subq"><span class="subq-num">β)</span> <span class="subq-text">Να λύσετε την ανίσωση $\\ln(1+f(x)) - \\ln(f(x)) > f^2(x) \\cdot f(\\ln 2)$.</span></div>',
    '<div class="points-chip">⭐ 7 μονάδες</div>',
    '<div class="subq"><span class="subq-num">γ)</span> <span class="subq-text">Να αποδείξετε ότι το εμβαδόν του χωρίου που ορίζεται από τη γραφική παράσταση της $f$ , τις ευθείες $x=1$, $x=2$ και τον άξονα $x\'x$ είναι $E = \\ln\\left(\\frac{27}{16}\\right)$.</span></div>',
    '<div class="points-chip">⭐ 9 μονάδες</div>',
]
q["question_html"] = "\n".join(q["question_html_parts"])

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f"Q31149: {len(q['question_html_parts'])} parts, {q['question_html'].count('$')//2} formulas")
print("  Fixed: $f(x) = \\ln(...)$, $f(x) > 0$, $(0, +\\infty)$ in subq")
print("  Fixed: inequality in β, area formula in γ with input like E = ln(27/16)")