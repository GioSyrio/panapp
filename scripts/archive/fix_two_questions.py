#!/usr/bin/env python3
"""Fix question_html_parts for Q26366 and Q23314 specifically."""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))

# ── Q26366 fix ──────────────────────────────────────────────────────────
q = next(x for x in v2 if x["id"] == 26366)
q["question_html_parts"] = [
    '<p class="text-content">ΘΕΜΑ 2</p>',
    '<p class="text-content">Στο παρακάτω σχήμα δίνεται η γραφική παράσταση της παραγώγου μιας πολυωνυμικής συνάρτησης τρίτου βαθμού η οποία είναι ορισμένη στο κλειστό διάστημα .</p>',
    '<div class="subq"><span class="subq-num">α)</span> <span class="subq-text">Ποια είναι η κλίση της στο ;</span></div>',
    '<div class="points-chip">⭐ 6 μονάδες</div>',
    '<div class="subq"><span class="subq-num">β)</span> <span class="subq-text">Να αποδείξετε ότι η είναι γνησίως αύξουσα στο .</span></div>',
    '<div class="points-chip">⭐ 8 μονάδες</div>',
    '<div class="subq"><span class="subq-num">γ)</span> <span class="subq-text">Να βρείτε τον τύπο της .</span></div>',
    '<div class="points-chip">⭐ 6 μονάδες</div>',
    '<div class="subq"><span class="subq-num">δ)</span> <span class="subq-text">Να υπολογίσετε το εμβαδόν μεταξύ της γραφικής παράστασης της και του άξονα στο διάστημα .</span></div>',
    '<div class="points-chip">⭐ 5 μονάδες</div>',
]
q["question_html"] = "\n".join(q["question_html_parts"])
print(f"Q26366: fixed → {len(q['question_html_parts'])} parts, {q['question_html'].count('$')//2} formulas")

# ── Q23314 fix ──────────────────────────────────────────────────────────
q = next(x for x in v2 if x["id"] == 23314)
q["question_html_parts"] = [
    '<p class="text-content">ΘΕΜΑ 2</p>',
    '<p class="text-content">Στο παρακάτω σχήμα δίνεται η γραφική παράσταση μιας συνάρτησης , για την οποία γνωρίζουμε ότι είναι συνεχής και τέμνει τον άξονα x\'x σε ένα μόνο σημείο με τετμημένη</p>',
    '<p class="text-content">και τον άξονα y\'y σε ένα μόνο σημείο με τεταγμένη 2.</p>',
    '<div class="subq"><span class="subq-num">α)</span> <span class="subq-text">Από την γραφική παράσταση ή με οποιονδήποτε άλλο τρόπο, να προσδιορίσετε τα όρια:</span></div>',
    '<p class="text-content">i) $\\lim_{x \\to 0} f(x)$</p>',
    '<p class="text-content">ii) $\\lim_{x \\to -2^+} f(x)$</p>',
    '<p class="text-content">iii) $\\lim_{x \\to -2^-} f(x)$</p>',
    '<div class="points-chip">⭐ 12 μονάδες</div>',
    '<div class="subq"><span class="subq-num">β)</span> <span class="subq-text">Να βρείτε τα όρια:</span></div>',
    '<p class="text-content">i) $\\lim_{x \\to 0} \\frac{f(x)}{x}$</p>',
    '<div class="points-chip">⭐ 6 μονάδες</div>',
    '<p class="text-content">ii) $\\lim_{x \\to -2} \\frac{f(x)}{x+2}$</p>',
    '<div class="points-chip">⭐ 7 μονάδες</div>',
    '<p class="text-content">και να αιτιολογήσετε την απάντησή σας.</p>',
]
q["question_html"] = "\n".join(q["question_html_parts"])
print(f"Q23314: fixed → {len(q['question_html_parts'])} parts, {q['question_html'].count('$')//2} formulas")

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)
print("\n✅ Both fixed and saved")